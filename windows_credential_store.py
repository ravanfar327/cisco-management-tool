"""
windows_credential_store.py
ذخیره‌ی امن پسورد master برای اجرای بدون تعامل (headless / unattended) -
مثلاً وقتی برنامه از طریق Windows Task Scheduler در استارتاپ سیستم اجرا
می‌شود و کسی پشت کیبورد نیست تا پسورد master را وارد کند.

از Windows Data Protection API (DPAPI) استفاده می‌کند - همان مکانیزمی که
مرورگرها و بسیاری از اپ‌های ویندوزی برای پسوردهای ذخیره‌شده استفاده
می‌کنند. رمزنگاری به‌صورت خودکار به همان اکانت ویندوز کاربر جاری (روی
همان ماشین) گره می‌خورد؛ یعنی حتی اگر فایل رمزنگاری‌شده کپی و روی
سیستم/کاربر دیگری اجرا شود، قابل رمزگشایی نیست. پسورد هیچ‌وقت به‌صورت
متن ساده روی دیسک نوشته نمی‌شود.

نکته‌ی امنیتی مهم (باید به کاربر نهایی هم گفته شود): این مکانیزم اعتماد
رو از «کسی که پسورد master رو می‌دونه» منتقل می‌کنه به «کسی که می‌تونه
با این اکانت ویندوز کد اجرا کنه». یعنی امنیت لیست دستگاه‌ها (که شامل
پسورد سوییچ‌هاست) بعد از فعال‌سازی این حالت، هم‌تراز امنیت خود اکانت
ویندوزیه که برنامه زیرش اجرا می‌شه.

پیش‌نیاز نصب (فقط روی ویندوز، فقط اگر از این قابلیت استفاده می‌کنی):
    pip install pywin32
"""

import os
import sys

STORE_FILE_NAME = "master_password.dpapi"


def _store_path(base_dir: str) -> str:
    return os.path.join(base_dir, STORE_FILE_NAME)


def is_available() -> bool:
    """
    True فقط وقتی هم روی ویندوز باشیم و هم pywin32 نصب باشد. جاهای دیگر
    کد باید همیشه قبل از فراخوانی توابع این ماژول این را چک کنند.
    """
    if sys.platform != "win32":
        return False
    try:
        import win32crypt  # noqa: F401
        return True
    except ImportError:
        return False


def has_saved_password(base_dir: str) -> bool:
    return os.path.exists(_store_path(base_dir))


def save_master_password(master_password: str, base_dir: str) -> None:
    """
    پسورد master را با DPAPI رمزنگاری و در یک فایل محلی ذخیره می‌کند.
    فقط قابل فراخوانی روی ویندوز (وقتی is_available() برابر True باشد).
    """
    import win32crypt

    blob = win32crypt.CryptProtectData(
        master_password.encode("utf-8"),
        "cisco_mgmt master password",  # توضیح/برچسب، نه بخشی از رمزنگاری
        None,
        None,
        None,
        0,
    )
    with open(_store_path(base_dir), "wb") as f:
        f.write(blob)


def load_master_password(base_dir: str) -> str | None:
    """
    پسورد master ذخیره‌شده را رمزگشایی می‌کند. اگر فایلی وجود نداشته
    باشد، یا رمزگشایی (مثلاً چون فایل روی اکانت/ماشین دیگری کپی شده)
    شکست بخورد، None برمی‌گرداند - هرگز استثنا پرتاب نمی‌کند تا حالت
    headless بدون کرش، پیام خطای واضح بدهد.
    """
    import win32crypt

    path = _store_path(base_dir)
    if not os.path.exists(path):
        return None

    with open(path, "rb") as f:
        blob = f.read()

    try:
        _, decrypted = win32crypt.CryptUnprotectData(blob, None, None, None, 0)
    except Exception:
        return None

    return decrypted.decode("utf-8")


def remove_saved_master_password(base_dir: str) -> None:
    path = _store_path(base_dir)
    if os.path.exists(path):
        os.remove(path)
