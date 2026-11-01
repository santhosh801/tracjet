import json
import os

SETTINGS_FILE = "settings.json"

DEFAULT_SETTINGS = {
    "theme": "Dark",
    "openai_api_key": "",
    "gmail_email": "san0thosh08@gmail.com",
    "gmail_app_password": "",
    "resume_path": "",
    "signature": "Best regards,\nSanthosh B\nAI Full Stack Product Engineer\nBengaluru | Immediate Joiner",
    "max_daily_emails": 50,
    "delay_between_emails": 3,
    "retry_count": 3,
}


def load_settings():
    if not os.path.exists(SETTINGS_FILE):
        save_settings(DEFAULT_SETTINGS)
        return DEFAULT_SETTINGS.copy()
    with open(SETTINGS_FILE, "r") as f:
        try:
            data = json.load(f)
            # Merge defaults for any missing keys
            for k, v in DEFAULT_SETTINGS.items():
                if k not in data:
                    data[k] = v
            return data
        except Exception:
            return DEFAULT_SETTINGS.copy()


def save_settings(settings):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=4)
