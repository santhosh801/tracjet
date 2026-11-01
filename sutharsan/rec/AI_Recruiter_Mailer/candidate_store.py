"""
Candidate profiles and their Template Library.

Each candidate owns their own name, contact details, resume, analysed profile,
Gmail + App Password, CTC/availability settings and 5 example templates.
The active candidate (settings["active_candidate_id"]) controls the sender,
resume attachment, signature and JD matching.
"""
import hashlib
import json
import os
import re
import shutil
from datetime import datetime

import secret_store
from database import get_db
from settings import load_settings, save_settings

TEMPLATE_SLOTS = 5
FILES_DIR = "candidate_files"
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")

CANDIDATE_FIELDS = ["name", "email", "phone", "gmail_address", "expected_ctc", "availability", "current_ctc",
                    "include_current_ctc", "extra_signature", "drafting_instructions"]


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def gmail_fingerprint(address: str, app_password: str) -> str:
    raw = (address or "").strip().lower() + "\0" + secret_store.normalize_app_password(app_password)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


# ── Candidate CRUD ───────────────────────────────────────────────────────
def list_candidates() -> list[dict]:
    conn = get_db()
    rows = conn.execute("SELECT id, name, gmail_address FROM candidates ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_candidate(cid) -> dict | None:
    if cid is None:
        return None
    conn = get_db()
    row = conn.execute("SELECT * FROM candidates WHERE id=?", (cid,)).fetchone()
    conn.close()
    if not row:
        return None
    c = dict(row)
    c["profile"] = json.loads(c["profile_json"]) if c.get("profile_json") else {}
    c["include_current_ctc"] = int(c.get("include_current_ctc") or 0)
    return c


def create_candidate(name: str = "New Candidate") -> int:
    conn = get_db()
    cur = conn.execute("INSERT INTO candidates (name, expected_ctc, availability, updated_at) VALUES (?, ?, ?, ?)",
                       (name, "Negotiable", "Immediate Joiner", _now()))
    cid = cur.lastrowid
    for slot in range(1, TEMPLATE_SLOTS + 1):
        conn.execute("INSERT OR IGNORE INTO templates (candidate_id, slot, name, role_category, example_subject, "
                     "example_body, updated_at) VALUES (?, ?, '', '', '', '', ?)", (cid, slot, _now()))
    conn.commit()
    conn.close()
    return cid


def update_candidate(cid: int, data: dict, app_password: str | None = None):
    """Save candidate fields.  Changing Gmail address or App Password resets the verified flag."""
    current = get_candidate(cid) or {}
    fields = {k: data[k] for k in CANDIDATE_FIELDS if k in data}
    if "expected_ctc" in fields and not (fields["expected_ctc"] or "").strip():
        fields["expected_ctc"] = "Negotiable"
    if "availability" in fields and not (fields["availability"] or "").strip():
        fields["availability"] = "Immediate Joiner"
    if "include_current_ctc" in fields:
        fields["include_current_ctc"] = 1 if fields["include_current_ctc"] else 0
    if app_password is not None:
        fields["gmail_app_password_enc"] = secret_store.protect(secret_store.normalize_app_password(app_password))
    new_addr = fields.get("gmail_address", current.get("gmail_address") or "")
    new_pw = app_password if app_password is not None else get_app_password(cid)
    if gmail_fingerprint(new_addr, new_pw) != (current.get("gmail_fingerprint") or ""):
        fields["gmail_verified"] = 0
    fields["updated_at"] = _now()
    conn = get_db()
    conn.execute(f"UPDATE candidates SET {', '.join(f'{k}=?' for k in fields)} WHERE id=?",
                 list(fields.values()) + [cid])
    conn.commit()
    conn.close()


def delete_candidate(cid: int):
    conn = get_db()
    conn.execute("DELETE FROM templates WHERE candidate_id=?", (cid,))
    conn.execute("DELETE FROM recruiters WHERE candidate_id=? AND status!='Sent'", (cid,))
    conn.execute("DELETE FROM candidates WHERE id=?", (cid,))
    conn.commit()
    conn.close()
    settings = load_settings()
    if settings.get("active_candidate_id") == cid:
        settings["active_candidate_id"] = None
        save_settings(settings)


def get_app_password(cid: int) -> str:
    conn = get_db()
    row = conn.execute("SELECT gmail_app_password_enc FROM candidates WHERE id=?", (cid,)).fetchone()
    conn.close()
    try:
        return secret_store.reveal(row["gmail_app_password_enc"]) if row else ""
    except Exception:
        return ""


def get_active_candidate_id():
    cid = load_settings().get("active_candidate_id")
    if cid is not None and get_candidate(cid):
        return cid
    cands = list_candidates()
    return cands[0]["id"] if cands else None


def set_active_candidate(cid):
    settings = load_settings()
    settings["active_candidate_id"] = cid
    save_settings(settings)


# ── Gmail ────────────────────────────────────────────────────────────────
def connect_and_test_gmail(cid: int, tester=None) -> tuple[bool, str]:
    """Log in to Gmail SMTP with the candidate's App Password and record the result."""
    if tester is None:
        from gmail_smtp import test_connection as tester
    c = get_candidate(cid)
    if not c:
        return False, "Candidate not found."
    address = (c.get("gmail_address") or "").strip()
    pw = get_app_password(cid)
    if not EMAIL_RE.match(address):
        return False, "Enter a valid Gmail address."
    if not secret_store.is_valid_app_password(pw):
        return False, ("The App Password must be the 16-character Google App Password "
                       "(not your normal Gmail password).")
    ok, msg = tester(address, pw)
    conn = get_db()
    conn.execute("UPDATE candidates SET gmail_verified=?, gmail_verified_at=?, gmail_fingerprint=? WHERE id=?",
                 (1 if ok else 0, _now() if ok else None, gmail_fingerprint(address, pw) if ok else None, cid))
    conn.commit()
    conn.close()
    return ok, msg


def gmail_connected(c: dict) -> bool:
    if not c or not c.get("gmail_verified"):
        return False
    return gmail_fingerprint(c.get("gmail_address"), get_app_password(c["id"])) == (c.get("gmail_fingerprint") or "")


# ── Resume + profile ─────────────────────────────────────────────────────
def store_resume(cid: int, source_path: str, analyze=True) -> dict:
    """Copy the resume into the candidate's folder, analyse it end-to-end and save the profile."""
    from resume_parser import analyze_resume_file
    if not os.path.exists(source_path):
        raise FileNotFoundError(source_path)
    folder = os.path.abspath(os.path.join(FILES_DIR, str(cid)))
    os.makedirs(folder, exist_ok=True)
    original = os.path.basename(source_path)
    dest = os.path.join(folder, original)
    if os.path.abspath(source_path) != dest:
        for f in os.listdir(folder):  # one resume per candidate
            try:
                os.remove(os.path.join(folder, f))
            except OSError:
                pass
        shutil.copy2(source_path, dest)
    fields = {"resume_path": dest, "resume_original_name": original, "updated_at": _now()}
    profile = {}
    if analyze:
        profile, text = analyze_resume_file(dest)
        fields.update(resume_text=text, profile_json=json.dumps(profile, ensure_ascii=False),
                      profile_status="analyzed", resume_analyzed_at=_now())
    conn = get_db()
    conn.execute(f"UPDATE candidates SET {', '.join(f'{k}=?' for k in fields)} WHERE id=?",
                 list(fields.values()) + [cid])
    conn.commit()
    conn.close()
    # Fill empty contact fields from the resume (never overwrite user-entered values)
    c = get_candidate(cid)
    fill = {}
    for key in ("name", "email", "phone"):
        cur = (c.get(key) or "").strip()
        if (not cur or (key == "name" and cur == "New Candidate")) and profile.get(key):
            fill[key] = profile[key]
    if fill:
        update_candidate(cid, fill)
    return profile


def save_profile(cid: int, profile: dict, confirmed: bool = True):
    conn = get_db()
    conn.execute("UPDATE candidates SET profile_json=?, profile_status=?, updated_at=? WHERE id=?",
                 (json.dumps(profile, ensure_ascii=False), "confirmed" if confirmed else "analyzed", _now(), cid))
    conn.commit()
    conn.close()


def profile_ready(profile: dict) -> bool:
    return bool(profile) and bool(profile.get("evidence") or profile.get("skills"))


# ── Template Library ─────────────────────────────────────────────────────
def get_templates(cid) -> list[dict]:
    if cid is None:
        return []
    conn = get_db()
    rows = conn.execute("SELECT * FROM templates WHERE candidate_id=? ORDER BY slot", (cid,)).fetchall()
    conn.close()
    have = {r["slot"]: dict(r) for r in rows}
    out = [have.get(s, {"id": None, "candidate_id": cid, "slot": s, "name": "", "role_category": "",
                        "example_subject": "", "example_body": ""}) for s in range(1, TEMPLATE_SLOTS + 1)]
    for t in out:
        try:
            t["profile"] = json.loads(t["profile_json"]) if t.get("profile_json") else {}
        except ValueError:
            t["profile"] = {}
    return out


def save_template(cid: int, slot: int, name: str, role_category: str, example_subject: str, example_body: str):
    if not 1 <= int(slot) <= TEMPLATE_SLOTS:
        raise ValueError("Template slot must be 1-5")
    conn = get_db()
    conn.execute("""INSERT INTO templates (candidate_id, slot, name, role_category, example_subject, example_body,
                    updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(candidate_id, slot) DO UPDATE SET name=excluded.name,
                    role_category=excluded.role_category, example_subject=excluded.example_subject,
                    example_body=excluded.example_body, updated_at=excluded.updated_at""",
                 (cid, slot, name.strip(), role_category.strip(), example_subject.strip(), example_body.strip(), _now()))
    conn.commit()
    conn.close()


def store_template_resume(cid: int, slot: int, source_path: str) -> dict:
    """Attach a resume to one template slot (its job category) and analyse it.  Returns the profile."""
    from resume_parser import analyze_resume_file
    if not 1 <= int(slot) <= TEMPLATE_SLOTS:
        raise ValueError("Template slot must be 1-5")
    if not os.path.exists(source_path):
        raise FileNotFoundError(source_path)
    folder = os.path.abspath(os.path.join(FILES_DIR, str(cid), f"template_{slot}"))
    os.makedirs(folder, exist_ok=True)
    original = os.path.basename(source_path)
    dest = os.path.join(folder, original)
    if os.path.abspath(source_path) != dest:
        for f in os.listdir(folder):  # one resume per template
            try:
                os.remove(os.path.join(folder, f))
            except OSError:
                pass
        shutil.copy2(source_path, dest)
    profile, text = analyze_resume_file(dest)
    conn = get_db()
    conn.execute("INSERT OR IGNORE INTO templates (candidate_id, slot, name, role_category, example_subject, "
                 "example_body, updated_at) VALUES (?, ?, '', '', '', '', ?)", (cid, slot, _now()))
    conn.execute("UPDATE templates SET resume_path=?, resume_original_name=?, resume_text=?, profile_json=?, "
                 "resume_analyzed_at=?, updated_at=? WHERE candidate_id=? AND slot=?",
                 (dest, original, text, json.dumps(profile, ensure_ascii=False), _now(), _now(), cid, slot))
    conn.commit()
    conn.close()
    return profile


def remove_template_resume(cid: int, slot: int):
    """Detach the template's own resume — that template falls back to the candidate's main resume."""
    conn = get_db()
    row = conn.execute("SELECT resume_path FROM templates WHERE candidate_id=? AND slot=?", (cid, slot)).fetchone()
    conn.execute("UPDATE templates SET resume_path=NULL, resume_original_name=NULL, resume_text=NULL, "
                 "profile_json=NULL, resume_analyzed_at=NULL, updated_at=? WHERE candidate_id=? AND slot=?",
                 (_now(), cid, slot))
    conn.commit()
    conn.close()
    if row and row["resume_path"] and os.path.exists(row["resume_path"]):
        try:
            os.remove(row["resume_path"])
        except OSError:
            pass


def template_has_resume(t: dict | None) -> bool:
    return bool(t and t.get("resume_path") and os.path.exists(t["resume_path"]))


def resume_for(c: dict, t: dict | None) -> dict:
    """Resume used for a job drafted with template t: the template's own resume, else the candidate's main one."""
    if template_has_resume(t):
        return {"path": t["resume_path"], "name": t.get("resume_original_name") or os.path.basename(t["resume_path"]),
                "profile": t.get("profile") or {}, "text": t.get("resume_text") or "", "source": f"template {t['slot']}"}
    path = (c or {}).get("resume_path") or ""
    return {"path": path, "name": (c or {}).get("resume_original_name") or os.path.basename(path),
            "profile": (c or {}).get("profile") or {}, "text": (c or {}).get("resume_text") or "", "source": "main"}


def template_configured(t: dict) -> bool:
    return bool((t.get("name") or "").strip() and (t.get("example_subject") or "").strip()
                and (t.get("example_body") or "").strip())


# ── Readiness ────────────────────────────────────────────────────────────
def readiness(c: dict | None) -> dict:
    """Checklist for the CANDIDATE STATUS panel.  ready=True only if every item passes."""
    if not c:
        return {"ready": False, "items": [("Candidate selected", False, "Create a candidate in Candidate Setup")],
                "missing": ["No candidate selected"], "gmail_connected": False, "templates_configured": 0}
    profile = c.get("profile") or {}
    templates = get_templates(c["id"])
    n_templates = sum(template_configured(t) for t in templates)
    main_ok = bool(c.get("resume_path")) and os.path.exists(c.get("resume_path") or "")
    used = [t for t in templates if template_configured(t)]
    # every configured template must be able to attach a resume: its own, or the main one
    per_template_ok = bool(used) and all(template_has_resume(t) for t in used)
    resume_ok = main_ok or per_template_ok
    analyzed = bool(c.get("profile_json")) or (per_template_ok and all(t.get("profile_json") for t in used))
    prof_ok = profile_ready(profile) if main_ok or profile else \
        (per_template_ok and all(profile_ready(t.get("profile") or {}) for t in used))
    gmail_ok = gmail_connected(c)
    pw_ok = secret_store.is_valid_app_password(get_app_password(c["id"]))
    items = [
        ("Candidate name", bool((c.get("name") or "").strip() and c.get("name") != "New Candidate"),
         "Enter the candidate's name"),
        ("Candidate email", bool(EMAIL_RE.match((c.get("email") or "").strip())), "Enter a valid candidate email"),
        ("Resume uploaded", resume_ok, "Upload the candidate's resume (or one resume per template)"),
        ("Resume analyzed", analyzed, "Analyze the resume"),
        ("Candidate profile ready", prof_ok, "Resume analysis found no experience or skills — edit the profile"),
        ("App Password configured (16 characters)", pw_ok, "Enter the 16-character Google App Password"),
        ("Gmail connected", gmail_ok, "Click “Connect & Test Gmail”"),
        ("Phone configured", bool((c.get("phone") or "").strip()), "Enter the phone number"),
        ("Expected CTC configured", bool((c.get("expected_ctc") or "").strip()), "Enter Expected CTC"),
        ("Availability configured", bool((c.get("availability") or "").strip()), "Enter Availability"),
        (f"{TEMPLATE_SLOTS} templates configured ({n_templates}/{TEMPLATE_SLOTS})", n_templates == TEMPLATE_SLOTS,
         f"Fill name, subject and Gmail draft for all {TEMPLATE_SLOTS} templates "
         f"(missing: {', '.join(str(t['slot']) for t in templates if not template_configured(t)) or '—'})"),
    ]
    missing = [hint for _label, ok, hint in items if not ok]
    return {"ready": not missing, "items": items, "missing": missing, "gmail_connected": gmail_ok,
            "templates_configured": n_templates}
