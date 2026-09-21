"""
gui_app.py
نقطه‌ی ورود رابط گرافیکی (GUI). این فایل کنار cisco_mgmt.py قرار می‌گیرد
و از همان ماژول‌های بک‌اند (device_manager, backup_settings, audit_log,
cisco_mgmt) استفاده می‌کند - هیچ منطقی اینجا بازنویسی نشده است.

اجرا:
    python gui_app.py

پیش‌نیاز نصب (علاوه بر پیش‌نیازهای خود پروژه):
    pip install PySide6
"""

import sys
import os

# اطمینان از این‌که پوشه‌ی خود این فایل (جایی که cisco_mgmt.py و بقیه‌ی
# ماژول‌های بک‌اند هستند) در sys.path باشد - چه با 'python gui_app.py'
# از یک پوشه‌ی دیگر اجرا شود، چه بعداً با PyInstaller به exe تبدیل شود.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication

from gui_theme import build_stylesheet
from gui_dialogs import UnlockDialog
from gui_main_window import MainWindow
import audit_log
import gui_preferences


def main() -> None:
    app = QApplication(sys.argv)
    preferences = gui_preferences.load_preferences()
    app.setStyleSheet(build_stylesheet(preferences.get("theme", "dark")))
    app.setApplicationName("Cisco Switch Management Tool")

    audit_log.log_event("APP_START", "GUI session started")

    unlock_dialog = UnlockDialog()
    if unlock_dialog.exec() != UnlockDialog.DialogCode.Accepted:
        # سه تلاش ناموفق یا انصراف کاربر - دقیقاً مثل رفتار CLI، بدون
        # نمایش پنجره‌ی اصلی خارج می‌شویم.
        sys.exit(0)

    window = MainWindow(unlock_dialog.devices, unlock_dialog.master_password, app)
    window.show()

    exit_code = app.exec()
    audit_log.log_event("APP_EXIT", "GUI session ended")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
