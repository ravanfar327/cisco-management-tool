"""
log_bridge.py
پل بین logging استاندارد پایتون (که cisco_mgmt.py از قبل با آن کار
می‌کند) و یک ویجت GUI. توابع بک‌اند معمولاً روی یک QThread جدا اجرا
می‌شوند (تا UI فریز نشود)؛ این هندلر با استفاده از Qt Signal پیام‌ها را
thread-safe به ترد اصلی (UI) می‌رساند - نیازی نیست خود توابع بک‌اند
چیزی درباره‌ی Qt بدانند.
"""

import logging
from PySide6.QtCore import QObject, Signal


class _Bridge(QObject):
    message = Signal(str, str)  # (formatted_text, level_name)


class QtLogHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.bridge = _Bridge()
        self.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
        except Exception:
            msg = record.getMessage()
        self.bridge.message.emit(msg, record.levelname)
