"""
device_manager.py
لایه‌ی ذخیره‌سازی رمزنگاری‌شده‌ی اطلاعات دستگاه‌ها (سوییچ‌ها)

از یک پسورد master برای مشتق کردن کلید رمزنگاری استفاده می‌شود (با
PBKDF2HMAC روی SHA-256، ۳۹۰٬۰۰۰ تکرار - مقدار توصیه‌شده‌ی فعلی OWASP).
فایل نمک (salt) به‌صورت جدا و متن‌باز ذخیره می‌شود (این کار استاندارد و
بی‌خطر است - نمک محرمانه نیست، فقط باید یکتا و ثابت بماند).

پیش‌نیاز نصب:
    pip install cryptography
"""

import os
import json
import base64
import getpass

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

import audit_log
import app_paths


BASE_DIR = app_paths.get_app_dir(__file__)
DEVICES_FILE = os.path.join(BASE_DIR, "devices.enc")
SALT_FILE = os.path.join(BASE_DIR, "devices.salt")
PBKDF2_ITERATIONS = 390_000


# ---------------------------------------------------------------------------
# رمزنگاری / رمزگشایی
# ---------------------------------------------------------------------------
def _get_or_create_salt() -> bytes:
    if os.path.exists(SALT_FILE):
        with open(SALT_FILE, "rb") as f:
            return f.read()
    salt = os.urandom(16)
    with open(SALT_FILE, "wb") as f:
        f.write(salt)
    return salt


def _derive_key(master_password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    return base64.urlsafe_b64encode(kdf.derive(master_password.encode("utf-8")))


def load_devices(master_password: str) -> list:
    """
    لیست دستگاه‌ها را رمزگشایی و برمی‌گرداند. اگر فایلی وجود نداشته باشد
    (اولین اجرا)، لیست خالی برمی‌گرداند. اگر پسورد master اشتباه باشد،
    ValueError می‌دهد.
    """
    if not os.path.exists(DEVICES_FILE):
        return []

    salt = _get_or_create_salt()
    key = _derive_key(master_password, salt)
    fernet = Fernet(key)

    with open(DEVICES_FILE, "rb") as f:
        encrypted = f.read()

    try:
        decrypted = fernet.decrypt(encrypted)
    except InvalidToken:
        audit_log.log_event(
            "MASTER_PW_FAILURE",
            "Wrong master password or corrupted device file",
            level="WARNING",
        )
        raise ValueError("Wrong master password, or the device file is corrupted.")

    audit_log.log_event("MASTER_PW_SUCCESS", "Device list decrypted successfully")
    return json.loads(decrypted.decode("utf-8"))


def save_devices(devices: list, master_password: str) -> None:
    salt = _get_or_create_salt()
    key = _derive_key(master_password, salt)
    fernet = Fernet(key)

    data = json.dumps(devices, ensure_ascii=False, indent=2).encode("utf-8")
    encrypted = fernet.encrypt(data)

    with open(DEVICES_FILE, "wb") as f:
        f.write(encrypted)


# ---------------------------------------------------------------------------
# عملیات CLI روی دستگاه‌ها
# ---------------------------------------------------------------------------
def is_cisco_device_type(device_type: str) -> bool:
    """
    طبق قرارداد نام‌گذاری netmiko، تمام درایورهای سیسکو با 'cisco_' شروع
    می‌شوند (cisco_ios, cisco_xe, cisco_nxos, cisco_asa, ...). این تابع
    برای تشخیص اینکه آیا باید مسیر بک‌آپ اختصاصی سیسکو (show
    running-config + پاک‌سازی) استفاده شود یا مسیر عمومی (دستور دلخواه
    کاربر) استفاده می‌شود.
    """
    return device_type.strip().lower().startswith("cisco_")


def _print_non_cisco_backup_explanation() -> None:
    print(
        "\n--- About automatic backup for non-Cisco devices ---\n"
        "This tool connects to the device over SSH and sends exactly ONE\n"
        "command (the one you provide below). Whatever text the device\n"
        "prints back in that same SSH session is saved as the backup file -\n"
        "the same mechanism already used for Cisco devices with\n"
        "'show running-config'.\n"
        "\n"
        "Requirements for the command you provide:\n"
        "  - It must PRINT the configuration as plain text directly in the\n"
        "    SSH session (e.g. 'show running-config', '/export',\n"
        "    'show configuration').\n"
        "  - It must NOT be a command that pushes/uploads a file to a\n"
        "    TFTP/FTP/SCP server. This tool has no file-transfer server\n"
        "    built in, so it cannot receive a file sent that way - only\n"
        "    text printed back in the SSH session is captured.\n"
        "\n"
        "Examples of commands that work well with this mechanism:\n"
        "  - Mikrotik RouterOS  : /export\n"
        "  - HP / Aruba ProCurve: show running-config\n"
        "  - Juniper JunOS      : show configuration\n"
        "  - Arista EOS         : show running-config\n"
        "\n"
        "Optional: if this device's CLI paginates long output (shows\n"
        "'--More--' and waits for a keypress), you can also provide a\n"
        "command that disables paging first (e.g. Juniper: 'set cli\n"
        "screen-length 0'). It is sent once, right before the backup\n"
        "command, and its own output is discarded. Leave empty if your\n"
        "device doesn't need this.\n"
    )


def _prompt_non_cisco_backup_settings(current_command: str = "", current_disable_paging: str = "") -> tuple[bool, str, str]:
    """
    گفت‌وگوی مشترک برای add و edit: توضیح مکانیزم را چاپ می‌کند، می‌پرسد
    آیا کاربر بک‌آپ خودکار برای این دستگاه غیر سیسکو می‌خواهد، و اگر
    بله، دستور بک‌آپ (اجباری) و دستور غیرفعال‌سازی صفحه‌بندی (اختیاری)
    را می‌گیرد.

    برمی‌گرداند: (enabled, backup_command, disable_paging_command)
    اگر کاربر منصرف شود، 'n' بزند، یا هر لحظه Ctrl+C بزند: (False, "", "")
    - Ctrl+C اینجا (و نه در جای دیگر برنامه) قرار است کاربر را از این
      گفت‌وگوی خاص بیرون بیاورد، نه کل برنامه را ببندد؛ پس صراحتاً
      KeyboardInterrupt را می‌گیریم.
    """
    try:
        _print_non_cisco_backup_explanation()
        prompt_suffix = " (y/n)"
        if current_command:
            prompt_suffix += " [currently enabled]"
        answer = input(f"Enable automatic backup for this device?{prompt_suffix}: ").strip().lower()
        if answer != "y":
            return False, "", ""

        while True:
            default_hint = f" [{current_command}]" if current_command else ""
            backup_command = input(
                f"Backup command (output of this command becomes the backup){default_hint}: "
            ).strip()
            if not backup_command:
                backup_command = current_command
            if backup_command:
                break
            print("A backup command is required to enable automatic backup. Try again, or press Ctrl+C to cancel.")

        default_paging_hint = f" [{current_disable_paging}]" if current_disable_paging else ""
        disable_paging_command = input(
            f"Command to disable pagination first (optional, leave empty if not needed){default_paging_hint}: "
        ).strip()
        if not disable_paging_command:
            disable_paging_command = current_disable_paging

        return True, backup_command, disable_paging_command

    except KeyboardInterrupt:
        print("\nCancelled - automatic backup was not enabled for this device.")
        return False, "", ""



def _parse_ssh_port(value: str) -> int | None:
    """
    ورودی پورت SSH را اعتبارسنجی می‌کند - باید عددی صحیح و در بازه‌ی
    مجاز پورت‌های TCP (۱ تا ۶۵۵۳۵) باشد. اگر نامعتبر بود None برمی‌گرداند.
    """
    try:
        port = int(value.strip())
    except ValueError:
        return None
    if 1 <= port <= 65535:
        return port
    return None


def add_device_interactive(devices: list) -> None:
    print("\n--- Add new device ---")
    name = input("Device name/label (e.g. 'Core-SW'): ").strip()
    host = input("IP address: ").strip()
    username = input("Username: ").strip()
    password = getpass.getpass("Password: ")
    secret = getpass.getpass("Enable secret (leave empty if none): ")
    device_type = input("Device type [cisco_ios]: ").strip() or "cisco_ios"

    port_input = input("SSH port [22]: ").strip()
    if port_input:
        port = _parse_ssh_port(port_input)
        if port is None:
            print("Invalid port, using default 22.")
            port = 22
    else:
        port = 22

    is_core_answer = input("Is this the core/L3 switch (has the VLAN gateways/SVIs)? (y/n): ").strip().lower()
    is_core = is_core_answer == "y"

    backup_command = ""
    disable_paging_command = ""
    if is_cisco_device_type(device_type):
        auto_backup_answer = input("Include this device in scheduled auto-backup? (y/n): ").strip().lower()
        auto_backup = auto_backup_answer == "y"
    else:
        auto_backup, backup_command, disable_paging_command = _prompt_non_cisco_backup_settings()

    devices.append(
        {
            "name": name,
            "device_type": device_type,
            "host": host,
            "username": username,
            "password": password,
            "secret": secret,
            "port": port,
            "timeout": 10,
            "is_core": is_core,
            "auto_backup": auto_backup,
            "backup_command": backup_command,
            "disable_paging_command": disable_paging_command,
        }
    )
    audit_log.log_event(
        "DEVICE_ADDED",
        f"name={name} host={host} port={port} type={device_type} is_core={is_core} auto_backup={auto_backup}",
    )
    print(f"Device '{name}' added{' (marked as core)' if is_core else ''}.")




def edit_device_interactive(devices: list) -> None:
    list_devices_cli(devices)
    if not devices:
        return
    choice = input("Enter the number of the device to edit: ").strip()
    if not (choice.isdigit() and 1 <= int(choice) <= len(devices)):
        print("Invalid selection.")
        return

    d = devices[int(choice) - 1]
    original_name = d["name"]
    changed_fields = []
    print(f"\n--- Editing '{d['name']}' (press Enter to keep current value) ---")

    new_name = input(f"Device name/label [{d['name']}]: ").strip()
    if new_name:
        d["name"] = new_name
        changed_fields.append("name")

    new_host = input(f"IP address [{d['host']}]: ").strip()
    if new_host:
        d["host"] = new_host
        changed_fields.append("host")

    current_port = d.get("port", 22)
    new_port_input = input(f"SSH port [{current_port}]: ").strip()
    if new_port_input:
        new_port = _parse_ssh_port(new_port_input)
        if new_port is not None:
            d["port"] = new_port
            changed_fields.append("port")
        else:
            print(f"Invalid port, keeping existing value ({current_port}).")

    new_username = input(f"Username [{d['username']}]: ").strip()
    if new_username:
        d["username"] = new_username
        changed_fields.append("username")

    new_password = getpass.getpass("Password (leave empty to keep current): ")
    if new_password:
        d["password"] = new_password
        changed_fields.append("password")  # فقط اسم فیلد، هرگز مقدار

    new_secret = getpass.getpass("Enable secret (leave empty to keep current): ")
    if new_secret:
        d["secret"] = new_secret
        changed_fields.append("secret")  # فقط اسم فیلد، هرگز مقدار

    was_cisco = is_cisco_device_type(d["device_type"])
    new_device_type = input(f"Device type [{d['device_type']}]: ").strip()
    if new_device_type:
        d["device_type"] = new_device_type
        changed_fields.append("device_type")
    is_cisco_now = is_cisco_device_type(d["device_type"])

    current_core = "y" if d.get("is_core") else "n"
    new_is_core = input(f"Is this the core/L3 switch? (y/n) [{current_core}]: ").strip().lower()
    if new_is_core in ("y", "n"):
        d["is_core"] = new_is_core == "y"
        changed_fields.append("is_core")

    if is_cisco_now:
        if was_cisco != is_cisco_now and d.get("backup_command"):
            print(
                "Device type changed to a Cisco type - the previously saved "
                "custom backup command is no longer used (Cisco devices use "
                "'show running-config' automatically). Clearing it."
            )
        d["backup_command"] = ""
        d["disable_paging_command"] = ""
        current_auto_backup = "y" if d.get("auto_backup") else "n"
        new_auto_backup = input(f"Include in scheduled auto-backup? (y/n) [{current_auto_backup}]: ").strip().lower()
        if new_auto_backup in ("y", "n"):
            d["auto_backup"] = new_auto_backup == "y"
            changed_fields.append("auto_backup")
    else:
        if was_cisco != is_cisco_now:
            print("Device type changed to a non-Cisco type - let's set up its backup command.")
        change_backup = input(
            "Change the automatic backup settings for this device? (y/n) [n]: "
        ).strip().lower()
        if change_backup == "y":
            enabled, backup_command, disable_paging_command = _prompt_non_cisco_backup_settings(
                current_command=d.get("backup_command", ""),
                current_disable_paging=d.get("disable_paging_command", ""),
            )
            d["auto_backup"] = enabled
            d["backup_command"] = backup_command
            d["disable_paging_command"] = disable_paging_command
            changed_fields.append("auto_backup/backup_command")

    if changed_fields:
        audit_log.log_event(
            "DEVICE_EDITED",
            f"device={original_name} host={d['host']} changed_fields={','.join(changed_fields)}",
        )
    print(f"Device '{d['name']}' updated.")


def get_core_device(devices: list) -> dict | None:
    """
    اولین دستگاهی که با is_core=True علامت خورده را برمی‌گرداند (دیکشنری
    آماده برای netmiko، بدون فیلدهای UI-only مثل 'name'، 'is_core' و
    'auto_backup')، یا None اگر هیچ‌کدام core نباشند.
    """
    for d in devices:
        if d.get("is_core"):
            return to_connection_params(d)
    return None


def list_devices_cli(devices: list) -> None:
    if not devices:
        print("No devices stored yet.")
        return
    print("\n--- Stored devices ---")
    for i, d in enumerate(devices, start=1):
        core_tag = " [CORE]" if d.get("is_core") else ""
        backup_tag = " [AUTO-BACKUP]" if d.get("auto_backup") else ""
        custom_tag = " [CUSTOM-BACKUP-CMD]" if d.get("backup_command") else ""
        port = d.get("port", 22)
        port_suffix = f":{port}" if port != 22 else ""
        print(f"{i}. {d['name']} ({d['host']}{port_suffix}) - type: {d['device_type']}{core_tag}{backup_tag}{custom_tag}")



def list_auto_backup_devices_cli(devices: list) -> None:
    auto_devices = [d for d in devices if d.get("auto_backup")]
    if not auto_devices:
        print("No devices are configured for scheduled auto-backup.")
        return
    print("\n--- Auto-backup devices ---")
    for i, d in enumerate(auto_devices, start=1):
        core_tag = " [CORE]" if d.get("is_core") else ""
        print(f"{i}. {d['name']} ({d['host']}) - type: {d['device_type']}{core_tag} [AUTO-BACKUP]")


def configure_auto_backup_devices_interactive(devices: list) -> None:
    if not devices:
        print("No devices stored yet. Add a device first.")
        return

    print("\n--- Configure scheduled auto-backup devices ---")
    print("For each device, choose whether it should be included in scheduled auto-backup.")
    for d in devices:
        current = "y" if d.get("auto_backup") else "n"
        prompt = f"Include '{d['name']}' ({d['host']}) in scheduled auto-backup? (y/n) [{current}]: "
        answer = input(prompt).strip().lower()
        if answer == "y":
            if not is_cisco_device_type(d["device_type"]) and not d.get("backup_command"):
                print(f"'{d['name']}' is a non-Cisco device with no backup command configured yet.")
                enabled, backup_command, disable_paging_command = _prompt_non_cisco_backup_settings()
                d["auto_backup"] = enabled
                d["backup_command"] = backup_command
                d["disable_paging_command"] = disable_paging_command
            else:
                d["auto_backup"] = True
        elif answer == "n":
            d["auto_backup"] = False
        else:
            print("Keeping current setting.")
    print("Device auto-backup assignment updated.")


def remove_device_interactive(devices: list) -> None:
    list_devices_cli(devices)
    if not devices:
        return
    choice = input("Enter the number of the device to remove: ").strip()
    if choice.isdigit() and 1 <= int(choice) <= len(devices):
        removed = devices.pop(int(choice) - 1)
        audit_log.log_event(
            "DEVICE_REMOVED",
            f"name={removed['name']} host={removed['host']}",
            level="WARNING",
        )
        print(f"Removed '{removed['name']}'.")
    else:
        print("Invalid selection.")


def select_device_raw(devices: list) -> dict | None:
    """
    مثل select_device ولی رکورد کامل (شامل 'name' و 'is_core') را برمی‌گرداند
    - برای جاهایی که لازم است بدانیم دستگاه انتخابی core هست یا نه.
    """
    list_devices_cli(devices)
    if not devices:
        return None
    choice = input("Enter the number of the device: ").strip()
    if choice.isdigit() and 1 <= int(choice) <= len(devices):
        return dict(devices[int(choice) - 1])
    print("Invalid selection.")
    return None


def to_connection_params(device: dict) -> dict:
    """رکورد خام یک دستگاه را به دیکشنری آماده برای netmiko تبدیل می‌کند."""
    clean = dict(device)
    for key in ("name", "is_core", "auto_backup", "backup_command", "disable_paging_command"):
        clean.pop(key, None)
    return clean
