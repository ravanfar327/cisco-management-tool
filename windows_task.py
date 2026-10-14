"""
windows_task.py
ثبت/به‌روزرسانی/حذف یک Task در Windows Task Scheduler (با schtasks) تا بک‌آپ
زمان‌بندی‌شده حتی وقتی برنامه‌ی GUI/CLI بسته است اجرا شود.

طراحی: به‌جای یک پروسه‌ی دائمی در پس‌زمینه، خود ویندوز در زمان تعیین‌شده
برنامه را با '--run-backup-once' اجرا می‌کند؛ برنامه یک دور بک‌آپ می‌گیرد و
خارج می‌شود. زمان‌بندی (daily/weekly/monthly + ساعت + روز) از همان
تنظیمات backup_settings گرفته می‌شود و با هر Save دوباره روی Task اعمال می‌شود.

محدودیت‌های شناخته‌شده:
- Task با حساب همین کاربر ویندوز اجرا می‌شود (چون پسورد master با DPAPI
  مخصوص همین کاربر رمزنگاری شده)، یعنی در زمان اجرا کاربر باید لاگین باشد.
- اگر کامپیوتر در زمان تعیین‌شده خاموش باشد، آن دور اجرا نمی‌شود (در
  Task Scheduler می‌توان گزینه‌ی 'Run task as soon as possible after a
  scheduled start is missed' را دستی فعال کرد).
- فقط روی ویندوز کار می‌کند.
"""

import os
import shutil
import subprocess
import sys

import app_paths
import cisco_mgmt

TASK_NAME = "CiscoMgmtAutoBackup"
RUN_FLAG = "--run-backup-once"
SCHTASKS_TR_MAX_LENGTH = 261  # محدودیت خود schtasks برای طول دستور /tr

_SCHTASKS_DAYS = {"mon": "MON", "tue": "TUE", "wed": "WED", "thu": "THU", "fri": "FRI", "sat": "SAT", "sun": "SUN"}


def is_supported() -> bool:
    return sys.platform == "win32" and shutil.which("schtasks") is not None


def unavailable_reason(dpapi_available: bool) -> str | None:
    """
    اگر بک‌آپ پس‌زمینه قابل‌استفاده نیست، دلیل دقیقش را برمی‌گرداند (برای
    نمایش در UI)؛ در غیر این صورت None. dpapi_available نتیجه‌ی
    windows_credential_store.is_available() است.
    """
    if sys.platform != "win32":
        return "this feature only works on Windows."
    if shutil.which("schtasks") is None:
        return "schtasks.exe was not found on this PC."
    if not dpapi_available:
        return (
            "the 'pywin32' package is missing (pip install pywin32). If you are running a "
            "built .exe, rebuild it with --hidden-import win32crypt."
        )
    return None


def build_task_command() -> str:
    """
    دستوری که Task Scheduler اجرا می‌کند. اگر برنامه با PyInstaller به exe
    تبدیل شده باشد خود exe است؛ وگرنه pythonw.exe (بدون پنجره‌ی کنسول) +
    مسیر cisco_mgmt.py.
    """
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" {RUN_FLAG}'

    python_dir = os.path.dirname(sys.executable)
    pythonw = os.path.join(python_dir, "pythonw.exe")
    interpreter = pythonw if os.path.exists(pythonw) else sys.executable
    script = os.path.join(app_paths.get_app_dir(__file__), "cisco_mgmt.py")
    return f'"{interpreter}" "{script}" {RUN_FLAG}'


def build_schtasks_create_args(settings: dict, command: str) -> tuple[list | None, str | None]:
    """
    آرگومان‌های 'schtasks /create' را از روی settings می‌سازد (تابع خالص و
    قابل‌تست - هیچ فرایندی اجرا نمی‌کند). خروجی: (args, None) یا (None, error)
    """
    cron_kwargs, error = cisco_mgmt.build_cron_trigger_kwargs(settings)
    if error:
        return None, error
    if len(command) > SCHTASKS_TR_MAX_LENGTH:
        return None, (
            f"The program path is too long for Windows Task Scheduler "
            f"({len(command)} > {SCHTASKS_TR_MAX_LENGTH} characters). Move the application "
            f"to a shorter folder path and try again."
        )

    start_time = f"{cron_kwargs['hour']:02d}:{cron_kwargs['minute']:02d}"
    args = ["schtasks", "/create", "/tn", TASK_NAME, "/tr", command, "/st", start_time, "/f"]

    if "day_of_week" in cron_kwargs:
        args += ["/sc", "WEEKLY", "/d", _SCHTASKS_DAYS[cron_kwargs["day_of_week"]]]
    elif "day" in cron_kwargs:
        args += ["/sc", "MONTHLY", "/d", str(cron_kwargs["day"])]
    else:
        args += ["/sc", "DAILY"]
    return args, None


def _run(args: list) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def task_exists() -> bool:
    if not is_supported():
        return False
    return _run(["schtasks", "/query", "/tn", TASK_NAME]).returncode == 0


def create_or_update_task(settings: dict) -> tuple[bool, str]:
    """Task را با زمان‌بندی فعلی می‌سازد یا (اگر وجود دارد) جایگزین می‌کند."""
    if not is_supported():
        return False, "Windows Task Scheduler is only available on Windows."

    args, error = build_schtasks_create_args(settings, build_task_command())
    if error:
        return False, error

    result = _run(args)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        return False, f"schtasks failed (exit code {result.returncode}): {detail}"
    return True, f"Task '{TASK_NAME}' registered: {cisco_mgmt.describe_schedule(settings)}."


def delete_task() -> tuple[bool, str]:
    if not is_supported():
        return False, "Windows Task Scheduler is only available on Windows."
    if not task_exists():
        return True, "No scheduled task was registered."
    result = _run(["schtasks", "/delete", "/tn", TASK_NAME, "/f"])
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        return False, f"schtasks failed (exit code {result.returncode}): {detail}"
    return True, f"Task '{TASK_NAME}' removed."
