import json
import os

SETTINGS_FILE = "settings.json"

# Candidate-specific values (Gmail, App Password, resume, signature, CTC) live in the
# candidates table — nothing candidate-specific is hardcoded here.
DEFAULT_SETTINGS = {
    "theme": "Dark",
    "openai_api_key": "",
    "use_openai_drafting": False,
    "gmail_email": "",            # legacy (pre-candidate) setting, no longer used for sending
    "gmail_app_password": "",     # legacy
    "resume_path": "",            # legacy
    "signature": "",              # legacy
    "max_daily_emails": 50,
    "delay_between_emails": 3,
    "retry_count": 3,
    # Soft review notes (poor template match, missing title, …) no longer need manual approval when
    # True; hard issues such as a missing recruiter email still block sending.
    "auto_approve_soft_review": False,
    "active_candidate_id": None,
    "send_filters": {"cities": [], "exp_mode": "All Experience", "exp_min": None, "exp_max": None},
}


def load_settings():
    if not os.path.exists(SETTINGS_FILE):
        save_settings(DEFAULT_SETTINGS)
        return json.loads(json.dumps(DEFAULT_SETTINGS))
    with open(SETTINGS_FILE, "r") as f:
        try:
            data = json.load(f)
            # Merge defaults for any missing keys
            for k, v in DEFAULT_SETTINGS.items():
                if k not in data:
                    data[k] = json.loads(json.dumps(v))
            return data
        except Exception:
            return json.loads(json.dumps(DEFAULT_SETTINGS))


def save_settings(settings):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=4)
