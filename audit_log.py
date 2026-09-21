"""
audit_log.py
لاگ امنیتی (security audit trail)

رویدادهای حساس امنیتی - تلاش ورود با پسورد master، افزودن/ویرایش/حذف
دستگاه، اجرای بک‌آپ (موفق/ناموفق)، شناسایی تغییر غیرمنتظره‌ی کانفیگ
(config drift)، فعال/غیرفعال‌سازی اجرای بدون‌تعامل (unattended startup)،
و تلاش‌های ناموفق اتصال به دستگاه‌ها - در یک فایل جدا و همیشگی (persistent)
ثبت می‌شوند تا در صورت بروز مشکل امنیتی (مثلاً یک تغییر کانفیگ ناخواسته،
یا چند تلاش ناموفق ورود پشت‌سرهم) بشود دقیقاً فهمید چه زمانی و چه اتفاقی
افتاده.

چرا یک ماژول جدا از لاگ عملیاتی عادی برنامه؟
  1. باید حتی وقتی برنامه به‌صورت headless (بدون کنسول، مثلاً از طریق
     Windows Task Scheduler) اجرا می‌شود هم رویدادها روی دیسک بمانند -
     نه فقط چاپ در کنسولی که کسی نمی‌بیندش.
  2. فرمت یکدست و قابل grep/parse (هر خط با یک برچسب ثابت شروع می‌شود،
     مثل DEVICE_ADDED یا MASTER_PW_FAILURE) - جدا از پیام‌های عملیاتی
     متفرقه - تا بشود بعداً راحت فیلترش کرد یا به یک SIEM وصلش کرد.
  3. چرخش خودکار فایل (rotation) دارد تا با گذشت زمان بی‌نهایت بزرگ نشود.

⚠️ قانون طلایی این ماژول: هرگز پسورد، enable secret، یا پسورد master را
اینجا ثبت نکن - همیشه فقط نام/IP/یوزرنیم دستگاه و شرح رویداد. کدهایی که
از این ماژول استفاده می‌کنند باید قبل از فراخوانی مطمئن شوند مقدار
حساسی داخل detail نمی‌فرستند.

پیش‌نیاز نصب: چیزی اضافه‌تر لازم نیست (فقط کتابخانه‌ی استاندارد logging).
"""

import os
import logging
from logging.handlers import RotatingFileHandler

import app_paths

BASE_DIR = app_paths.get_app_dir(__file__)
AUDIT_LOG_FILE = os.path.join(BASE_DIR, "security_audit.log")

_audit_logger = logging.getLogger("cisco_mgmt.audit")

if not _audit_logger.handlers:
    _handler = RotatingFileHandler(
        AUDIT_LOG_FILE,
        maxBytes=5 * 1024 * 1024,  # 5MB
        backupCount=5,             # security_audit.log.1 .. .5
        encoding="utf-8",
    )
    _formatter = logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s")
    _handler.setFormatter(_formatter)
    _audit_logger.addHandler(_handler)
    _audit_logger.setLevel(logging.INFO)
    # این لاگر جداست و نباید هم‌زمان رو کنسول هم چاپ بشه (کنسول کار
    # لاگر عملیاتی خود برنامه‌ست) - propagate=False این را تضمین می‌کند.
    _audit_logger.propagate = False


def log_event(event_type: str, detail: str = "", level: str = "INFO") -> None:
    """
    یک رویداد امنیتی را با فرمت یکدست ثبت می‌کند.

    event_type: یک برچسب کوتاه و ثابت با حروف بزرگ و زیرخط، مثل
                'DEVICE_ADDED', 'AUTH_FAILURE', 'MASTER_PW_FAILURE' -
                تا بشود بعداً با grep دنبال یک نوع رویداد خاص گشت.
    detail:     شرح انسان‌خوان رویداد - نام/IP/یوزرنیم دستگاه و مانند
                آن. هرگز پسورد/secret اینجا قرار نگیرد.
    level:      INFO (پیش‌فرض) / WARNING / ERROR / CRITICAL
    """
    message = f"{event_type} - {detail}" if detail else event_type
    level = level.upper()
    if level == "WARNING":
        _audit_logger.warning(message)
    elif level == "ERROR":
        _audit_logger.error(message)
    elif level == "CRITICAL":
        _audit_logger.critical(message)
    else:
        _audit_logger.info(message)
