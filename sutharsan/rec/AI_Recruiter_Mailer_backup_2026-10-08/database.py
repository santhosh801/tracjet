import sqlite3
from datetime import datetime

DB_FILE = "recruiter_data.db"


def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS recruiters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recruiter_name TEXT,
            company TEXT,
            email TEXT UNIQUE,
            job_title TEXT,
            location TEXT,
            experience TEXT,
            skills_required TEXT,
            jd TEXT,
            category TEXT,
            match_percentage INTEGER,
            matched_skills TEXT,
            missing_skills TEXT,
            recommendation TEXT,
            generated_subject TEXT,
            generated_body TEXT,
            status TEXT DEFAULT 'Pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Automatically add missing columns if upgrading database
    cursor = conn.execute("PRAGMA table_info(recruiters)")
    existing_cols = [row['name'] for row in cursor.fetchall()]
    
    expected_cols = {
        "category": "TEXT",
        "match_percentage": "INTEGER",
        "matched_skills": "TEXT",
        "missing_skills": "TEXT",
        "recommendation": "TEXT",
        "generated_subject": "TEXT",
        "generated_body": "TEXT",
        "status": "TEXT DEFAULT 'Pending'",
        "created_at": "TEXT"
    }
    
    for col, col_type in expected_cols.items():
        if col not in existing_cols:
            try:
                conn.execute(f"ALTER TABLE recruiters ADD COLUMN {col} {col_type}")
            except Exception as e:
                print(f"Migration error for {col}: {e}")
                
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
    conn.commit()
    conn.close()


def get_all_recruiters():
    conn = get_db()
    rows = conn.execute('SELECT * FROM recruiters ORDER BY id DESC').fetchall()
    conn.close()
    return [dict(r) for r in rows]


def insert_recruiter(data):
    conn = get_db()
    inserted_id = None
    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO recruiters 
            (recruiter_name, company, email, job_title, location, experience, skills_required, jd, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data.get('recruiter_name', ''), data.get('company', ''), data.get('email', ''),
            data.get('job_title', ''), data.get('location', ''), data.get('experience', ''),
            data.get('skills_required', ''), data.get('jd', ''), 'Pending'
        ))
        conn.commit()
        if cursor.rowcount > 0:
            inserted_id = cursor.lastrowid
        else:
            row = conn.execute('SELECT id FROM recruiters WHERE email=?', (data.get('email', ''),)).fetchone()
            if row:
                inserted_id = row['id']
    except Exception as e:
        print(f"Insert error: {e}")
    finally:
        conn.close()
    return inserted_id


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


def delete_all_recruiters():
    conn = get_db()
    conn.execute('DELETE FROM recruiters')
    conn.commit()
    conn.close()


def log_event(recipient, company, subject, status, error_message=""):
    conn = get_db()
    now = datetime.now()
    conn.execute('''
        INSERT INTO logs (date, time, recipient, company, subject, status, error_message)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), recipient, company, subject, status, error_message))
    conn.commit()
    conn.close()


def get_logs():
    conn = get_db()
    rows = conn.execute('SELECT * FROM logs ORDER BY id DESC').fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_report():
    conn = get_db()
    c = conn.cursor
    total = conn.execute('SELECT COUNT(*) FROM recruiters').fetchone()[0]
    sent = conn.execute("SELECT COUNT(*) FROM recruiters WHERE status='Sent'").fetchone()[0]
    failed = conn.execute("SELECT COUNT(*) FROM recruiters WHERE status='Failed'").fetchone()[0]
    generated = conn.execute("SELECT COUNT(*) FROM recruiters WHERE status='Generated'").fetchone()[0]
    pending = conn.execute("SELECT COUNT(*) FROM recruiters WHERE status='Pending'").fetchone()[0]
    sending = conn.execute("SELECT COUNT(*) FROM recruiters WHERE status='Sending'").fetchone()[0]
    
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


def insert_recruiters_bulk(data_list):
    conn = get_db()
    inserted_ids = []
    try:
        cursor = conn.cursor()
        for data in data_list:
            cursor.execute('''
                INSERT OR IGNORE INTO recruiters 
                (recruiter_name, company, email, job_title, location, experience, skills_required, jd, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                data.get('recruiter_name', ''), data.get('company', ''), data.get('email', ''),
                data.get('job_title', ''), data.get('location', ''), data.get('experience', ''),
                data.get('skills_required', ''), data.get('jd', ''), 'Pending'
            ))
            if cursor.rowcount > 0:
                inserted_ids.append(cursor.lastrowid)
            else:
                row = conn.execute('SELECT id FROM recruiters WHERE email=?', (data.get('email', ''),)).fetchone()
                if row:
                    inserted_ids.append(row['id'])
        conn.commit()
    except Exception as e:
        print(f"Bulk insert error: {e}")
    finally:
        conn.close()
    return inserted_ids


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
