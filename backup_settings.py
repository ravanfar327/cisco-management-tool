"""
backup_settings.py
تنظیمات عمومی بک‌آپ خودکار: فاصله‌ی زمانی، تعداد نگه‌داشت، و مسیر ذخیره‌سازی

این تنظیمات به‌صورت متن‌ساده (JSON) ذخیره می‌شوند - برخلاف devices.enc که
رمزنگاری‌شده است - چون هیچ اطلاعات حساسی (پسورد و ...) اینجا نیست، فقط
چند عدد و یک مسیر پوشه.

پیش‌نیاز نصب:
    pip install apscheduler
"""

import json
import os

import app_paths

BASE_DIR = app_paths.get_app_dir(__file__)
SETTINGS_FILE = os.path.join(BASE_DIR, "backup_settings.json")

DEFAULT_SETTINGS = {
    "schedule_type": "daily",
    "schedule_time": "00:00",
    "schedule_day_of_week": "mon",
    "schedule_day_of_month": 1,
    "retention_count": 10,
    "backup_path": os.path.join(BASE_DIR, "backups"),
}


def load_settings() -> dict:
    if not os.path.exists(SETTINGS_FILE):
        return dict(DEFAULT_SETTINGS)

    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    # اگر تنظیمات ذخیره‌شده ناقص بود (مثلاً بعد از یک آپدیت کد)، مقادیر
    # پیش‌فرض جای خالی‌ها را پر می‌کنند
    merged = dict(DEFAULT_SETTINGS)
    merged.update(data)

    backup_path = merged.get("backup_path")
    if backup_path:
        if not os.path.isabs(backup_path):
            backup_path = os.path.join(BASE_DIR, backup_path)
        merged["backup_path"] = os.path.abspath(backup_path)

    return merged


def save_settings(settings: dict) -> None:
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


def _parse_time(value: str) -> str | None:
    try:
        hours, minutes = value.split(":")
        hours = int(hours)
        minutes = int(minutes)
        if 0 <= hours < 24 and 0 <= minutes < 60:
            return f"{hours:02d}:{minutes:02d}"
    except ValueError:
        return None
    return None


def _parse_schedule_type(value: str) -> str | None:
    normalized = value.strip().lower()
    aliases = {
        "daily": "daily",
        "d": "daily",
        "weekly": "weekly",
        "w": "weekly",
        "monthly": "monthly",
        "m": "monthly",
    }
    return aliases.get(normalized)


def _parse_day_of_week(value: str) -> str | None:
    normalized = value.strip().lower()
    aliases = {
        "monday": "mon",
        "mon": "mon",
        "tuesday": "tue",
        "tue": "tue",
        "wednesday": "wed",
        "wed": "wed",
        "thursday": "thu",
        "thu": "thu",
        "friday": "fri",
        "fri": "fri",
        "saturday": "sat",
        "sat": "sat",
        "sunday": "sun",
        "sun": "sun",
    }
    if normalized in aliases:
        return aliases[normalized]
    if normalized.isdigit():
        index = int(normalized) - 1
        if 0 <= index < 7:
            return ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][index]
    return None


def _parse_day_of_month(value: str) -> int | None:
    try:
        day = int(value)
        if 1 <= day <= 28:
            return day
    except ValueError:
        return None
    return None


def configure_settings_interactive() -> dict:
    settings = load_settings()
    print("\n--- Scheduled auto-backup settings ---")

    print("Current settings:")
    print(f"  Schedule type: {settings['schedule_type']}")
    print(f"  Schedule time: {settings['schedule_time']}")
    if settings["schedule_type"] == "weekly":
        print(f"  Day of week: {settings['schedule_day_of_week']}")
    if settings["schedule_type"] == "monthly":
        print(f"  Day of month: {settings['schedule_day_of_month']}")
    print(f"  Backups to keep: {settings['retention_count']}")
    print(f"  Backup path: {settings['backup_path']}")

    print("\nSchedule types: daily, weekly, monthly (you can also just type d, w, or m)")
    new_type_raw = input(f"Schedule type [{settings['schedule_type']}]: ").strip()
    if new_type_raw:
        parsed_type = _parse_schedule_type(new_type_raw)
        if parsed_type:
            settings["schedule_type"] = parsed_type
        else:
            print("Invalid schedule type, keeping existing value.")

    new_time = input(f"Schedule time (HH:MM) [{settings['schedule_time']}]: ").strip()
    if new_time:
        parsed_time = _parse_time(new_time)
        if parsed_time:
            settings["schedule_time"] = parsed_time
        else:
            print("Invalid time format, keeping existing schedule time.")

    if settings["schedule_type"] == "weekly":
        new_weekday = input(
            f"Day of week for backup [{settings['schedule_day_of_week']}]: "
        ).strip()
        if new_weekday:
            parsed_weekday = _parse_day_of_week(new_weekday)
            if parsed_weekday:
                settings["schedule_day_of_week"] = parsed_weekday
            else:
                print("Invalid weekday, keeping existing day of week.")

    if settings["schedule_type"] == "monthly":
        new_dom = input(
            f"Day of month for backup (1-28) [{settings['schedule_day_of_month']}]: "
        ).strip()
        if new_dom:
            parsed_dom = _parse_day_of_month(new_dom)
            if parsed_dom is not None:
                settings["schedule_day_of_month"] = parsed_dom
            else:
                print("Invalid day of month, keeping existing value.")

    new_retention = input(f"Number of backups to keep per device [{settings['retention_count']}]: ").strip()
    if new_retention.isdigit() and int(new_retention) > 0:
        settings["retention_count"] = int(new_retention)

    new_path = input(f"Backup storage path [{settings['backup_path']}]: ").strip()
    if new_path:
        settings["backup_path"] = new_path

    save_settings(settings)
    print("Settings saved.")
    return settings