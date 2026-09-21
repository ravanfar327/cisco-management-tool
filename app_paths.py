"""
app_paths.py
مسیر «پوشه‌ی کنار برنامه» را برمی‌گرداند - چه برنامه به‌صورت اسکریپت
پایتون اجرا شود، چه با PyInstaller به یک exe مستقل تبدیل شده باشد.

چرا این ماژول لازم است: وقتی با PyInstaller (به‌خصوص با --onefile) یک
exe ساخته می‌شود، مقدار __file__ داخل هر ماژول در زمان اجرا به یک
پوشه‌ی موقت داخل sys._MEIPASS اشاره می‌کند - نه به کنار خود فایل exe.
اگر فایل‌های داده‌ی برنامه (devices.enc، پوشه‌ی backups، لاگ‌ها،
تنظیمات و ...) بر همین مبنا ساخته شوند، هر بار که برنامه بسته می‌شود
آن پوشه‌ی موقت حذف می‌شود و همه‌چیز (بک‌آپ‌ها، پسورد master، تنظیمات)
گم می‌شود. این تابع همیشه پوشه‌ی واقعی و پایدار کنار exe/اسکریپت را
برمی‌گرداند تا این مشکل پیش نیاید.

استفاده - هر ماژولی که قبلاً این‌طور بود:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

باید به این تغییر کند:
    import app_paths
    BASE_DIR = app_paths.get_app_dir(__file__)
"""

import os
import sys


def get_app_dir(module_file: str) -> str:
    """
    module_file: همیشه __file__ خود ماژول فراخوان (نه app_paths.py) -
    چون وقتی frozen نباشیم، باید مسیر کنار همان ماژول را برگردانیم.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(module_file))
