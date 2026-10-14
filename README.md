# Cisco Switch Management Tool

A Windows-friendly Python tool for managing Cisco (and other vendor) switches: topology/IP discovery, encrypted config backup with scheduling, config drift detection, idle-port security reports, and a device inventory report — available both as a **CLI** and a full **desktop GUI**.

> Built and tested primarily against Cisco IOS/IOS-XE switches, with optional support for non-Cisco devices (Mikrotik, HP/Aruba, Juniper, Arista, ...) via a custom backup command per device.


🇮🇷 توضیحات فارسی

ابزاری مبتنی بر پایتون و مناسب ویندوز برای مدیریت سوئیچ‌های سیسکو (و سایر برندها): کشف توپولوژی و IP، پشتیبان‌گیری رمزنگاری‌شده از کانفیگ به‌همراه زمان‌بندی، تشخیص تغییرات کانفیگ (Drift)، گزارش امنیتی پورت‌های بی‌استفاده و گزارش موجودی دستگاه‌ها — هم به‌صورت CLI و هم به‌صورت یک رابط گرافیکی دسکتاپ کامل.

    این پروژه عمدتاً روی سوئیچ‌های Cisco IOS/IOS-XE ساخته و تست شده است، اما با تعریف یک دستور پشتیبان‌گیری سفارشی برای هر دستگاه، امکان پشتیبانی از دستگاه‌های غیرسیسکو (Mikrotik، HP/Aruba، Juniper، Arista و ...) هم وجود دارد.

## Features

- **Topology / IP discovery** — find which switch and physical port an IP or MAC address is connected to, by walking CDP neighbors from a core switch.
- **Encrypted device storage** — all device credentials are encrypted at rest (Fernet + PBKDF2, 390k iterations) behind a single master password.
- **Scheduled + on-demand backup** — daily/weekly/monthly auto-backup with retention, plus one-off manual backups. Non-Cisco devices use a custom backup command instead of Cisco-specific parsing.
- **Config drift detection** — diff the two most recent backups of a device (or all devices) to catch unexpected/unauthorized changes.
- **Idle ports report** — flag `notconnect` and `err-disabled` ports, plus ports that are `connected` but have shown no traffic since the last check (candidates for security hardening).
- **Device inventory report** — model, serial number, and running IOS version for every device, with a reminder to check Cisco's own site for the latest release.
- **Security audit log** — a dedicated, rotating `security_audit.log` tracks master-password attempts, device changes, backup results, config drift, and more (never logs actual passwords/secrets).
- **Unattended startup on Windows** — securely save the master password via Windows DPAPI so scheduled backups can run headlessly from Task Scheduler at boot, with no one needing to type a password.
- **Full GUI** — a PySide6 desktop app covering every feature above, with light/dark themes.

🇮🇷 ویژگی‌ها

    کشف توپولوژی / IP — با پیمایش همسایه‌های CDP از یک سوئیچ Core، مشخص می‌کند که یک IP یا MAC به کدام سوئیچ و کدام پورت فیزیکی متصل است.

    ذخیره‌سازی رمزنگاری‌شده دستگاه‌ها — تمام اطلاعات ورود دستگاه‌ها به‌صورت رمزنگاری‌شده ذخیره می‌شود (Fernet + PBKDF2 با ۳۹۰٬۰۰۰ تکرار) و با یک رمز اصلی (Master Password) محافظت می‌گردد.

    پشتیبان‌گیری زمان‌بندی‌شده و درخواستی — پشتیبان‌گیری خودکار روزانه/هفتگی/ماهانه به‌همراه سیاست نگهداری (Retention)، به‌علاوه پشتیبان‌گیری دستی. دستگاه‌های غیرسیسکو به‌جای پارس اختصاصی سیسکو از یک دستور سفارشی استفاده می‌کنند. فایل پشتیبان به گونه ای آماده و ذخیره می گردد تا فقط با یک کپی ساده بر روی سوییچ جدید نشسته و نیاز به هیچ کار اضافه ای نباشد.

    تشخیص تغییرات کانفیگ (Config Drift) — دو پشتیبان‌گیری آخر یک دستگاه (یا همه دستگاه‌ها) را با هم مقایسه می‌کند تا تغییرات غیرمنتظره یا غیرمجاز مشخص شود.

    گزارش پورت‌های بی‌استفاده — پورت‌های notconnect و err-disabled را علامت می‌زند، و همچنین پورت‌هایی که در وضعیت connected هستند اما از آخرین بررسی ترافیکی نداشته‌اند (نامزدهای سخت‌سازی امنیتی).

    گزارش موجودی دستگاه‌ها — مدل، شماره سریال و نسخه IOS در حال اجرا برای هر دستگاه، همراه با یادآوری برای بررسی سایت سیسکو جهت دریافت آخرین نسخه.

    لاگ ممیزی امنیتی — فایل چرخشی مجزای security_audit.log تلاش‌های ورود رمز اصلی، تغییرات دستگاه، نتایج پشتیبان‌گیری، تغییرات کانفیگ و موارد دیگر را ثبت می‌کند (هرگز رمز یا اطلاعات محرمانه ثبت نمی‌شود).

    راه‌اندازی خودکار در ویندوز — رمز اصلی به‌صورت امن با Windows DPAPI ذخیره می‌شود تا پشتیبان‌گیری‌های زمان‌بندی‌شده بتوانند هنگام بوت و بدون نیاز به وارد کردن رمز، از طریق Task Scheduler اجرا شوند.

    رابط گرافیکی کامل — یک اپلیکیشن دسکتاپ با PySide6 که تمام قابلیت‌های بالا را پوشش می‌دهد، همراه با تم روشن/تاریک.

## Screenshots

#Dashboard
/screenshots/dashboard.png

#ip_discovery
/screenshots/ip_discovery.png

#Login
/screenshots/Login.png

#settings
/screenshots/settings.png

## Requirements

- Python 3.11+ (Windows recommended; the CLI is cross-platform, `pywin32`-based features are Windows-only)
- See [`requirements.txt`](requirements.txt) for Python packages

Install dependencies:

```bash
pip install -r requirements.txt
```
🇮🇷 پیش‌نیازها

    پایتون 3.11 یا بالاتر (ویندوز توصیه می‌شود؛ CLI چندسکویی است و قابلیت‌های مبتنی بر pywin32 فقط در ویندوز کار می‌کنند)

    بسته‌های پایتونی موردنیاز را در فایل requirements.txt ببینید

نصب وابستگی‌ها:
bash

pip install -r requirements.txt


## Usage

### CLI

```bash
python cisco_mgmt.py
```

You'll be prompted for a master password (used to encrypt/decrypt your device list — 3 attempts before the app exits). From there, a numbered menu covers device management, backup, config drift, idle ports, inventory, and exit.

To run scheduled backups unattended (e.g. via Windows Task Scheduler), see "Backup > Enable unattended startup" in the CLI menu — it prints the exact command to register.

### GUI

```bash
python gui_app.py
```

All project files must be in the **same folder** (no subfolders) — the GUI imports the CLI's backend modules directly.

🇮🇷 روش استفاده — CLI
bash

python cisco_mgmt.py

از شما رمز اصلی خواسته می‌شود (برای رمزنگاری/رمزگشایی لیست دستگاه‌ها استفاده می‌شود — تا ۳ تلاش و سپس برنامه بسته می‌شود). پس از آن، یک منوی شماره‌دار مدیریت دستگاه‌ها، پشتیبان‌گیری، تغییرات کانفیگ، پورت‌های بی‌استفاده، موجودی و خروج را پوشش می‌دهد.

برای اجرای پشتیبان‌گیری‌های زمان‌بندی‌شده به‌صورت خودکار (مثلاً با Windows Task Scheduler)، از گزینه «Backup > Enable unattended startup» در منوی CLI استفاده کنید — دستور دقیق برای ثبت در Task Scheduler چاپ می‌شود.
GUI
bash

python gui_app.py

All project files must be in the same folder (no subfolders) — the GUI imports the CLI's backend modules directly.

🇮🇷 روش استفاده — GUI
bash

python gui_app.py

تمام فایل‌های پروژه باید در یک پوشه باشند (بدون زیرپوشه) — چون GUI مستقیماً ماژول‌های بک‌اند CLI را ایمپورت می‌کند.


## Project layout

```
cisco_mgmt.py               Core backend: topology scan, backup, drift, idle ports, inventory, CLI menu
device_manager.py           Encrypted device storage + CRUD
backup_settings.py          Scheduled backup configuration
audit_log.py                Security audit log
windows_credential_store.py DPAPI-based master password storage (Windows-only)
app_paths.py                Resolves the app's data directory correctly, script or frozen .exe
gui_scheduler.py            Background scheduler for automatic backups while the GUI is open
windows_task.py             Windows Task Scheduler integration (backups when the app is closed).
gui_app.py                  GUI entry point
gui_theme.py                Dark/light QSS stylesheet
gui_widgets.py              Custom widgets (e.g. SteppedSpinBox)
gui_workers.py              Background-thread helper for blocking SSH calls
gui_log_bridge.py           Routes backend logging into the GUI console
gui_preferences.py          GUI-only settings (theme choice)
gui_dialogs.py              Unlock screen + device add/edit dialog
gui_main_window.py          Main window, sidebar navigation
gui_pages_*.py              One file per page (Devices, Backup, Config Drift, Idle Ports,
                            Inventory, IP Discovery, Settings, Audit Log)
```

🇮🇷 ساختار پروژه
text

cisco_mgmt.py               بک‌اند اصلی: اسکن توپولوژی، پشتیبان‌گیری، Drift، پورت‌های بی‌استفاده، موجودی، منوی CLI
device_manager.py           ذخیره‌سازی رمزنگاری‌شده دستگاه‌ها + عملیات CRUD
backup_settings.py          تنظیمات پشتیبان‌گیری زمان‌بندی‌شده
audit_log.py                لاگ ممیزی امنیتی
windows_credential_store.py ذخیره‌سازی رمز اصلی با DPAPI (فقط ویندوز)
app_paths.py                تشخیص صحیح مسیر داده‌های برنامه، چه اسکریپت چه فایل اجرایی (frozen .exe)
gui_scheduler.py            زمان‌بند پس‌زمینه برای پشتیبان‌گیری خودکار تا وقتی GUI باز است
windows_task.py             یکپارچه‌سازی با Windows Task Scheduler (پشتیبان‌گیری وقتی برنامه بسته است)
gui_app.py                  نقطه ورود GUI
gui_theme.py                شیوه‌نامه (QSS) تم تاریک/روشن
gui_widgets.py              ویجت‌های سفارشی (مثلاً SteppedSpinBox)
gui_workers.py              کمک‌کننده Thread پس‌زمینه برای فراخوانی‌های مسدودکننده SSH
gui_log_bridge.py           هدایت لاگ‌های بک‌اند به کنسول GUI
gui_preferences.py          تنظیمات مخصوص GUI (انتخاب تم)
gui_dialogs.py              صفحه ورود (Unlock) + دیالوگ افزودن/ویرایش دستگاه
gui_main_window.py          پنجره اصلی، ناوبری کناری
gui_pages_*.py              یک فایل برای هر صفحه (دستگاه‌ها، پشتیبان‌گیری، تغییرات کانفیگ،
                            پورت‌های بی‌استفاده، موجودی، کشف IP، تنظیمات، لاگ ممیزی)


## Building a standalone Windows .exe

See [`BUILD.md`](BUILD.md) for step-by-step PyInstaller instructions for both the CLI and GUI.

🇮🇷 ساخت فایل اجرایی مستقل ویندوز (.exe)

برای دستورالعمل‌های گام‌به‌گام PyInstaller جهت ساخت هر دو نسخه CLI و GUI به BUILD.md مراجعه کنید.



## Security notes

- The device list (`devices.enc`) is encrypted with a key derived from your master password. **If you lose the master password, the device list cannot be recovered.**
- `security_audit.log` never contains passwords or secrets — only event types, device names/hosts, and timestamps.
- "Unattended startup" trades password-prompt security for automation: once enabled, anyone who can run code as your Windows user can decrypt the device list. Only enable it on a machine/account you control.
- Never commit `devices.enc`, `devices.salt`, `master_password.dpapi`, `backup_settings.json`, `gui_preferences.json`, or any `*.log` file to version control — see [`.gitignore`](.gitignore).

🇮🇷 نکات امنیتی

    لیست دستگاه‌ها (devices.enc) با کلیدی که از رمز اصلی شما مشتق می‌شود رمزنگاری شده است. اگر رمز اصلی را گم کنید، بازیابی لیست دستگاه‌ها امکان‌پذیر نیست.

    فایل security_audit.log هرگز شامل رمز یا اطلاعات محرمانه نیست — فقط نوع رویداد، نام/آدرس دستگاه و زمان.

    گزینه «Unattended startup» امنیت ناشی از پرسیدن رمز را با خودکارسازی معاوضه می‌کند: پس از فعال‌سازی، هر کسی که بتواند با حساب ویندوزی شما کد اجرا کند، قادر به رمزگشایی لیست دستگاه‌ها خواهد بود. این گزینه را فقط روی ماشین/حسابی که خودتان کنترل می‌کنید فعال کنید.

    هرگز فایل‌های devices.enc، devices.salt، master_password.dpapi، backup_settings.json، gui_preferences.json یا هیچ فایل *.log را در سیستم کنترل نسخه (Version Control) قرار ندهید — به .gitignore مراجعه کنید.

## License

MIT — see [`LICENSE`]. Keep this software producer name for any publishing or copying.

## Contributing

Issues and pull requests are welcome. Please avoid including real device credentials, IPs, or hostnames in any issue/PR content.

🇮🇷 مشارکت
Issue و Pull Request پذیرفته می‌شود. لطفاً از درج اطلاعات واقعی دستگاه‌ها مثل رمز عبور، IP یا نام هاست در محتوای Issue/PR خودداری کنید.