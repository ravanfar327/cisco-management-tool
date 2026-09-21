"""
gui_preferences.py
تنظیمات مخصوص خود رابط گرافیکی (نه بک‌اند عملیاتی) - فعلاً فقط انتخاب
تم (dark/light). عمداً در یک فایل JSON جدا از backup_settings.json
ذخیره می‌شود، چون این یک ترجیح UI است، نه یک پارامتر عملیاتی بک‌آپ.
"""

import json
import os

import app_paths

BASE_DIR = app_paths.get_app_dir(__file__)
PREFERENCES_FILE = os.path.join(BASE_DIR, "gui_preferences.json")

DEFAULT_PREFERENCES = {
    "theme": "dark",  # "dark" یا "light"
}


def load_preferences() -> dict:
    if not os.path.exists(PREFERENCES_FILE):
        return dict(DEFAULT_PREFERENCES)
    try:
        with open(PREFERENCES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_PREFERENCES)
    merged = dict(DEFAULT_PREFERENCES)
    merged.update(data)
    return merged


def save_preferences(preferences: dict) -> None:
    with open(PREFERENCES_FILE, "w", encoding="utf-8") as f:
        json.dump(preferences, f, ensure_ascii=False, indent=2)
