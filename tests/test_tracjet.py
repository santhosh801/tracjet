"""
Tracjet critical-path tests.   Run from the project folder:

    python -m unittest discover -s tests -v

Uses fictional candidates and an isolated temp database / settings file.
No real email is sent — SMTP is replaced with fakes.
"""
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
import zlib
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import candidate_store as cs  # noqa: E402
import database as db  # noqa: E402
import gmail_smtp  # noqa: E402
import pipeline  # noqa: E402
import settings as settings_mod  # noqa: E402
from email_composer import CLOSING_SENTENCE, HIGHLIGHT_COUNT, ctc_line  # noqa: E402
from filters import (ELIGIBLE, FILTERED_EXPERIENCE, FILTERED_LOCATION, FilterConfig,  # noqa: E402
                     evaluate_filters)
from fixtures_data import (BD_RESUME, DEV_RESUME, JD_BD, JD_FSD, JD_PY, JD_TL, TEMPLATES)  # noqa: E402
from jd_analyzer import analyze_jd, parse_experience, split_bulk_posts  # noqa: E402
from send_pipeline import send_eligible  # noqa: E402

APP_PW = "abcdefghijklmnop"


# ── helpers ──────────────────────────────────────────────────────────────
def build_pdf(pages: list[list[str]], path: str):
    """Write a minimal multi-page text PDF (enough for pypdf extraction)."""
    objs = []
    font_id = 3 + 2 * len(pages)
    kids = []
    for i, lines in enumerate(pages):
        page_id, content_id = 3 + 2 * i, 4 + 2 * i
        kids.append(page_id)
        ops = ["BT", "/F1 10 Tf", "12 TL", "40 800 Td"]
        for line in lines:
            esc = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            ops.append(f"({esc}) Tj T*")
        ops.append("ET")
        stream = "\n".join(ops).encode("latin-1", errors="replace")
        objs.append((page_id, f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                              f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>".encode()))
        objs.append((content_id, b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream +
                     b"\nendstream"))
    objs.append((1, b"<< /Type /Catalog /Pages 2 0 R >>"))
    objs.append((2, f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] /Count {len(kids)} >>".encode()))
    objs.append((font_id, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"))
    objs.sort()
    out = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for oid, body in objs:
        offsets[oid] = len(out)
        out += f"{oid} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    n = max(offsets) + 1
    out += f"xref\n0 {n}\n0000000000 65535 f \n".encode()
    for i in range(1, n):
        out += f"{offsets[i]:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {n} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    with open(path, "wb") as f:
        f.write(out)


def build_docx(text: str, path: str):
    import zipfile
    from xml.sax.saxutils import escape
    paras = "".join(f"<w:p><w:r><w:t xml:space=\"preserve\">{escape(l)}</w:t></w:r></w:p>" for l in text.splitlines())
    doc = ('<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/'
           f'wordprocessingml/2006/main"><w:body>{paras}</w:body></w:document>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/'
                   'package/2006/content-types"/>')
        z.writestr("word/document.xml", doc)


def job_post(i, city="Bengaluru", exp="3-5 years", email=True, title="Business Development Manager"):
    mail = f"\nShare your CV at recruiter{i}@company{i}.test" if email else ""
    return (f"We're Hiring: {title}\nCompany: Company{i} Learning\nLocation: {city}\nExperience: {exp}\n"
            "Key Responsibilities:\n• Drive new business through inbound and outbound lead generation\n"
            "• Own the sales pipeline in CRM and achieve monthly revenue targets\n"
            "• Build strong client relationships and negotiate contracts" + mail + "\n")


def bulk(posts):
    return "\n".join(f"========== JOB {i + 1} ==========\n{p}" for i, p in enumerate(posts))


class FakeSender:
    def __init__(self, fail_for=()):
        self.calls = []
        self.fail_for = set(fail_for)

    def __call__(self, sender, pw, to, subject, body, body_type, attachments):
        self.calls.append({"sender": sender, "pw": pw, "to": to, "subject": subject, "body": body,
                           "attachments": list(attachments)})
        if to in self.fail_for:
            return False, "boom"
        return True, "Sent successfully"


class TracjetTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="tracjet_test_")
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp)
        self._old_db, self._old_settings = db.DB_FILE, settings_mod.SETTINGS_FILE
        db.DB_FILE = os.path.join(self.tmp, "test.db")
        settings_mod.SETTINGS_FILE = os.path.join(self.tmp, "settings.json")
        db.init_db()
        s = settings_mod.load_settings()
        s["delay_between_emails"] = 0
        settings_mod.save_settings(s)

    def tearDown(self):
        os.chdir(self.old_cwd)
        db.DB_FILE, settings_mod.SETTINGS_FILE = self._old_db, self._old_settings
        shutil.rmtree(self.tmp, ignore_errors=True)

    # candidate fully set up and READY
    def make_candidate(self, resume_text=BD_RESUME, name="Asha Raman", phone="+91 90000 11111",
                       gmail="asha.sender.test@gmail.com", connect=True, templates=TEMPLATES, fmt="docx",
                       **extra):
        cid = cs.create_candidate(name)
        path = os.path.join(self.tmp, f"{name.replace(' ', '_')}_Resume.{fmt}")
        if fmt == "pdf":
            build_pdf([resume_text.splitlines()], path)
        else:
            build_docx(resume_text, path)
        cs.store_resume(cid, path)
        data = {"name": name, "email": f"{name.split()[0].lower()}@example.org", "phone": phone,
                "gmail_address": gmail}
        data.update(extra)
        cs.update_candidate(cid, data, app_password=APP_PW)
        for t in templates:
            cs.save_template(cid, t["slot"], t["name"], t["role_category"], t["example_subject"], t["example_body"])
        if connect:
            ok, _ = cs.connect_and_test_gmail(cid, tester=lambda a, p: (True, f"Connected as {a}"))
            self.assertTrue(ok)
        return cid

    def ingest(self, cid, text):
        ctx = pipeline.load_context(cid)
        return pipeline.ingest_bulk_text(text, ctx)

    def record_for(self, cid, title_part):
        return next(r for r in db.get_all_recruiters(cid) if title_part.lower() in (r["job_title"] or "").lower())


# ── TEST 1 ───────────────────────────────────────────────────────────────
class Test01ResumeProfile(TracjetTestCase):
    def test_resume_upload_extracts_profile_end_to_end(self):
        cid = cs.create_candidate()
        lines = BD_RESUME.splitlines()
        split = lines.index("EDUCATION")
        path = os.path.join(self.tmp, "Asha_Raman_Resume.pdf")
        build_pdf([lines[:split], lines[split:]], path)  # education only on page 2
        profile = cs.store_resume(cid, path)
        self.assertEqual(profile["name"], "Asha Raman")
        self.assertEqual(profile["email"], "asha.raman.test@example.org")
        self.assertIn("90000", profile["phone"])
        self.assertEqual(profile["location"], "Bengaluru")
        self.assertEqual(profile["total_experience"], "4.9+ years")
        self.assertEqual(profile["current_role"], "Senior Business Development Executive")
        self.assertIn("BrightPath Learning Pvt Ltd", profile["companies"])
        self.assertIn("CloudNova Solutions", profile["companies"])
        self.assertTrue(any("120%" in a for a in profile["achievements"]))
        for skill in ("Salesforce", "HubSpot", "Negotiation", "Lead Generation"):
            self.assertIn(skill, profile["skills"])
        self.assertIn("Salesforce", profile["crm_tools"])
        self.assertIn("ChatGPT", profile["ai_tools"])
        self.assertTrue(any("MBA" in e for e in profile["education"]), "page-2 education must be analysed")
        self.assertIn("Kannada", profile["languages"])
        self.assertTrue(profile["certifications"])
        self.assertTrue(profile["leadership_experience"])
        self.assertIn("EdTech", profile["industries"])
        self.assertGreaterEqual(len(profile["evidence"]), 8)
        c = cs.get_candidate(cid)
        self.assertEqual(c["name"], "Asha Raman")  # filled from resume
        self.assertTrue(os.path.exists(c["resume_path"]))
        self.assertEqual(c["resume_original_name"], "Asha_Raman_Resume.pdf")

    def test_docx_resume(self):
        cid = cs.create_candidate()
        path = os.path.join(self.tmp, "ravi.docx")
        build_docx(DEV_RESUME, path)
        p = cs.store_resume(cid, path)
        self.assertEqual(p["current_role"], "Software Engineer")
        self.assertIn("Acme Technologies", p["companies"])
        self.assertIn("React.js", p["technical_skills"])


# ── TEST 2 ───────────────────────────────────────────────────────────────
class Test02Gmail(TracjetTestCase):
    def test_connect_and_test_gmail_uses_smtp_login(self):
        cid = self.make_candidate(connect=False)
        self.assertFalse(cs.readiness(cs.get_candidate(cid))["gmail_connected"])
        with mock.patch.object(gmail_smtp.smtplib, "SMTP") as smtp:
            ok, msg = cs.connect_and_test_gmail(cid)
        self.assertTrue(ok, msg)
        smtp.return_value.login.assert_called_once_with("asha.sender.test@gmail.com", APP_PW)
        c = cs.get_candidate(cid)
        self.assertTrue(cs.gmail_connected(c))
        self.assertTrue(cs.readiness(c)["ready"], cs.readiness(c)["missing"])
        # App Password stored encrypted, never plaintext
        raw = sqlite3.connect(db.DB_FILE).execute("SELECT gmail_app_password_enc FROM candidates").fetchone()[0]
        self.assertNotIn(APP_PW, raw)

    def test_rejects_non_app_password_and_auth_failure(self):
        cid = self.make_candidate(connect=False)
        cs.update_candidate(cid, {}, app_password="myNormalPassword!")
        ok, msg = cs.connect_and_test_gmail(cid, tester=lambda a, p: self.fail("SMTP must not be tried"))
        self.assertFalse(ok)
        self.assertIn("16-character", msg)
        cs.update_candidate(cid, {}, app_password="abcd efgh ijkl mnop")  # spaces are normalised
        ok, _ = cs.connect_and_test_gmail(cid, tester=lambda a, p: (False, "Authentication failed."))
        self.assertFalse(ok)
        self.assertFalse(cs.gmail_connected(cs.get_candidate(cid)))

    def test_changing_credentials_resets_connection(self):
        cid = self.make_candidate()
        self.assertTrue(cs.gmail_connected(cs.get_candidate(cid)))
        cs.update_candidate(cid, {"gmail_address": "other.test@gmail.com"})
        self.assertFalse(cs.gmail_connected(cs.get_candidate(cid)))


# ── TEST 3 ───────────────────────────────────────────────────────────────
class Test03Templates(TracjetTestCase):
    def test_five_templates_saved_and_renamable(self):
        cid = self.make_candidate()
        ts = cs.get_templates(cid)
        self.assertEqual(len(ts), 5)
        self.assertEqual([t["name"] for t in ts], [t["name"] for t in TEMPLATES])
        cs.save_template(cid, 3, "BD – Renamed", "Sales", "Subj", "Dear Hiring Team,\nBody")
        self.assertEqual(cs.get_templates(cid)[2]["name"], "BD – Renamed")
        self.assertEqual(cs.readiness(cs.get_candidate(cid))["templates_configured"], 5)
        with self.assertRaises(ValueError):
            cs.save_template(cid, 6, "x", "", "", "")

    def test_missing_template_blocks_readiness(self):
        cid = self.make_candidate(templates=TEMPLATES[:4])
        r = cs.readiness(cs.get_candidate(cid))
        self.assertFalse(r["ready"])
        self.assertTrue(any("missing: 5" in m for m in r["missing"]))


# ── TESTS 4-6 ────────────────────────────────────────────────────────────
class Test04to06TemplateSelection(TracjetTestCase):
    def test_04_business_development_jd(self):
        cid = self.make_candidate()
        self.ingest(cid, JD_BD)
        r = db.get_all_recruiters(cid)[0]
        self.assertEqual(r["template_name"], "Business Development")
        scores = json.loads(r["template_scores"])
        self.assertEqual(len(scores), 5, "all five templates must be scored")
        self.assertGreater(scores[0]["score"], scores[1]["score"])

    def test_05_full_stack_jd(self):
        cid = self.make_candidate(resume_text=DEV_RESUME, name="Ravi Kumar")
        self.ingest(cid, JD_FSD)
        self.assertEqual(db.get_all_recruiters(cid)[0]["template_name"], "Full Stack Developer")

    def test_06_team_lead_jd(self):
        cid = self.make_candidate()
        self.ingest(cid, JD_TL)
        self.assertEqual(db.get_all_recruiters(cid)[0]["template_name"], "Team Lead")

    def test_responsibilities_influence_choice(self):
        # Misleading title, but the body is pure customer-success work
        jd = ("Hiring: Associate\nCompany: Nimbus\nLocation: Pune\nExperience: 3-5 years\nResponsibilities:\n"
              "- Customer onboarding and customer support\n- Improve customer satisfaction and retention\n"
              "- Handle escalations for key accounts\nEmail: hr@nimbus.test")
        cid = self.make_candidate()
        self.ingest(cid, jd)
        self.assertEqual(db.get_all_recruiters(cid)[0]["template_name"], "Customer Success")


# ── TESTS 7-10: filters ──────────────────────────────────────────────────
class Test07to10Filters(TracjetTestCase):
    def setUp(self):
        super().setUp()
        self.cid = self.make_candidate()
        posts = [job_post(1, "Bengaluru", "3-5 years"), job_post(2, "Chennai", "4-6 years"),
                 job_post(3, "Hyderabad", "3-5 years"), job_post(4, "Pune", "5-7 years"),
                 job_post(5, "Bengaluru", "8+ years"), job_post(6, "Remote", "3-4 years")]
        self.ingest(self.cid, bulk(posts))
        self.by_company = {r["company"]: r for r in db.get_all_recruiters(self.cid)}

    def status(self, n, cfg):
        return evaluate_filters(self.by_company[f"Company{n} Learning"], cfg)[0]

    def test_07_all_cities(self):
        cfg = FilterConfig.from_settings({"cities": []})
        for n in range(1, 7):
            self.assertEqual(self.status(n, cfg), ELIGIBLE)

    def test_08_bengaluru_only(self):
        cfg = FilterConfig.from_settings({"cities": ["Bengaluru"]})
        self.assertEqual(self.status(1, cfg), ELIGIBLE)
        self.assertEqual(self.status(5, cfg), ELIGIBLE)
        for n in (2, 3, 4, 6):
            self.assertEqual(self.status(n, cfg), FILTERED_LOCATION)

    def test_09_experience_3_to_6(self):
        cfg = FilterConfig.from_settings({"exp_mode": "custom", "exp_min": 3, "exp_max": 6})
        self.assertEqual(self.status(1, cfg), ELIGIBLE)       # 3–5
        self.assertEqual(self.status(2, cfg), ELIGIBLE)       # 4–6
        self.assertEqual(self.status(4, cfg), FILTERED_EXPERIENCE)  # 5–7
        self.assertEqual(self.status(5, cfg), FILTERED_EXPERIENCE)  # 8+
        bucket = FilterConfig.from_settings({"exp_mode": "8+ years"})
        self.assertEqual(self.status(5, bucket), ELIGIBLE)
        self.assertEqual(self.status(1, bucket), FILTERED_EXPERIENCE)

    def test_10_combined(self):
        cfg = FilterConfig.from_settings({"cities": ["Bengaluru", "Chennai"], "exp_mode": "custom",
                                          "exp_min": 3, "exp_max": 6})
        self.assertEqual(self.status(1, cfg), ELIGIBLE)                # Bengaluru 3–5
        self.assertEqual(self.status(2, cfg), ELIGIBLE)                # Chennai 4–6
        self.assertEqual(self.status(3, cfg), FILTERED_LOCATION)       # Hyderabad
        self.assertEqual(self.status(5, cfg), FILTERED_EXPERIENCE)     # Bengaluru 8+
        self.assertNotEqual(self.status(4, cfg), ELIGIBLE)             # Pune 5–7: both fail
        ctx = pipeline.load_context(self.cid)
        counts = pipeline.refresh_statuses(ctx, cfg)
        self.assertEqual(counts["total"], 6)
        self.assertEqual(counts["location_eligible"], 3)
        self.assertEqual(counts["ready"], 2)
        self.assertEqual(counts["filtered"], 4)

    def test_experience_parsing_variants(self):
        self.assertEqual(parse_experience("Experience: 3-5 years")[:2], (3.0, 5.0))
        self.assertEqual(parse_experience("Exp: 3 to 5 yrs")[:2], (3.0, 5.0))
        self.assertEqual(parse_experience("Minimum 4 years of experience")[:2], (4.0, None))
        self.assertEqual(parse_experience("5+ years experience in sales")[:2], (5.0, None))
        self.assertEqual(parse_experience("Freshers can apply")[:2], (0.0, 0.0))
        self.assertEqual(parse_experience("Experience: 4–6")[:2], (4.0, 6.0))
        self.assertEqual(parse_experience("no requirement mentioned")[:2], (None, None))


# ── TESTS 11-12: CTC ─────────────────────────────────────────────────────
class Test11to12CTC(TracjetTestCase):
    def test_11_current_ctc_hidden_by_default(self):
        cid = self.make_candidate(current_ctc="7.5 LPA", include_current_ctc=False)
        self.ingest(cid, JD_BD)
        r = db.get_all_recruiters(cid)[0]
        self.assertNotIn("Current CTC", r["generated_body"])
        self.assertNotIn("7.5 LPA", r["generated_body"] + r["generated_subject"])
        self.assertIn("Expected CTC: Negotiable | Availability: Immediate Joiner", r["generated_body"])
        # a manual edit that leaks the current CTC is a hard block
        db.update_record(r["id"], generated_body=r["generated_body"] + "\nCurrent CTC: 7.5 LPA")
        ev = pipeline.evaluate_record(db.get_recruiter(r["id"]), pipeline.load_context(cid), FilterConfig())
        self.assertFalse(ev["eligible"])
        self.assertTrue(any(i["code"] == "current_ctc_leak" for i in ev["issues"]))

    def test_12_current_ctc_shown_when_enabled(self):
        cid = self.make_candidate(current_ctc="7.5 LPA", include_current_ctc=True, expected_ctc="10 LPA",
                                  availability="15 days notice")
        self.ingest(cid, JD_BD)
        body = db.get_all_recruiters(cid)[0]["generated_body"]
        self.assertIn("Current CTC: 7.5 LPA | Expected CTC: 10 LPA | Availability: 15 days notice", body)
        self.assertEqual(body.count("Current CTC"), 1)

    def test_defaults(self):
        cid = cs.create_candidate("X")
        c = cs.get_candidate(cid)
        self.assertEqual(ctc_line(c), "Expected CTC: Negotiable | Availability: Immediate Joiner")


# ── TESTS 13-15: blockers ────────────────────────────────────────────────
class Test13to15SendBlockers(TracjetTestCase):
    def test_13_no_recruiter_email_cannot_send(self):
        cid = self.make_candidate()
        self.ingest(cid, bulk([job_post(1, email=False), job_post(2)]))
        recs = db.get_all_recruiters(cid)
        self.assertEqual(len(recs), 2, "job without email stays visible")
        sender = FakeSender()
        summary = send_eligible(cid, FilterConfig(), sender_fn=sender, delay=0)
        self.assertEqual(len(sender.calls), 1)
        self.assertEqual(sender.calls[0]["to"], "recruiter2@company2.test")
        no_mail = next(r for r in db.get_all_recruiters(cid) if not r["email"])
        self.assertNotEqual(no_mail["status"], "Sent")
        self.assertEqual(no_mail["quality_status"], "Needs Review")
        self.assertTrue(summary["skipped"])

    def test_14_no_resume_cannot_send(self):
        cid = self.make_candidate()
        self.ingest(cid, JD_BD)
        os.remove(cs.get_candidate(cid)["resume_path"])
        sender = FakeSender()
        summary = send_eligible(cid, FilterConfig(), sender_fn=sender, delay=0)
        self.assertEqual(sender.calls, [])
        self.assertIn("not ready", summary["error"].lower())

    def test_15_gmail_not_connected_cannot_send(self):
        cid = self.make_candidate(connect=False)
        self.ingest(cid, JD_BD)
        sender = FakeSender()
        summary = send_eligible(cid, FilterConfig(), sender_fn=sender, delay=0)
        self.assertEqual(sender.calls, [])
        self.assertIn("gmail", summary["error"].lower())


# ── TEST 16 ──────────────────────────────────────────────────────────────
class Test16PoorTemplate(TracjetTestCase):
    def test_poor_template_match_needs_review(self):
        cid = self.make_candidate()
        jd = ("Hiring: Head Chef\nCompany: Spice Route Hotels\nLocation: Bengaluru\nExperience: 3-5 years\n"
              "Responsibilities:\n- Plan menus and supervise kitchen staff\n- Maintain food hygiene standards\n"
              "Email: chef.jobs@spiceroute.test")
        self.ingest(cid, jd)
        r = db.get_all_recruiters(cid)[0]
        ev = pipeline.evaluate_record(r, pipeline.load_context(cid), FilterConfig())
        self.assertLess(r["template_match_score"], 45)
        self.assertEqual(ev["quality_status"], "Needs Review")
        self.assertTrue(any(i["code"] == "template_poor" for i in ev["issues"]))
        self.assertFalse(ev["eligible"])
        sender = FakeSender()
        send_eligible(cid, FilterConfig(), sender_fn=sender, delay=0)
        self.assertEqual(sender.calls, [])

    def test_manual_approval_only_overrides_soft_issues(self):
        cid = self.make_candidate()
        self.ingest(cid, JD_PY)  # low candidate match → soft issue
        r = db.get_all_recruiters(cid)[0]
        ctx = pipeline.load_context(cid)
        self.assertEqual(pipeline.evaluate_record(r, ctx, FilterConfig())["quality_status"], "Needs Review")
        db.update_record(r["id"], review_approved=1)
        ev = pipeline.evaluate_record(db.get_recruiter(r["id"]), ctx, FilterConfig())
        self.assertEqual(ev["quality_status"], "Ready (Approved)")
        db.update_record(r["id"], generated_body=r["generated_body"].replace("Dear", "Dear [Recruiter Name]"))
        ev = pipeline.evaluate_record(db.get_recruiter(r["id"]), ctx, FilterConfig())
        self.assertEqual(ev["quality_status"], "Needs Review")  # placeholder is a hard issue


# ── TEST 17 ──────────────────────────────────────────────────────────────
class Test17NoInventedSkills(TracjetTestCase):
    def test_skills_not_in_resume_are_never_written(self):
        cid = self.make_candidate()  # BD candidate: no Python, Spark, Kafka...
        self.ingest(cid, JD_PY)
        r = db.get_all_recruiters(cid)[0]
        body = r["generated_body"] + r["generated_subject"]
        for skill in ("Python", "Spark", "Airflow", "Snowflake", "Kafka", "React"):
            self.assertNotIn(skill, body.replace("Python Data Engineer", ""))
        self.assertIn("Python", r["missing_skills"])  # reported to the user, not claimed
        issues = pipeline.evaluate_record(r, pipeline.load_context(cid), FilterConfig())["issues"]
        self.assertFalse([i for i in issues if i["code"] in ("invented_skill", "invented_number")])

    def test_example_draft_facts_are_not_copied(self):
        # The BD example says "5 years of Python experience" and names "Globex Corp"
        cid = self.make_candidate()
        self.ingest(cid, JD_BD)
        body = db.get_all_recruiters(cid)[0]["generated_body"]
        self.assertNotIn("Python", body)
        self.assertNotIn("Globex", body)
        self.assertNotIn("5 years", body)
        self.assertIn("4.9+ years", body)

    def test_quality_flags_invented_skill_and_number(self):
        cid = self.make_candidate()
        self.ingest(cid, JD_BD)
        r = db.get_all_recruiters(cid)[0]
        db.update_record(r["id"], generated_body=r["generated_body"].replace(
            "Kind Regards", "I also know Kubernetes and grew revenue by 300%.\n\nKind Regards"))
        codes = {i["code"] for i in pipeline.evaluate_record(db.get_recruiter(r["id"]), pipeline.load_context(cid),
                                                              FilterConfig())["issues"]}
        self.assertIn("invented_skill", codes)
        self.assertIn("invented_number", codes)


# ── TEST 18 ──────────────────────────────────────────────────────────────
class Test18Bulk(TracjetTestCase):
    def test_bulk_paste_20_jobs(self):
        cid = self.make_candidate()
        cities = ["Bengaluru", "Chennai", "Hyderabad", "Pune", "Mumbai"]
        res = self.ingest(cid, bulk([job_post(i, cities[i % 5]) for i in range(20)]))
        self.assertEqual(res["parsed"], 20)
        recs = db.get_all_recruiters(cid)
        self.assertEqual(len(recs), 20)
        self.assertEqual(len({r["email"] for r in recs}), 20)
        self.assertTrue(all(r["status"] == "Generated" for r in recs))
        # pasting the same jobs again does not duplicate
        self.ingest(cid, bulk([job_post(i, cities[i % 5]) for i in range(20)]))
        self.assertEqual(len(db.get_all_recruiters(cid)), 20)

    def test_split_formats(self):
        chunks, explicit = split_bulk_posts(bulk(["a" * 40, "b" * 40, "c" * 40]))
        self.assertTrue(explicit)
        self.assertEqual(len(chunks), 3)
        chunks, explicit = split_bulk_posts("Feed post\nX hiring a@b.test\nFeed post\nY hiring c@d.test")
        self.assertFalse(explicit)
        self.assertEqual(len(chunks), 2)


# ── TEST 19 ──────────────────────────────────────────────────────────────
class Test19SendOnlyEligible(TracjetTestCase):
    def test_10_eligible_5_filtered_2_review(self):
        cid = self.make_candidate()
        posts = [job_post(i, "Bengaluru") for i in range(10)]
        posts += [job_post(100 + i, "Hyderabad") for i in range(5)]
        posts += [job_post(200 + i, "Bengaluru") for i in range(2)]
        self.ingest(cid, bulk(posts))
        for r in db.get_all_recruiters(cid):
            if r["email"].startswith("recruiter20"):
                db.update_record(r["id"], generated_body=r["generated_body"].replace(
                    "Dear Hiring Team", "Dear [Recruiter Name]"))
        cfg = FilterConfig.from_settings({"cities": ["Bengaluru"]})
        counts = pipeline.refresh_statuses(pipeline.load_context(cid), cfg)
        self.assertEqual((counts["ready"], counts["filtered"], counts["needs_review"]), (10, 5, 2))
        sender = FakeSender()
        summary = send_eligible(cid, cfg, sender_fn=sender, delay=0)
        self.assertEqual(summary["sent"], 10)
        self.assertEqual(len(sender.calls), 10)
        sent_to = {c["to"] for c in sender.calls}
        self.assertEqual(sent_to, {f"recruiter{i}@company{i}.test" for i in range(10)})
        recs = db.get_all_recruiters(cid)
        self.assertEqual(sum(r["status"] == "Sent" for r in recs), 10)
        self.assertTrue(all(r["sent_at"] and r["sent_from"] for r in recs if r["status"] == "Sent"))
        logs = db.get_logs()
        self.assertTrue(all(l["template_name"] and l["job_title"] for l in logs if l["status"] == "Sent"))
        # a second click sends nothing new
        sender2 = FakeSender()
        send_eligible(cid, cfg, sender_fn=sender2, delay=0)
        self.assertEqual(sender2.calls, [])

    def test_filters_rechecked_at_send_time(self):
        cid = self.make_candidate()
        self.ingest(cid, bulk([job_post(1, "Bengaluru"), job_post(2, "Chennai")]))
        pipeline.refresh_statuses(pipeline.load_context(cid), FilterConfig())  # all eligible, persisted
        sender = FakeSender()
        send_eligible(cid, FilterConfig.from_settings({"cities": ["Chennai"]}), sender_fn=sender, delay=0)
        self.assertEqual([c["to"] for c in sender.calls], ["recruiter2@company2.test"])

    def test_failure_continues_with_others(self):
        cid = self.make_candidate()
        self.ingest(cid, bulk([job_post(1), job_post(2), job_post(3)]))
        sender = FakeSender(fail_for={"recruiter2@company2.test"})
        summary = send_eligible(cid, FilterConfig(), sender_fn=sender, delay=0)
        self.assertEqual((summary["sent"], summary["failed"]), (2, 1))
        failed = [r for r in db.get_all_recruiters(cid) if r["status"] == "Failed"]
        self.assertEqual(len(failed), 1)
        retry = FakeSender()
        send_eligible(cid, FilterConfig(), only_statuses={"Failed"}, sender_fn=retry, delay=0)
        self.assertEqual([c["to"] for c in retry.calls], ["recruiter2@company2.test"])


# ── TEST 20 ──────────────────────────────────────────────────────────────
class Test20Attachment(TracjetTestCase):
    def test_correct_candidate_resume_and_gmail(self):
        a = self.make_candidate()
        b = self.make_candidate(resume_text=DEV_RESUME, name="Ravi Kumar", gmail="ravi.sender.test@gmail.com",
                                phone="+91 98888 22222")
        self.ingest(a, bulk([job_post(1), job_post(2)]))
        self.ingest(b, JD_FSD)
        sa, sb = FakeSender(), FakeSender()
        send_eligible(a, FilterConfig(), sender_fn=sa, delay=0)
        send_eligible(b, FilterConfig(), sender_fn=sb, delay=0)
        a_resume, b_resume = cs.get_candidate(a)["resume_path"], cs.get_candidate(b)["resume_path"]
        self.assertEqual(len(sa.calls), 2)
        self.assertEqual(len(sb.calls), 1)
        for c in sa.calls:
            self.assertEqual(c["attachments"], [a_resume])
            self.assertEqual(c["sender"], "asha.sender.test@gmail.com")
            self.assertIn("Asha Raman", c["body"])
        self.assertEqual(sb.calls[0]["attachments"], [b_resume])
        self.assertEqual(sb.calls[0]["sender"], "ravi.sender.test@gmail.com")
        self.assertIn("Ravi Kumar", sb.calls[0]["body"])
        self.assertNotIn("Asha", sb.calls[0]["body"])
        self.assertTrue(os.path.basename(a_resume).startswith("Asha_Raman_Resume"))

    def test_mime_message_contains_resume(self):
        cid = self.make_candidate(fmt="pdf")
        path = cs.get_candidate(cid)["resume_path"]
        msg = gmail_smtp.build_email("a@gmail.com", "r@x.test", "S", "B", "plain", [path])
        names = [p.get_filename() for p in msg.walk() if p.get_filename()]
        self.assertEqual(names, ["Asha_Raman_Resume.pdf"])


# ── Email content rules ──────────────────────────────────────────────────
class TestEmailContent(TracjetTestCase):
    def test_structure_highlights_and_closing(self):
        cid = self.make_candidate()
        self.ingest(cid, bulk([JD_BD, JD_TL]))
        bd, tl = self.record_for(cid, "Business Development"), self.record_for(cid, "Team Lead")
        for r in (bd, tl):
            body = r["generated_body"]
            hl = json.loads(r["highlights"])
            self.assertEqual(len(hl), HIGHLIGHT_COUNT)
            self.assertIn(CLOSING_SENTENCE, body)
            self.assertIn("Kind Regards,\nAsha Raman\n+91 90000 11111", body)
            self.assertNotRegex(body, r"\[[^\]]+\]")
            ev = pipeline.evaluate_record(r, pipeline.load_context(cid), FilterConfig())
            self.assertEqual(ev["quality_status"], "Ready", ev["issues"])
        self.assertTrue(bd["generated_body"].startswith("Dear Neha Kapoor,"))
        self.assertTrue(tl["generated_body"].startswith("Dear Arjun Mehta,"))
        self.assertIn("Orbit EdTech", bd["generated_body"])
        self.assertNotEqual({h["text"] for h in json.loads(bd["highlights"])},
                            {h["text"] for h in json.loads(tl["highlights"])}, "highlights must follow the JD")
        self.assertIn("Business Development Manager", bd["generated_subject"])

    def test_hiring_team_when_no_recruiter_name(self):
        cid = self.make_candidate()
        self.ingest(cid, job_post(7))
        self.assertTrue(db.get_all_recruiters(cid)[0]["generated_body"].startswith("Dear Hiring Team,"))

    def test_no_phone_is_not_invented(self):
        cid = self.make_candidate(phone="")
        cs.update_candidate(cid, {"phone": ""})
        self.ingest(cid, job_post(8))
        body = db.get_all_recruiters(cid)[0]["generated_body"]
        self.assertIn("Kind Regards,\nAsha Raman\n\nExpected CTC", body)
        self.assertFalse(cs.readiness(cs.get_candidate(cid))["ready"])


# ── Migration ────────────────────────────────────────────────────────────
class TestMigration(unittest.TestCase):
    def test_legacy_unique_email_schema_is_migrated(self):
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "legacy.db")
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE recruiters (id INTEGER PRIMARY KEY AUTOINCREMENT, recruiter_name TEXT, "
                     "company TEXT, email TEXT UNIQUE, job_title TEXT, location TEXT, experience TEXT, "
                     "skills_required TEXT, jd TEXT, status TEXT DEFAULT 'Pending', created_at TEXT)")
        conn.execute("INSERT INTO recruiters (email, company, status) VALUES ('a@x.test', 'X', 'Sent')")
        conn.execute("CREATE TABLE logs (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, time TEXT, recipient TEXT, "
                     "company TEXT, subject TEXT, status TEXT, error_message TEXT)")
        conn.commit()
        conn.close()
        old = db.DB_FILE
        db.DB_FILE = path
        try:
            db.init_db()
            db.init_db()  # idempotent
            rows = db.get_all_recruiters()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["status"], "Sent")
            # same email for a different job is now allowed
            db.insert_recruiter({"email": "a@x.test", "job_title": "Other", "candidate_id": 1})
            self.assertEqual(len(db.get_all_recruiters()), 2)
        finally:
            db.DB_FILE = old
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()


# ── Per-template resumes (one resume per job category) ──────────────────
class TestTemplateResumes(TracjetTestCase):
    def upload_template_resume(self, cid, slot, text, fname):
        path = os.path.join(self.tmp, fname)
        build_docx(text, path)
        return cs.store_template_resume(cid, slot, path)

    def test_each_template_attaches_its_own_resume(self):
        cid = self.make_candidate()
        for slot in (1, 2):  # software / full-stack categories get the developer resume
            self.upload_template_resume(cid, slot, DEV_RESUME, "Asha_Dev_Resume.docx")
        self.ingest(cid, bulk([JD_FSD, JD_BD]))
        fsd, bd = self.record_for(cid, "Full Stack"), self.record_for(cid, "Business Development")
        self.assertIn(fsd["template_name"], ("Software Engineer", "Full Stack Developer"))
        self.assertEqual(bd["template_name"], "Business Development")
        self.assertRegex(fsd["generated_body"], r"React|Node")  # facts come from the template's resume
        sender = FakeSender()
        send_eligible(cid, FilterConfig(), sender_fn=sender, delay=0)
        sent = {c["to"]: c["attachments"] for c in sender.calls}
        self.assertEqual([os.path.basename(p) for p in sent[fsd["email"]]], ["Asha_Dev_Resume.docx"])
        self.assertEqual(sent[bd["email"]], [cs.get_candidate(cid)["resume_path"]])

    def test_template_resumes_alone_make_candidate_ready(self):
        cid = self.make_candidate()
        os.remove(cs.get_candidate(cid)["resume_path"])
        self.assertFalse(cs.readiness(cs.get_candidate(cid))["ready"])
        for t in TEMPLATES:
            self.upload_template_resume(cid, t["slot"], BD_RESUME, f"Asha_{t['slot']}.docx")
        self.assertTrue(cs.readiness(cs.get_candidate(cid))["ready"])
        cs.remove_template_resume(cid, 3)
        self.assertFalse(cs.readiness(cs.get_candidate(cid))["ready"])
