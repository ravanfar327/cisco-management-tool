"""
workers.py
اجرای هر تابع بلاک‌کننده (مثل اتصال SSH یا بک‌آپ) روی یک QThread جدا.

توابع بک‌اند این پروژه (netmiko, ...) کاملاً synchronous و بلاک‌کننده‌اند.
اگر مستقیم از UI thread صدا زده شوند، کل رابط گرافیکی برای چند ثانیه
(یا در صورت timeout، تا ۳۰ ثانیه) فریز می‌شود. Worker این مشکل را حل
می‌کند: تابع را روی یک ترد جدا اجرا می‌کند و نتیجه/خطا را با signal به
ترد اصلی (UI) برمی‌گرداند - بدون این‌که خود تابع بک‌اند لازم باشد چیزی
درباره‌ی Qt بداند.
"""

from PySide6.QtCore import QThread, Signal


class Worker(QThread):
    """
    یک QThread عمومی: هر تابع پایتونی (fn) را با آرگومان‌های دلخواه روی
    ترد جدا اجرا می‌کند.

    finished_ok(object): وقتی fn بدون خطا نتیجه برگرداند
    finished_error(str): وقتی fn استثنا پرتاب کند (متن خطا)
    """

    finished_ok = Signal(object)
    finished_error = Signal(str)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def run(self) -> None:
        try:
            result = self._fn(*self._args, **self._kwargs)
        except Exception as e:  # noqa: BLE001 - هر خطای بک‌اند باید به UI برسد، نه کرش کند
            self.finished_error.emit(str(e))
            return
        self.finished_ok.emit(result)
