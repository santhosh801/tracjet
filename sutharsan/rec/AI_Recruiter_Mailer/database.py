import json
import sqlite3
from datetime import datetime, timedelta

DB_FILE = "recruiter_data.db"

# Columns of the recruiters (job/email records) table, in order.
RECRUITER_COLUMNS = {
    "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
    "recruiter_name": "TEXT",
    "company": "TEXT",
    "email": "TEXT",
    "job_title": "TEXT",
    "location": "TEXT",
    "experience": "TEXT",
    "skills_required": "TEXT",
    "jd": "TEXT",
    "category": "TEXT",
    "match_percentage": "INTEGER",
    "matched_skills": "TEXT",
    "missing_skills": "TEXT",
    "recommendation": "TEXT",
    "generated_subject": "TEXT",
    "generated_body": "TEXT",
    "status": "TEXT DEFAULT 'Pending'",
    "created_at": "TEXT DEFAULT CURRENT_TIMESTAMP",
    # ── candidate platform columns ──
    "candidate_id": "INTEGER",
    "dedupe_key": "TEXT",
    "location_cities": "TEXT",
    "exp_min": "REAL",
    "exp_max": "REAL",
    "seniority": "TEXT",
    "jd_analysis": "TEXT",
    "template_id": "INTEGER",
    "template_name": "TEXT",
    "template_scores": "TEXT",
    "template_reason": "TEXT",
    "template_match_score": "INTEGER",
    "candidate_match": "TEXT",
    "highlights": "TEXT",
    "uses_bullets": "INTEGER DEFAULT 1",
    "generation_mode": "TEXT",
    "filter_status": "TEXT",
    "quality_status": "TEXT",
    "quality_issues": "TEXT",
    "review_approved": "INTEGER DEFAULT 0",
    "sent_at": "TEXT",
    "sent_from": "TEXT",
    "attachment_name": "TEXT",
}

LOG_COLUMNS = {
    "candidate_id": "INTEGER", "job_title": "TEXT", "template_name": "TEXT",
    "sender": "TEXT", "attachment": "TEXT", "recruiter_name": "TEXT", "record_id": "INTEGER",
}

# Each template slot can carry its own resume (attached + used for facts when that template is chosen).
TEMPLATE_RESUME_COLUMNS = {
    "resume_path": "TEXT", "resume_original_name": "TEXT", "resume_text": "TEXT", "profile_json": "TEXT",
    "resume_analyzed_at": "TEXT",
}

UPDATABLE = set(RECRUITER_COLUMNS) - {"id", "created_at"}


def get_db():
    conn = sqlite3.connect(DB_FILE, timeout=15)
    conn.row_factory = sqlite3.Row
    return conn


def _create_recruiters_sql(name="recruiters"):
    cols = ",\n".join(f"{c} {t}" for c, t in RECRUITER_COLUMNS.items())
    return f"CREATE TABLE IF NOT EXISTS {name} (\n{cols}\n)"


def _migrate_recruiters(conn):
    """
    Older databases declared `email TEXT UNIQUE`, which blocks the same recruiter
    email for a different job or a different candidate.  Rebuild the table
    without that constraint, keeping every existing row.
    """
    row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='recruiters'").fetchone()
    if row is None:
        conn.execute(_create_recruiters_sql())
    elif "UNIQUE" in (row["sql"] or "").upper():
        old_cols = [r["name"] for r in conn.execute("PRAGMA table_info(recruiters)").fetchall()]
        conn.execute("DROP TABLE IF EXISTS recruiters_new")
        conn.execute(_create_recruiters_sql("recruiters_new"))
        cols = ", ".join(c for c in old_cols if c in RECRUITER_COLUMNS)
        conn.execute(f"INSERT INTO recruiters_new ({cols}) SELECT {cols} FROM recruiters")
        conn.execute("DROP TABLE recruiters")
        conn.execute("ALTER TABLE recruiters_new RENAME TO recruiters")
    existing_cols = [r["name"] for r in conn.execute("PRAGMA table_info(recruiters)").fetchall()]
    for col, col_type in RECRUITER_COLUMNS.items():
        if col not in existing_cols:
            try:
                conn.execute(f"ALTER TABLE recruiters ADD COLUMN {col} {col_type.replace('PRIMARY KEY AUTOINCREMENT', '')}")
            except Exception as e:
                print(f"Migration error for {col}: {e}")
    conn.execute("UPDATE recruiters SET dedupe_key = lower(email) WHERE dedupe_key IS NULL AND email IS NOT NULL")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_recruiters_candidate_dedupe "
                 "ON recruiters(candidate_id, dedupe_key)")


def init_db():
    conn = get_db()
    c = conn.cursor()
    _migrate_recruiters(conn)
    c.execute('''
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            time TEXT,
            recipient TEXT,
            company TEXT,
            subject TEXT,
            status TEXT,
            error_message TEXT
        )
    ''')
    log_cols = [r["name"] for r in conn.execute("PRAGMA table_info(logs)").fetchall()]
    for col, col_type in LOG_COLUMNS.items():
        if col not in log_cols:
            conn.execute(f"ALTER TABLE logs ADD COLUMN {col} {col_type}")
    c.execute('''
        CREATE TABLE IF NOT EXISTS candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, email TEXT, phone TEXT,
            gmail_address TEXT, gmail_app_password_enc TEXT,
            gmail_verified INTEGER DEFAULT 0, gmail_verified_at TEXT, gmail_fingerprint TEXT,
            resume_path TEXT, resume_original_name TEXT, resume_text TEXT,
            profile_json TEXT, profile_status TEXT DEFAULT 'none', resume_analyzed_at TEXT,
            expected_ctc TEXT DEFAULT 'Negotiable', availability TEXT DEFAULT 'Immediate Joiner',
            current_ctc TEXT, include_current_ctc INTEGER DEFAULT 0,
            extra_signature TEXT, drafting_instructions TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id INTEGER NOT NULL,
            slot INTEGER NOT NULL,
            name TEXT, role_category TEXT, example_subject TEXT, example_body TEXT,
            updated_at TEXT,
            UNIQUE(candidate_id, slot)
        )
    ''')
    tpl_cols = [r["name"] for r in conn.execute("PRAGMA table_info(templates)").fetchall()]
    for col, col_type in TEMPLATE_RESUME_COLUMNS.items():
        if col not in tpl_cols:
            conn.execute(f"ALTER TABLE templates ADD COLUMN {col} {col_type}")
    conn.commit()
    conn.close()


def dedupe_key_for(data: dict) -> str:
    email = (data.get("email") or "").strip().lower()
    title = " ".join((data.get("job_title") or "").lower().split())
    if email:
        return f"{email}|{title}"
    import hashlib
    return "jd:" + hashlib.sha1((data.get("jd") or "").strip().lower().encode("utf-8")).hexdigest()[:16]


def get_all_recruiters(candidate_id=None):
    conn = get_db()
    if candidate_id is None:
        rows = conn.execute('SELECT * FROM recruiters ORDER BY id DESC').fetchall()
    else:
        rows = conn.execute('SELECT * FROM recruiters WHERE candidate_id=? ORDER BY id DESC', (candidate_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_recruiter(rid):
    conn = get_db()
    row = conn.execute('SELECT * FROM recruiters WHERE id=?', (rid,)).fetchone()
    conn.close()
    return dict(row) if row else None


def _insert_one(conn, data):
    cursor = conn.cursor()
    fields = {k: v for k, v in data.items() if k in UPDATABLE}
    fields.setdefault("status", "Pending")
    fields["dedupe_key"] = data.get("dedupe_key") or dedupe_key_for(data)
    for k, v in list(fields.items()):
        if isinstance(v, (list, dict)):
            fields[k] = json.dumps(v, ensure_ascii=False)
    cols = ", ".join(fields)
    marks = ", ".join("?" for _ in fields)
    cursor.execute(f"INSERT OR IGNORE INTO recruiters ({cols}) VALUES ({marks})", list(fields.values()))
    if cursor.rowcount > 0:
        return cursor.lastrowid, True
    if data.get("candidate_id") is not None:
        row = conn.execute('SELECT id FROM recruiters WHERE candidate_id=? AND dedupe_key=?',
                           (data.get("candidate_id"), fields["dedupe_key"])).fetchone()
    else:
        row = conn.execute('SELECT id FROM recruiters WHERE candidate_id IS NULL AND email=?',
                           (data.get('email', ''),)).fetchone()
    return (row['id'] if row else None), False


def insert_recruiter(data):
    conn = get_db()
    inserted_id = None
    try:
        inserted_id, _ = _insert_one(conn, data)
        conn.commit()
    except Exception as e:
        print(f"Insert error: {e}")
    finally:
        conn.close()
    return inserted_id


def insert_recruiters_bulk(data_list, return_new_flags=False):
    conn = get_db()
    inserted_ids, flags = [], []
    try:
        for data in data_list:
            rid, is_new = _insert_one(conn, data)
            if rid:
                inserted_ids.append(rid)
                flags.append(is_new)
        conn.commit()
    except Exception as e:
        print(f"Bulk insert error: {e}")
    finally:
        conn.close()
    return (inserted_ids, flags) if return_new_flags else inserted_ids


def update_record(rid, **fields):
    """Generic update for whitelisted recruiter columns (lists/dicts stored as JSON)."""
    fields = {k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v)
              for k, v in fields.items() if k in UPDATABLE}
    if not fields:
        return
    conn = get_db()
    conn.execute(f"UPDATE recruiters SET {', '.join(f'{k}=?' for k in fields)} WHERE id=?",
                 list(fields.values()) + [rid])
    conn.commit()
    conn.close()


def update_records_bulk(updates: list[tuple[int, dict]]):
    conn = get_db()
    try:
        for rid, fields in updates:
            fields = {k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v)
                      for k, v in fields.items() if k in UPDATABLE}
            if fields:
                conn.execute(f"UPDATE recruiters SET {', '.join(f'{k}=?' for k in fields)} WHERE id=?",
                             list(fields.values()) + [rid])
        conn.commit()
    finally:
        conn.close()


def update_analysis(rid, category, match_pct, matched, missing, recommendation):
    conn = get_db()
    conn.execute('''
        UPDATE recruiters SET category=?, match_percentage=?, matched_skills=?, missing_skills=?, recommendation=?
        WHERE id=?
    ''', (category, match_pct, matched, missing, recommendation, rid))
    conn.commit()
    conn.close()


def update_recruiter_details(rid, name, company, email, job_title, subject, body):
    conn = get_db()
    conn.execute('''
        UPDATE recruiters
        SET recruiter_name=?, company=?, email=?, job_title=?, generated_subject=?, generated_body=?
        WHERE id=?
    ''', (name, company, email, job_title, subject, body, rid))
    conn.commit()
    conn.close()


def update_email_content(rid, subject, body):
    conn = get_db()
    conn.execute('UPDATE recruiters SET generated_subject=?, generated_body=?, status=? WHERE id=?',
                 (subject, body, 'Generated', rid))
    conn.commit()
    conn.close()


def update_status(rid, status):
    conn = get_db()
    conn.execute('UPDATE recruiters SET status=? WHERE id=?', (status, rid))
    conn.commit()
    conn.close()


def delete_all_recruiters(candidate_id=None):
    conn = get_db()
    if candidate_id is None:
        conn.execute('DELETE FROM recruiters')
    else:
        conn.execute('DELETE FROM recruiters WHERE candidate_id=?', (candidate_id,))
    conn.commit()
    conn.close()


def log_event(recipient, company, subject, status, error_message="", candidate_id=None, job_title="",
              template_name="", sender="", attachment="", recruiter_name="", record_id=None):
    conn = get_db()
    now = datetime.now()
    conn.execute('''
        INSERT INTO logs (date, time, recipient, company, subject, status, error_message,
                          candidate_id, job_title, template_name, sender, attachment, recruiter_name, record_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), recipient, company, subject, status, error_message,
          candidate_id, job_title, template_name, sender, attachment, recruiter_name, record_id))
    conn.commit()
    conn.close()


def recently_emailed(candidate_id, days: int = 30) -> dict:
    """{lower(recipient): last sent date} for emails this candidate sent in the last `days` days."""
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    conn = get_db()
    rows = conn.execute("SELECT lower(trim(recipient)) AS r, MAX(date) AS d FROM logs WHERE status='Sent' "
                        "AND candidate_id=? AND date>=? GROUP BY lower(trim(recipient))", (candidate_id, since)).fetchall()
    conn.close()
    return {r["r"]: r["d"] for r in rows}


def get_send_history(candidate_id=None) -> list[dict]:
    """Sent / failed counts per day per candidate, newest day first."""
    conn = get_db()
    where, args = ("WHERE l.candidate_id=?", (candidate_id,)) if candidate_id is not None else ("", ())
    rows = conn.execute(f'''
        SELECT l.date, l.candidate_id, COALESCE(c.name, 'Unknown') AS name,
               SUM(l.status='Sent') AS sent, SUM(l.status='Failed') AS failed
        FROM logs l LEFT JOIN candidates c ON c.id = l.candidate_id
        {where}
        GROUP BY l.date, l.candidate_id
        ORDER BY l.date DESC, name
    ''', args).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_today_sent_by_candidate() -> list[dict]:
    today = datetime.now().strftime("%Y-%m-%d")
    return [r for r in get_send_history() if r["date"] == today and r["sent"]]


def get_logs():
    conn = get_db()
    rows = conn.execute('SELECT * FROM logs ORDER BY id DESC').fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_report(candidate_id=None):
    conn = get_db()
    where, args = ("WHERE candidate_id=?", (candidate_id,)) if candidate_id is not None else ("", ())
    and_ = "AND" if where else "WHERE"

    def count(cond=""):
        return conn.execute(f"SELECT COUNT(*) FROM recruiters {where} {(and_ + ' ' + cond) if cond else ''}",
                            args).fetchone()[0]

    total = count()
    sent = count("status='Sent'")
    failed = count("status='Failed'")
    generated = count("status='Generated'")
    pending = count("status='Pending'")
    sending = count("status='Sending'")

    from datetime import timedelta
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    week_ago_str = (now - timedelta(days=7)).strftime("%Y-%m-%d")

    today_sent = conn.execute("SELECT COUNT(*) FROM logs WHERE status='Sent' AND date=?", (today_str,)).fetchone()[0]
    weekly_sent = conn.execute("SELECT COUNT(*) FROM logs WHERE status='Sent' AND date>=?", (week_ago_str,)).fetchone()[0]

    conn.close()
    return {
        "total": total, "sent": sent, "failed": failed,
        "generated": generated, "pending": pending, "sending": sending,
        "today_sent": today_sent, "weekly_sent": weekly_sent
    }


def get_sent_history():
    conn = get_db()
    rows = conn.execute('''
        SELECT date, COUNT(*) as count
        FROM logs
        WHERE status='Sent'
        GROUP BY date
        ORDER BY date DESC
    ''').fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_sent_logs_by_date(date_str):
    conn = get_db()
    rows = conn.execute('''
        SELECT time, recipient, company, subject
        FROM logs
        WHERE status='Sent' AND date=?
        ORDER BY time DESC
    ''', (date_str,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_emails_bulk(updates_list):
    conn = get_db()
    try:
        conn.executemany('''
            UPDATE recruiters SET generated_subject=?, generated_body=?, status=? WHERE id=?
        ''', [(u['subject'], u['body'], 'Generated', u['id']) for u in updates_list])
        conn.commit()
    except Exception as e:
        print(f"Bulk email update error: {e}")
    finally:
        conn.close()
