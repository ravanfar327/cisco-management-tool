"""
gui_scheduler.py
اجرای واقعی بک‌آپ خودکار در پس‌زمینه‌ی خود برنامه‌ی GUI، با
BackgroundScheduler از APScheduler - نه BlockingScheduler که CLI
استفاده می‌کند، چون آن ترد فراخواننده را کاملاً بلاک می‌کند و اگر
همان ترد UI باشد، کل رابط کاربری فریز می‌شود. BackgroundScheduler روی
ترد جدای خودش اجرا می‌شود و به Qt event loop کاری ندارد.

این scheduler فقط تا وقتی برنامه‌ی GUI باز است کار می‌کند. برای اجرای
کاملاً مستقل از باز بودن GUI (حتی بعد از بستنش)، باید از حالت headless
CLI استفاده شود ('--service' + Windows Task Scheduler، طبق توضیحات
منوی Backup در CLI) - آن یک مسیر کاملاً جدا و مستقل است.

منطق تبدیل تنظیمات (schedule_type/time/day) به پارامترهای cron، و
تابعی که واقعاً دستگاه‌ها را بک‌آپ می‌گیرد، از cisco_mgmt.py می‌آید -
اینجا فقط لایه‌ی اجراست.
"""

import logging

import cisco_mgmt

logger = logging.getLogger("cisco_mgmt")

JOB_ID = "gui_scheduled_backup"


class GuiScheduler:
    def __init__(self):
        self._scheduler = None
        self._available = False
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
        except ImportError:
            logger.warning(
                "APScheduler is not installed - scheduled auto-backup will not run "
                "from the GUI. Install it with: pip install apscheduler"
            )
            return

        self._scheduler = BackgroundScheduler()
        self._scheduler.start()
        self._available = True

    def reconfigure(self, devices: list, settings: dict) -> bool:
        """
        job قبلی (اگر بود) را حذف و با تنظیمات تازه دوباره ثبت می‌کند.
        باید هر بار که برنامه استارت می‌شود، و هر بار که کاربر تنظیمات
        زمان‌بندی را Save می‌کند، صدا زده شود.

        توجه: devices همان لیست زنده‌ای است که بقیه‌ی GUI (مثلاً
        DevicesPage) در جا تغییرش می‌دهد (append/pop/تغییر مستقیم
        index) - چون همان رفرنس به APScheduler پاس داده می‌شود، تغییر
        auto_backup هر دستگاه بدون نیاز به reconfigure دوباره، در دور
        بعدی اجرای job منعکس می‌شود (run_scheduled_backup_job هر بار
        خودش دوباره فیلتر می‌کند).

        خروجی: True یعنی موفق، False یعنی APScheduler نصب نیست یا
        تنظیمات (ساعت/روز) نامعتبر است.
        """
        if not self._available:
            return False

        cron_kwargs, error = cisco_mgmt.build_cron_trigger_kwargs(settings)
        if error:
            logger.error("Could not schedule auto-backup: %s", error)
            return False

        if self._scheduler.get_job(JOB_ID) is not None:
            self._scheduler.remove_job(JOB_ID)

        self._scheduler.add_job(
            cisco_mgmt.run_scheduled_backup_job,
            "cron",
            id=JOB_ID,
            args=[devices, settings],
            replace_existing=True,
            **cron_kwargs,
        )
        logger.info(
            "Scheduled auto-backup configured (GUI): %s",
            cisco_mgmt.describe_schedule(settings),
        )
        return True

    def clear(self) -> None:
        """
        job داخل برنامه را برمی‌دارد. وقتی بک‌آپ پس‌زمینه‌ی ویندوز (Task
        Scheduler) فعال است، این لازم است تا همان بک‌آپ در یک زمان دو بار
        (یک‌بار توسط Task و یک‌بار توسط خود GUI) اجرا نشود.
        """
        if self._available and self._scheduler.get_job(JOB_ID) is not None:
            self._scheduler.remove_job(JOB_ID)
            logger.info("In-app scheduled backup paused (Windows Task Scheduler is handling it).")

    def shutdown(self) -> None:
        if self._available and self._scheduler is not None:
            self._scheduler.shutdown(wait=False)
