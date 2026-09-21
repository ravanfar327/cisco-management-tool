"""
switch_core.py
هسته‌ی اولیه‌ی ابزار مدیریت سوییچ سیسکو

سه قابلیت اصلی:
1. مدیریت لیست دستگاه‌ها (افزودن/حذف/انتخاب) با ذخیره‌سازی رمزنگاری‌شده
   (از طریق device_manager.py)
2. نمایش IP هایی که در لحظه از هر پورت فیزیکی سرویس می‌گیرند - با walk کردن
   کل توپولوژی شبکه (از سوییچ انتخاب‌شده شروع می‌شود، از روی CDP سوییچ‌های
   پایین‌دستی متصل به پورت‌های trunk را پیدا و به آن‌ها هم وصل می‌شود،
   تا پورت فیزیکی واقعی روی هر سوییچی که باشد پیدا شود - نه فقط یک لایه)
3. بک‌آپ گرفتن از کانفیگ سوییچ (فعلاً فقط سوییچ seed انتخاب‌شده) و
   تمیزسازی آن به شکلی که مستقیماً قابل paste و اجرا روی یک سوییچ جدید باشد

پیش‌نیاز نصب:
    pip install netmiko cryptography

فرض مهم: تمام سوییچ‌های شبکه با همان یوزرنیم/پسورد/enable سوییچ seed
قابل دسترسی هستند. اگر این‌طور نیست، هر سوییچ را جداگانه در لیست
دستگاه‌ها (با credentials خودش) اضافه کن و آن را به‌عنوان seed انتخاب کن.
"""

import re
import os
import sys
import json
import getpass
import logging
from logging.handlers import RotatingFileHandler
import difflib
from datetime import datetime
from netmiko import ConnectHandler
from netmiko.exceptions import NetmikoTimeoutException, NetmikoAuthenticationException

import device_manager
import backup_settings
import audit_log
import app_paths

BASE_DIR = app_paths.get_app_dir(__file__)

# Configure module logger
logger = logging.getLogger(__name__)
if not logger.handlers:
    console_handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s %(levelname)s: %(message)s")
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # لاگ عملیاتی روی دیسک هم لازم است - نه فقط کنسول - چون وقتی برنامه
    # headless (مثلاً از طریق Windows Task Scheduler) اجرا می‌شود، هیچ‌کس
    # کنسول را نمی‌بیند و بدون این فایل، تمام پیام‌های INFO/WARNING/ERROR
    # برای همیشه گم می‌شوند.
    file_handler = RotatingFileHandler(
        os.path.join(BASE_DIR, "cisco_mgmt.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    logger.setLevel(logging.INFO)


MAX_TOPOLOGY_DEPTH = 4  # حداکثر تعداد هاپ برای جلوگیری از walk بی‌نهایت


# ---------------------------------------------------------------------------
# ابزار کمکی: نرمال‌سازی نام پورت
# ---------------------------------------------------------------------------
def normalize_port_name(name: str) -> str:
    """
    نام‌های کامل اینترفیس (که مثلاً CDP برمی‌گرداند، مثل GigabitEthernet1/0/1)
    را به فرم کوتاه‌شده‌ای که 'show mac address-table' و 'show interfaces trunk'
    استفاده می‌کنند (مثل Gi1/0/1) تبدیل می‌کند، تا بشود این دو را با هم مقایسه کرد.
    """
    replacements = [
        ("TenGigabitEthernet", "Te"),
        ("GigabitEthernet", "Gi"),
        ("FastEthernet", "Fa"),
        ("Ethernet", "Eth"),
        ("Port-channel", "Po"),
    ]
    for full, abbr in replacements:
        if name.startswith(full):
            return abbr + name[len(full):]
    return name


# ---------------------------------------------------------------------------
# بخش ۱: جدول ARP -> نگاشت IP به اینترفیس L3 (VLAN/SVI) - فقط روی دستگاه L3 معنادار است
# ---------------------------------------------------------------------------
def get_arp_table(conn, debug: bool = False):
    """
    خروجی 'show ip arp' را می‌گیرد و لیستی از دیکشنری‌ها برمی‌گرداند:
    [{'ip': ..., 'mac': ..., 'interface': ...}, ...]
    """
    output = conn.send_command("show ip arp")
    entries = []

    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 6 or parts[0] != "Internet":
            continue
        ip, mac, interface = parts[1], parts[3], parts[5]
        entries.append({"ip": ip, "mac": mac, "interface": interface})

    if debug and not entries:
        print("\n[DEBUG] No ARP entries parsed. Raw command output:\n")
        print(output)
        print("\n[DEBUG] End of raw output.\n")

    return entries


# ---------------------------------------------------------------------------
# بخش ۲: جدول MAC Address -> نگاشت MAC به پورت فیزیکی (محلی، روی همین دستگاه)
# ---------------------------------------------------------------------------
def get_mac_table(conn, debug: bool = False):
    """
    خروجی 'show mac address-table' را می‌گیرد و دیکشنری‌ای برمی‌گرداند:
    { mac_address: physical_port }
    """
    output = conn.send_command("show mac address-table", read_timeout=30)
    table = {}

    for line in output.splitlines():
        parts = line.split()
        if len(parts) != 4 or not parts[0].isdigit():
            continue
        _vlan, mac, _type, port = parts
        table[mac.lower()] = port

    if debug and not table:
        print("\n[DEBUG] No MAC address-table entries parsed. Raw command output:\n")
        print(output)
        print("\n[DEBUG] End of raw output.\n")

    return table


# ---------------------------------------------------------------------------
# بخش ۳: تشخیص پورت‌های trunk (uplink به سوییچ‌های دیگر)
# ---------------------------------------------------------------------------
def get_trunk_ports(conn, debug: bool = False):
    output = conn.send_command("show interfaces trunk")
    trunk_ports = set()

    in_port_section = False
    for line in output.splitlines():
        if line.strip().startswith("Port") and "Mode" in line:
            in_port_section = True
            continue
        if in_port_section:
            parts = line.split()
            if not parts:
                break
            trunk_ports.add(parts[0])

    if debug and not trunk_ports:
        print("\n[DEBUG] No trunk ports parsed (device may have no trunks configured). Raw output:\n")
        print(output)
        print("\n[DEBUG] End of raw output.\n")

    return trunk_ports


# ---------------------------------------------------------------------------
# بخش ۴: همسایه‌های CDP -> نگاشت پورت محلی به IP/hostname سوییچ همسایه
# ---------------------------------------------------------------------------
def get_cdp_neighbors(conn, debug: bool = False):
    """
    خروجی 'show cdp neighbors detail' را می‌گیرد و دیکشنری‌ای برمی‌گرداند:
    { local_port (نرمال‌شده): {"ip": ..., "hostname": ...} }

    این تابع مستقل از مدل/ورژن دقیق IOS کار می‌کند چون به‌جای وابستگی به
    ترتیب دقیق خطوط، خروجی را بر اساس خط جداکننده‌ی استاندارد CDP
    ("----...") به بلوک‌های جدا تقسیم می‌کند و از هر بلوک فقط دو فیلد
    Interface و IP address را با regex استخراج می‌کند.
    """
    output = conn.send_command("show cdp neighbors detail", read_timeout=30)
    neighbors = {}

    blocks = re.split(r"-{10,}", output)
    for block in blocks:
        m_intf = re.search(r"Interface:\s*(\S+?),", block)
        m_ip = re.search(r"IP address:\s*(\S+)", block)
        m_host = re.search(r"Device ID:\s*(\S+)", block)
        if m_intf and m_ip:
            local_port = normalize_port_name(m_intf.group(1))
            neighbor_ip = m_ip.group(1)
            neighbor_host = m_host.group(1) if m_host else neighbor_ip
            neighbors[local_port] = {"ip": neighbor_ip, "hostname": neighbor_host}

    if debug and not neighbors:
        print("\n[DEBUG] No CDP neighbors parsed (CDP may be disabled on this device). Raw output:\n")
        print(output)
        print("\n[DEBUG] End of raw output.\n")

    return neighbors


# ---------------------------------------------------------------------------
# بخش ۵: Walk کردن کل توپولوژی - از seed شروع و روی هر trunk تا هر عمقی ادامه می‌دهد
# ---------------------------------------------------------------------------
def ensure_enable_mode(conn, host: str) -> None:
    """Enter enable mode when the device is not already in privileged exec."""
    if conn.check_enable_mode():
        return
    try:
        conn.enable()
    except Exception as e:
        logger.warning(
            "Failed to enter enable mode on %s. Continuing with current privilege level...",
            host,
            e,
        )


def get_serial_number(conn, debug: bool = False) -> str | None:
    """
    شماره سریال شاسی دستگاه را از 'show version' می‌خواند. برخلاف hostname
    که ادمین تنظیمش می‌کند (و ممکن است تنظیم نشده باشد یا تکراری باشد)،
    شماره سریال توسط کارخانه تعیین می‌شود و همیشه یکتاست - برای همین
    شناسه‌ی قابل‌اعتمادتری برای تشخیص دستگاه‌هاست.

    فرمت خروجی بسته به مدل/ورژن IOS فرق می‌کند، برای همین چند الگو را
    امتحان می‌کنیم:
      "Processor board ID FCW2140L0GH"        (اکثر پلتفرم‌های کلاسیک IOS)
      "System Serial Number           : FOC12345ABCD"   (بعضی پلتفرم‌های جدیدتر)
    """
    output = conn.send_command("show version", read_timeout=20)

    patterns = [
        r"Processor board ID\s+(\S+)",
        r"System Serial Number\s*:?\s*(\S+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, output)
        if m:
            return m.group(1)

    if debug:
        print("\n[DEBUG] Could not parse serial number from 'show version'. Raw output:\n")
        print(output)
        print("\n[DEBUG] End of raw output.\n")

    return None


def scan_topology(device_params: dict, max_depth: int = MAX_TOPOLOGY_DEPTH, debug: bool = True):
    """
    از دستگاه seed شروع می‌کند، ARP را از آنجا می‌خواند (چون فقط دستگاه L3
    جدول ARP معنادار دارد)، سپس با BFS روی پورت‌های trunk قدم می‌زند:
    هر سوییچی که کشف شود را هم به همان credentials وصل می‌شود، MAC table
    و trunk ports و CDP neighbors آن را می‌خواند.

    خروجی نهایی mac_location است: نگاشت هر MAC به دقیق‌ترین پورت فیزیکی
    و نام دستگاهی که پیدا شده - یعنی حتی اگر دستگاه پشت ۳-۴ سوییچ دیگر
    باشد، اگر مسیر از طریق CDP قابل کشف باشد، پورت edge واقعی پیدا می‌شود.

    برمی‌گرداند: (seed_conn, seed_hostname, arp_entries, mac_location)
    seed_conn باز می‌ماند تا بعداً برای بک‌آپ کانفیگ استفاده شود.
    """
    visited_ips = set()
    mac_location = {}      # mac -> {"device": hostname, "device_serial": serial, "port": port}  (پورت واقعی، غیر-trunk)
    tentative_location = {}  # همون ساختار، فقط پشت یک trunk، عمق بیشتر کشف نشد
    hostname_to_serials = {}  # برای تشخیص hostname تکراری روی سریال‌های مختلف

    def _register_hostname(hostname: str, serial: str | None):
        if serial is None:
            return
        seen = hostname_to_serials.setdefault(hostname, set())
        seen.add(serial)
        if len(seen) > 1:
            print(f"WARNING: duplicate hostname '{hostname}' detected on {len(seen)} different devices "
                  f"(different serial numbers: {', '.join(seen)}). "
                  f"Set unique hostnames on these switches for reliable device identification.")

    netmiko_params = dict(device_params)
    for key in ("name", "is_core", "auto_backup"):
        netmiko_params.pop(key, None)

    try:
        seed_conn = ConnectHandler(**netmiko_params)
    except (NetmikoAuthenticationException, NetmikoTimeoutException) as e:
        logger.error("Authentication/connection failed for seed device %s: %s", device_params.get("host", "unknown"), e)
        audit_log.log_event(
            "DEVICE_AUTH_FAILURE",
            f"host={device_params.get('host', 'unknown')} context=topology_scan",
            level="WARNING",
        )
        raise
    except Exception as e:
        logger.error("Failed to connect to seed device %s: %s", device_params.get("host", "unknown"), e)
        raise

    ensure_enable_mode(seed_conn, device_params.get("host", "unknown"))

    seed_hostname = seed_conn.find_prompt().strip("#>").strip()
    seed_serial = get_serial_number(seed_conn, debug=debug)
    _register_hostname(seed_hostname, seed_serial)
    logger.info("Connected to seed device. Hostname: %s (Serial: %s)", seed_hostname, seed_serial or "unknown")

    arp_entries = get_arp_table(seed_conn, debug=debug)

    queue = [(seed_conn, seed_hostname, seed_serial, device_params["host"], 0)]
    visited_ips.add(device_params["host"])

    while queue:
        conn, hostname, serial, ip, depth = queue.pop(0)
        logger.info("Scanning %s (%s) at depth %d...", hostname, ip, depth)

        mac_table = get_mac_table(conn, debug=debug)
        trunk_ports = get_trunk_ports(conn, debug=debug)

        for mac, port in mac_table.items():
            if port in trunk_ports:
                if mac not in mac_location and mac not in tentative_location:
                    tentative_location[mac] = {"device": hostname, "device_serial": serial, "port": port}
            else:
                mac_location[mac] = {"device": hostname, "device_serial": serial, "port": port}
                tentative_location.pop(mac, None)

        if depth >= max_depth or not trunk_ports:
            if conn is not seed_conn:
                conn.disconnect()
            continue

        cdp = get_cdp_neighbors(conn, debug=debug)
        for local_port in trunk_ports:
            neighbor = cdp.get(local_port)
            if not neighbor:
                # این trunk به یک سوییچ دیگه می‌ره ولی CDP روی همسایه فعال نیست
                # یا نتونستیم پیداش کنیم - همون tentative_location (پشت این trunk) باقی می‌مونه
                continue

            neighbor_ip = neighbor["ip"]
            if neighbor_ip in visited_ips:
                continue
            visited_ips.add(neighbor_ip)

            next_params = dict(netmiko_params)
            next_params["host"] = neighbor_ip
            try:
                next_conn = ConnectHandler(**next_params)
            except (NetmikoAuthenticationException, NetmikoTimeoutException) as e:
                logger.warning(
                    "Could not connect to neighbor %s (%s): %s. Skipping this branch (credentials may differ).",
                    neighbor["hostname"], neighbor_ip, e,
                )
                continue

            ensure_enable_mode(next_conn, neighbor_ip)

            next_hostname = next_conn.find_prompt().strip("#>").strip()
            next_serial = get_serial_number(next_conn, debug=debug)
            _register_hostname(next_hostname, next_serial)
            queue.append((next_conn, next_hostname, next_serial, neighbor_ip, depth + 1))

        if conn is not seed_conn:
            conn.disconnect()

    # پورت‌های واقعی (mac_location) اولویت دارند؛ برای هرچه پیدا نشد، از
    # tentative_location استفاده می‌شود (یعنی حداقل می‌دونیم پشت کدوم
    # trunk روی کدوم دستگاهه، حتی اگه به سوییچ بعدی نتونستیم برسیم)
    final_location = {**tentative_location, **mac_location}
    return seed_conn, seed_hostname, arp_entries, final_location


def refresh_unresolved_via_ping(seed_conn, arp_entries, mac_location):
    """
    برای IP هایی که هنوز resolve نشدن، از سوییچ seed ping می‌زنیم. چون
    ترافیک ping باید فیزیکی از تمام سوییچ‌های مسیر عبور کنه تا به مقصد
    برسه، این کار MAC Address Table تمام سوییچ‌های روی مسیر (نه فقط
    seed) رو تازه می‌کنه - برای همین بعد از ping باید کل توپولوژی رو
    دوباره scan کنیم.
    """
    unresolved_ips = [e["ip"] for e in arp_entries if e["mac"].lower() not in mac_location]
    if not unresolved_ips:
        return False

    logger.info("Pinging %d unresolved IP(s) to refresh MAC tables across the topology...", len(unresolved_ips))
    for ip in unresolved_ips:
        try:
            seed_conn.send_command(f"ping {ip}", read_timeout=30)
        except Exception as ex:
            logger.warning("Ping to %s timed out or failed (%s). Skipping.", ip, ex)
    return True


def build_resolved_entries(arp_entries, mac_location):
    resolved = []
    for entry in arp_entries:
        mac = entry["mac"].lower()
        loc = mac_location.get(mac)
        resolved.append(
            {
                "ip": entry["ip"],
                "mac": entry["mac"],
                "vlan_interface": entry["interface"],
                "device": loc["device"] if loc else "-",
                "device_serial": loc["device_serial"] if loc else None,
                "physical_port": loc["port"] if loc else "-",
            }
        )
    return resolved


def print_discovered_devices(entries):
    """
    وقتی فیلتر یک دستگاه هیچ نتیجه‌ای نداد، این تابع لیست دستگاه‌هایی که
    واقعاً در طول walk کردن توپولوژی کشف شدند (hostname + سریال) را چاپ
    می‌کند - تا ادمین بفهمد شماره سریال دستگاه موردنظرش با یکی از
    این‌ها یکی هست یا نه.
    """
    seen = {}
    for e in entries:
        if e["device_serial"]:
            seen[e["device_serial"]] = e["device"]

    if not seen:
        print("No devices were discovered in the topology at all (check core connectivity/CDP).")
        return

    print("\nDevices actually discovered during the topology walk:")
    for serial, hostname in seen.items():
        print(f"  - {hostname}  (Serial: {serial})")
    print()


def print_arp_table(entries):
    logger.info("Active IPs by device and physical port (full topology)")
    print(f"{'Device':<20}{'Port':<12}{'IP Address':<18}{'MAC Address':<18}{'VLAN':<8}")
    print("-" * 76)
    for e in sorted(entries, key=lambda x: (x["device"], x["physical_port"])):
        print(f"{e['device']:<20}{e['physical_port']:<12}{e['ip']:<18}{e['mac']:<18}{e['vlan_interface']:<8}")
    print(f"\nTotal entries: {len(entries)}")
    print("Note: device/port '-' means the MAC could not be located anywhere in the")
    print("scanned topology (typically the seed switch's own SVI IP, a directly")
    print("routed link, or a device that is currently offline).\n")


# ---------------------------------------------------------------------------
# بخش ۶: بک‌آپ کانفیگ و تبدیل به فرمت قابل اجرا (فعلاً فقط سوییچ seed)
# ---------------------------------------------------------------------------
def get_running_config(conn):
    return conn.send_command("show running-config", read_timeout=30)


def clean_config_for_restore(raw_config: str) -> str:
    """
    خروجی show running-config را به فرمتی قابل‌استفاده برای restore تبدیل می‌کند.

    هدف این است که پیکربندی روی سوییچ خام بدون نیاز به پاک‌سازی دستی
    قابل‌پست باشد. برای این کار:
    - خطوط غیرضروری و هدرهای نمایشی را حذف می‌کند
    - بلوک‌های PKI/گواهی خودامضا را حذف می‌کند
    - دستورات پویا و مربوط به دستگاه فعلی مثل MAC sticky را حذف می‌کند
    - بخش‌های interface را به‌صورت بلوک‌های قابل‌استفاده بازنویسی می‌کند
      و در صورت هم‌خوانی، به interface range تبدیل می‌کند
    - در پایان با end و write memory بسته می‌شود
    """
    lines = raw_config.splitlines()
    global_lines: list[str] = []
    interface_blocks: list[tuple[str, list[str]]] = []

    skip_patterns = [
        r"^Building configuration",
        r"^Current configuration",
        r"^!\s*Last configuration change",
        r"^!\s*NVRAM config last updated",
        r"^ntp clock-period",
    ]
    skip_regex = re.compile("|".join(skip_patterns))

    def normalize_line(line: str) -> str:
        return line.strip()

    def keep_global(line: str) -> bool:
        lower = line.lower().strip()
        if lower.startswith("hostname "):
            return True
        if lower.startswith("enable secret "):
            return True
        if lower.startswith("username "):
            return True
        if lower.startswith("clock timezone "):
            return True
        if lower.startswith("ip domain-name "):
            return True
        if lower.startswith("ip ssh version "):
            return True
        if lower.startswith("ip dhcp snooping"):
            return True
        if lower.startswith("ip verify source"):
            return True
        if lower.startswith("logging "):
            return True
        if lower.startswith("service timestamps "):
            return True
        if lower.startswith("snmp-server "):
            return True
        if lower.startswith("access-list "):
            return True
        if lower.startswith("ntp server "):
            return True
        if lower.startswith("spanning-tree "):
            return True
        if lower.startswith("vlan "):
            return True
        if lower.startswith("no service password-encryption"):
            return True
        if lower.startswith("ip name-server "):
            return True
        if lower.startswith("ip default-gateway "):
            return True
        if lower.startswith("system mtu routing "):
            return True
        if lower.startswith("ip route "):
            return True
        return False

    def keep_block_command(line: str) -> bool:
        lower = line.lower().strip()
        if lower.startswith("switchport "):
            if "switchport port-security mac-address sticky" in lower:
                return False
            return True
        if lower.startswith("storm-control "):
            return True
        if lower.startswith("spanning-tree "):
            return True
        if lower.startswith("mls qos"):
            return True
        if lower.startswith("priority-queue"):
            return True
        if lower.startswith("srr-queue"):
            return True
        if lower.startswith("shutdown"):
            return True
        if lower.startswith("no shutdown"):
            return True
        if lower.startswith("duplex "):
            return True
        if lower.startswith("speed "):
            return True
        if lower.startswith("description "):
            return True
        if lower.startswith("ip dhcp snooping"):
            return True
        if lower.startswith("ip verify source"):
            return True
        if lower.startswith("standby "):
            return True
        if lower.startswith("switchport mode "):
            return True
        return False

    def normalize_interface_body_for_grouping(body: list[str]) -> tuple[str, ...]:
        normalized = []
        for line in body:
            stripped = normalize_line(line)
            lower = stripped.lower().strip()
            if lower in {"shutdown", "no shutdown"}:
                continue
            if lower.startswith("duplex ") or lower.startswith("speed "):
                continue
            if lower.startswith("description "):
                continue
            if lower.startswith("switchport port-security"):
                continue
            normalized.append(stripped)
        return tuple(normalized)

    def same_body(body_a: list[str], body_b: list[str]) -> bool:
        return normalize_interface_body_for_grouping(body_a) == normalize_interface_body_for_grouping(body_b)

    def parse_interface_range(header: str) -> tuple[str, int, int] | None:
        if not header.lower().startswith("interface "):
            return None
        name = header[len("interface "):].strip()
        match = re.match(r"^(?P<prefix>.+?)(?P<last>\d+)$", name)
        if not match:
            return None
        prefix = match.group("prefix")
        last = int(match.group("last"))
        return prefix, last, last

    def can_group(headers: list[str]) -> tuple[str, int, int] | None:
        if len(headers) < 2:
            return None
        parsed = []
        for header in headers:
            parsed_item = parse_interface_range(header)
            if parsed_item is None:
                return None
            parsed.append(parsed_item)

        prefix = parsed[0][0]
        if not all(item[0] == prefix for item in parsed):
            return None

        nums = [item[1] for item in parsed]
        if any(nums[i] + 1 != nums[i + 1] for i in range(len(nums) - 1)):
            return None
        start = nums[0]
        end = nums[-1]
        return prefix, start, end

    current_interface_header: str | None = None
    current_interface_lines: list[str] = []

    for line in lines:
        stripped = line.rstrip()
        if not stripped.strip():
            continue
        if skip_regex.search(stripped):
            continue

        lower = stripped.lower().strip()
        if lower in {"end", "write memory", "copy running-config startup-config", "copy run start", "wr"}:
            continue
        if lower.startswith("boot-start-marker") or lower.startswith("boot-end-marker"):
            continue
        if lower.startswith("crypto pki"):
            continue
        if lower.startswith("certificate") or "BEGIN CERTIFICATE" in lower or "END CERTIFICATE" in lower:
            continue
        if lower.startswith("!"):
            if current_interface_header is not None:
                interface_blocks.append((current_interface_header, current_interface_lines))
                current_interface_header = None
                current_interface_lines = []
            continue

        if lower.startswith("interface "):
            if current_interface_header is not None:
                interface_blocks.append((current_interface_header, current_interface_lines))
                current_interface_header = None
                current_interface_lines = []
            current_interface_header = normalize_line(stripped)
            current_interface_lines = []
            continue

        if current_interface_header is not None:
            if keep_block_command(stripped):
                current_interface_lines.append(normalize_line(stripped))
            continue

        if keep_global(stripped):
            global_lines.append(normalize_line(stripped))

    if current_interface_header is not None:
        interface_blocks.append((current_interface_header, current_interface_lines))

    result = ["conf t", "! Cleaned configuration for restore"]
    if global_lines:
        result.extend(global_lines)

    idx = 0
    while idx < len(interface_blocks):
        header, body = interface_blocks[idx]
        group_headers = [header]
        group_body = body
        next_idx = idx + 1
        while next_idx < len(interface_blocks):
            next_header, next_body = interface_blocks[next_idx]
            if same_body(group_body, next_body):
                parsed = can_group(group_headers + [next_header])
                if parsed is not None:
                    group_headers.append(next_header)
                    next_idx += 1
                    continue
            break

        if len(group_headers) > 1:
            range_info = can_group(group_headers)
            if range_info is not None:
                prefix, start, end = range_info
                result.append("!")
                result.append(f"interface range {prefix}{start}-{end}")
                result.extend(group_body)
                result.append("exit")
                idx = next_idx
                continue

        result.append("!")
        result.append(header)
        if body:
            result.extend(body)
        result.append("exit")
        idx += 1

    result.append("end")
    result.append("write memory")
    return "\n".join(result).strip() + "\n"


def enforce_retention(backup_dir: str, hostname: str, retention_count: int) -> None:
    """
    فایل‌های بک‌آپ قدیمی‌تر از تعداد نگه‌داشت مشخص‌شده را برای این
    hostname به‌طور خودکار حذف می‌کند. چون timestamp در نام فایل به
    فرمت YYYY-MM-DD_HH-MM-SS است، مرتب‌سازی الفبایی همان مرتب‌سازی
    زمانی است (قدیمی‌ترها اول لیست می‌آیند).
    """
    if retention_count <= 0:
        return

    prefix = f"{hostname}_"
    try:
        matching = sorted(
            f for f in os.listdir(backup_dir)
            if f.startswith(prefix) and f.endswith(".txt")
        )
    except FileNotFoundError:
        return

    excess = len(matching) - retention_count
    for old_file in matching[:excess]:
        try:
            os.remove(os.path.join(backup_dir, old_file))
            print(f"Removed old backup (retention limit reached): {old_file}")
        except OSError as e:
            print(f"Warning: could not remove old backup '{old_file}' ({e}).")


def save_backup(hostname: str, cleaned_config: str, backup_dir: str, retention_count: int) -> str:
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{hostname}_{timestamp}.txt"
    filepath = os.path.join(backup_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(cleaned_config)

    enforce_retention(backup_dir, hostname, retention_count)
    logger.info("Backup saved: %s", filepath)

    return os.path.abspath(filepath)


# ---------------------------------------------------------------------------
# بخش ۷: Config Drift - مقایسه‌ی بک‌آپ‌های پیاپی یک دستگاه و هشدار روی تغییرات
# ---------------------------------------------------------------------------
def list_backup_files(backup_dir: str, hostname: str) -> list[str]:
    """
    مسیر کامل تمام فایل‌های بک‌آپ یک hostname را برمی‌گرداند - مرتب از
    قدیمی به جدید (چون timestamp تو نام فایل هست، مرتب‌سازی الفبایی
    همان مرتب‌سازی زمانی است).
    """
    prefix = f"{hostname}_"
    try:
        matching = sorted(
            f for f in os.listdir(backup_dir)
            if f.startswith(prefix) and f.endswith(".txt")
        )
    except FileNotFoundError:
        return []
    return [os.path.join(backup_dir, f) for f in matching]


def list_backed_up_hostnames(backup_dir: str) -> list[str]:
    """
    از روی نام فایل‌های موجود تو پوشه‌ی بک‌آپ، لیست یکتای hostname هایی
    که حداقل یک بک‌آپ ازشون گرفته شده را برمی‌گرداند. چون نام فایل به
    فرم '{hostname}_{YYYY-MM-DD}_{HH-MM-SS}.txt' است (یعنی همیشه دقیقاً
    دو زیرخط برای بخش timestamp دارد، حتی اگر خود hostname هم زیرخط
    داشته باشد)، rsplit با maxsplit=2 درست کار می‌کند.
    """
    try:
        files = os.listdir(backup_dir)
    except FileNotFoundError:
        return []
    hostnames = {
        f.rsplit("_", 2)[0]
        for f in files
        if f.endswith(".txt") and f.count("_") >= 2
    }
    return sorted(hostnames)


def diff_latest_two_backups(backup_dir: str, hostname: str) -> str | None:
    """
    یک unified diff بین دو بک‌آپ آخر یک دستگاه برمی‌گرداند.
    - None یعنی کمتر از ۲ بک‌آپ موجوده (چیزی برای مقایسه نیست)
    - رشته‌ی خالی یعنی مقایسه انجام شد ولی هیچ تفاوتی نبود
    - رشته‌ی غیرخالی یعنی خط‌به‌خط تغییرات کانفیگ
    """
    files = list_backup_files(backup_dir, hostname)
    if len(files) < 2:
        return None

    older_path, newer_path = files[-2], files[-1]
    with open(older_path, "r", encoding="utf-8") as f:
        older_lines = f.read().splitlines()
    with open(newer_path, "r", encoding="utf-8") as f:
        newer_lines = f.read().splitlines()

    diff_lines = list(
        difflib.unified_diff(
            older_lines,
            newer_lines,
            fromfile=os.path.basename(older_path),
            tofile=os.path.basename(newer_path),
            lineterm="",
        )
    )
    return "\n".join(diff_lines)


def check_drift_for_device(hostname: str, backup_dir: str) -> bool:
    """
    درفت رو برای یک دستگاه چاپ می‌کند. مقدار برگشتی True یعنی تغییری
    پیدا شد (برای استفاده در check_drift_all_devices جهت شمارش).
    """
    diff_text = diff_latest_two_backups(backup_dir, hostname)
    if diff_text is None:
        print(f"{hostname}: fewer than 2 backups exist yet - nothing to compare.")
        return False
    if diff_text == "":
        print(f"{hostname}: no configuration changes since the previous backup.")
        return False

    print(f"\n=== Config drift detected: {hostname} ===")
    print(diff_text)
    print()
    audit_log.log_event(
        "CONFIG_DRIFT_DETECTED",
        f"hostname={hostname} - configuration changed since the previous backup",
        level="WARNING",
    )
    return True


def check_drift_all_devices(backup_dir: str) -> None:
    hostnames = list_backed_up_hostnames(backup_dir)
    if not hostnames:
        print("No backups have been taken yet.")
        return

    changed_count = 0
    for hostname in hostnames:
        if check_drift_for_device(hostname, backup_dir):
            changed_count += 1

    print(f"--- Checked {len(hostnames)} device(s); {changed_count} had configuration drift. ---\n")


def print_backup_history(hostname: str, backup_dir: str) -> None:
    files = list_backup_files(backup_dir, hostname)
    if not files:
        print(f"No backups found for '{hostname}'.")
        return
    print(f"\n--- Backup history: {hostname} ---")
    for i, path in enumerate(files, start=1):
        size_kb = os.path.getsize(path) / 1024
        print(f"{i}. {os.path.basename(path)}  ({size_kb:.1f} KB)")
    print()


def select_backup_hostname(backup_dir: str) -> str | None:
    """
    چون این بخش روی hostname واقعی دستگاه (که تو نام فایل بک‌آپ ثبت
    شده) کار می‌کند - نه روی رکورد دستگاه تو device_manager - لیست
    انتخاب مستقیماً از روی فایل‌های بک‌آپ ساخته می‌شود.
    """
    hostnames = list_backed_up_hostnames(backup_dir)
    if not hostnames:
        print("No backups have been taken yet.")
        return None

    print("\n--- Devices with backups ---")
    for i, h in enumerate(hostnames, start=1):
        print(f"{i}. {h}")
    choice = input("Enter the number of the device: ").strip()
    if choice.isdigit() and 1 <= int(choice) <= len(hostnames):
        return hostnames[int(choice) - 1]
    print("Invalid selection.")
    return None


# ---------------------------------------------------------------------------
# بخش ۸: گزارش پورت‌های بلااستفاده (Idle Ports) - برای سخت‌سازی امنیتی
# ---------------------------------------------------------------------------
def get_interfaces_status(conn, debug: bool = False) -> dict:
    """
    خروجی 'show interfaces status' را می‌گیرد و دیکشنری‌ای برمی‌گرداند:
    { port: {"name":..., "status":..., "vlan":..., "duplex":..., "speed":..., "type":...} }

    ستون Name می‌تواند حاوی فاصله باشد (وقتی روی پورت description گذاشته
    شده)، پس split() ساده یا پارس بر اساس موقعیت ستون هدر قابل‌اعتماد
    نیست (اگر یک مقدار طولانی‌تر از عرض ستون هدر باشد، ستون‌ها جابه‌جا
    می‌شوند). به‌جایش از این نکته استفاده می‌کنیم که پنج فیلد آخر هر
    خط (Status, Vlan, Duplex, Speed, Type) همیشه دقیقاً یک توکن هستند؛
    پس با توکن‌سازی خط، اولین توکن Port و هر چیزی بین آن و پنج توکن
    آخر، Name است - این روش با هر تعداد کلمه در description درست کار
    می‌کند.
    """
    output = conn.send_command("show interfaces status", read_timeout=30)
    interfaces: dict = {}
    lines = output.splitlines()

    header_idx = None
    for i, line in enumerate(lines):
        if line.strip().startswith("Port") and "Status" in line and "Vlan" in line:
            header_idx = i
            break

    if header_idx is None:
        if debug:
            print("\n[DEBUG] Could not find the header row in 'show interfaces status'. Raw output:\n")
            print(output)
            print("\n[DEBUG] End of raw output.\n")
        return interfaces

    for line in lines[header_idx + 1:]:
        tokens = line.split()
        if len(tokens) < 6:  # Port + 5 فیلد آخر، حداقل لازم است
            continue

        port = tokens[0]
        status, vlan, duplex, speed, port_type = tokens[-5:]
        name = " ".join(tokens[1:-5])

        interfaces[port] = {
            "name": name,
            "status": status,
            "vlan": vlan,
            "duplex": duplex,
            "speed": speed,
            "type": port_type,
        }

    if debug and not interfaces:
        print("\n[DEBUG] No interface status rows parsed. Raw command output:\n")
        print(output)
        print("\n[DEBUG] End of raw output.\n")

    return interfaces


def get_interfaces_counters(conn, debug: bool = False) -> dict:
    """
    خروجی 'show interfaces counters' را می‌خواند و برای هر پورت مجموع
    پکت‌های ورودی و خروجی (Ucast+Mcast+Bcast) را برمی‌گرداند:
        { port: {"in_pkts": int, "out_pkts": int} }

    برخلاف 'show interfaces status'، این خروجی هیچ فیلد متنی آزاد
    (مثل description) ندارد - فقط Port و چند ستون عددی - پس split()
    ساده کاملاً قابل‌اعتماد است و نیازی به تکنیک token-from-both-ends
    ندارد.
    """
    output = conn.send_command("show interfaces counters", read_timeout=30)
    counters: dict = {}
    section = None  # "in" یا "out" - بسته به اینکه تو کدوم جدول هستیم

    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("Port") and "InOctets" in stripped:
            section = "in"
            continue
        if stripped.startswith("Port") and "OutOctets" in stripped:
            section = "out"
            continue
        if section is None:
            continue

        tokens = stripped.split()
        if len(tokens) < 4:
            continue
        port = tokens[0]
        try:
            numbers = [int(t.replace(",", "")) for t in tokens[1:]]
        except ValueError:
            continue

        entry = counters.setdefault(port, {"in_pkts": 0, "out_pkts": 0})
        # ستون‌ها: Octets, UcastPkts, McastPkts, BcastPkts - مجموع سه‌تای
        # آخر برابر کل تعداد پکت است (Octets صرفاً بایت است، نه پکت)
        total_pkts = sum(numbers[1:4]) if len(numbers) >= 4 else sum(numbers[1:])
        if section == "in":
            entry["in_pkts"] = total_pkts
        else:
            entry["out_pkts"] = total_pkts

    if debug and not counters:
        print("\n[DEBUG] Could not parse 'show interfaces counters'. Raw output:\n")
        print(output)
        print("\n[DEBUG] End of raw output.\n")

    return counters


TRAFFIC_STATE_FILE = os.path.join(BASE_DIR, "port_traffic_state.json")


def load_traffic_state() -> dict:
    if not os.path.exists(TRAFFIC_STATE_FILE):
        return {}
    with open(TRAFFIC_STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_traffic_state(state: dict) -> None:
    with open(TRAFFIC_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def update_traffic_state_for_device(hostname: str, counters: dict) -> dict:
    """
    شمارنده‌های تازه‌خوانده‌شده رو با آخرین snapshot ذخیره‌شده روی دیسک
    مقایسه می‌کنه. اگر شمارنده‌ی یک پورت نسبت به دفعه‌ی قبل عوض نشده
    باشه، last_changed دست‌نخورده می‌مونه (یعنی «از آخرین تغییر واقعی
    چند روز گذشته» درست محاسبه می‌شه، نه از آخرین باری که این تابع
    اجرا شده). اگر عوض شده یا برای اولین‌بار دیده می‌شه، last_changed
    = الان.

    نتیجه‌ی به‌روزشده هم روی دیسک ذخیره می‌شه و هم برگردونده می‌شه.
    """
    state = load_traffic_state()
    device_state = state.get(hostname, {})
    now = datetime.now().isoformat(timespec="seconds")

    for port, c in counters.items():
        prev = device_state.get(port)
        if prev is None or prev.get("in_pkts") != c["in_pkts"] or prev.get("out_pkts") != c["out_pkts"]:
            device_state[port] = {
                "in_pkts": c["in_pkts"],
                "out_pkts": c["out_pkts"],
                "last_changed": now,
            }
        # اگه شمارنده عوض نشده، prev دست‌نخورده می‌مونه (last_changed قدیمی حفظ می‌شه)

    state[hostname] = device_state
    save_traffic_state(state)
    return device_state


def find_traffic_idle_ports(device_state: dict, interfaces: dict, idle_days: int) -> dict:
    """
    از بین پورت‌هایی که الان status=connected دارن (یعنی از نظر لینک
    «در حال استفاده» به نظر می‌رسن)، اون‌هایی که شمارنده‌ی پکتشون حداقل
    idle_days روزه تغییر نکرده رو برمی‌گردونه - یعنی پورت‌هایی که لینک
    بالاست ولی عملاً ترافیکی رد و بدل نمی‌شه (مثلاً سرور از رده‌خارج‌شده‌ای
    که کابلش هنوز وصله).
    """
    idle = {}
    now = datetime.now()
    for port, d in interfaces.items():
        if d["status"].lower() != "connected":
            continue
        port_state = device_state.get(port)
        if not port_state:
            continue
        last_changed = datetime.fromisoformat(port_state["last_changed"])
        days_idle = (now - last_changed).days
        if days_idle >= idle_days:
            idle[port] = {**d, "days_idle": days_idle}
    return idle



def print_idle_ports_report(hostname: str, interfaces: dict, traffic_idle: dict | None = None) -> None:
    """
    گزارش نهایی رو چاپ می‌کند: پورت‌های notconnect (بدون لینک)،
    err-disabled، و اگر traffic_idle داده شده باشد، پورت‌های connected
    که مدتی است هیچ پکتی رد نکرده‌اند (خروجی find_traffic_idle_ports).
    """
    traffic_idle = traffic_idle or {}

    notconnect = {p: d for p, d in interfaces.items() if d["status"].lower() == "notconnect"}
    err_disabled = {p: d for p, d in interfaces.items() if "err" in d["status"].lower()}
    connected = {p: d for p, d in interfaces.items() if d["status"].lower() == "connected"}
    disabled = {p: d for p, d in interfaces.items() if d["status"].lower() == "disabled"}

    print(f"\n=== Idle Ports Report: {hostname} ===")
    print(
        f"Total ports: {len(interfaces)}  |  Connected: {len(connected)}  |  "
        f"Already shut down: {len(disabled)}  |  Idle (up, no link): {len(notconnect)}  |  "
        f"Err-disabled: {len(err_disabled)}\n"
    )

    if notconnect:
        print("--- Idle ports (administratively up, nothing connected - candidates for security hardening) ---")
        print(f"{'Port':<12}{'Name':<20}{'Vlan':<8}")
        print("-" * 40)
        for port, d in sorted(notconnect.items()):
            print(f"{port:<12}{d['name'][:19]:<20}{d['vlan']:<8}")
    else:
        print("No idle (notconnect) ports found.")

    if err_disabled:
        print("\n--- WARNING: Err-disabled ports (need attention) ---")
        for port, d in sorted(err_disabled.items()):
            print(f"  - {port} ({d['name']})")

    if traffic_idle:
        print("\n--- Connected ports with no traffic for a while (link up, but likely unused) ---")
        print(f"{'Port':<12}{'Name':<20}{'Vlan':<8}{'Days idle':<10}")
        print("-" * 50)
        for port, d in sorted(traffic_idle.items(), key=lambda kv: -kv[1]["days_idle"]):
            print(f"{port:<12}{d['name'][:19]:<20}{d['vlan']:<8}{d['days_idle']:<10}")
    elif interfaces:
        print(
            "\nNo traffic-idle ports flagged yet (either every connected port had "
            "recent traffic, or there isn't enough history yet - the traffic "
            "check needs at least one prior run of this report to compare against)."
        )

    print(
        "\nNote: the notconnect/err-disabled sections reflect only the current"
        "\nlink status. A notconnect port might just be one whose user"
        "\ntemporarily unplugged the cable - manual verification is recommended"
        "\nbefore shutting a port down. The traffic-idle section (if any) is"
        "\nbased on packet counters compared against the last time this report"
        "\nwas run on this device.\n"
    )


def run_idle_ports_report(selected_device: dict, idle_days_threshold: int = 14) -> None:
    """
    مستقیماً به دستگاه انتخابی وصل می‌شود، وضعیت پورت‌ها و شمارنده‌ی
    پکت‌ها را می‌خواند، شمارنده‌ها را با آخرین snapshot ذخیره‌شده مقایسه
    می‌کند (و آن snapshot را برای دفعه‌ی بعد به‌روز می‌کند)، و گزارش
    نهایی (notconnect + err-disabled + traffic-idle) را چاپ می‌کند.
    """
    params = device_manager.to_connection_params(selected_device)
    logger.info("Connecting to %s for idle ports report...", params["host"])

    try:
        conn = ConnectHandler(**params)
    except NetmikoAuthenticationException:
        logger.error("Authentication failed on %s (wrong username or password).", params["host"])
        audit_log.log_event(
            "DEVICE_AUTH_FAILURE",
            f"host={params['host']} context=idle_ports_report",
            level="WARNING",
        )
        return
    except NetmikoTimeoutException:
        logger.error("Connection to %s timed out.", params["host"])
        return

    hostname = conn.find_prompt().strip("#>").strip()
    ensure_enable_mode(conn, params["host"])
    interfaces = get_interfaces_status(conn, debug=True)
    counters = get_interfaces_counters(conn, debug=True)
    conn.disconnect()

    if not interfaces:
        print("Could not read interface status from this device.")
        return

    traffic_idle = {}
    if counters:
        device_state = update_traffic_state_for_device(hostname, counters)
        traffic_idle = find_traffic_idle_ports(device_state, interfaces, idle_days_threshold)
    else:
        print("Note: could not read packet counters from this device - skipping the traffic-idle check.")

    print_idle_ports_report(hostname, interfaces, traffic_idle)


# ---------------------------------------------------------------------------
# بخش ۹: گزارش Inventory (مدل، سریال، ورژن IOS فعلی)
# ---------------------------------------------------------------------------
CISCO_SOFTWARE_DOWNLOAD_URL = "https://software.cisco.com/download/home"

VERSION_CHECK_NOTICE = (
    "IMPORTANT: this tool only reports the version currently running on each\n"
    "device - it does NOT know what Cisco's latest stable release is. Before\n"
    "deciding whether to upgrade, manually compare the 'IOS Version' column\n"
    "below against the latest release for that exact model on Cisco's own\n"
    "site:\n"
    f"  {CISCO_SOFTWARE_DOWNLOAD_URL}\n"
    "(requires a Cisco.com account with an active service contract) - search\n"
    "there for the exact model number (e.g. 'WS-C2960X-24TS-L' or\n"
    "'C9300-24T'), open its download page, and check the recommended /\n"
    "latest release and its release notes before upgrading anything."
)


def get_version_and_model(conn, debug: bool = False):
    """
    مدل سخت‌افزار و ورژن IOS/IOS-XE را از 'show version' می‌خواند.
    فرمت خروجی بین پلتفرم‌های مختلف فرق زیادی دارد، برای همین چند الگو
    را به ترتیب امتحان می‌کنیم. برمی‌گرداند: (model_or_None, version_or_None)
    """
    output = conn.send_command("show version", read_timeout=20)

    version = None
    version_patterns = [
        r"Cisco IOS(?: XE)? Software,.*?Version\s+([^\s,]+)",
        r"IOS \(tm\).*?Version\s+([^\s,]+)",
        r"\bVersion\s+([0-9][\w.()]+)",
    ]
    for pattern in version_patterns:
        m = re.search(pattern, output)
        if m:
            version = m.group(1)
            break

    model = None
    model_patterns = [
        r"[Cc]isco (\S+)\s*\(.*?\)\s*processor",
        r"Model [Nn]umber\s*:?\s*(\S+)",
        r"[Cc]isco\s+(WS-\S+|C\d\S*|ISR\S*|ASR\S*|IE-\S*)",
    ]
    for pattern in model_patterns:
        m = re.search(pattern, output)
        if m:
            model = m.group(1)
            break

    if debug and (version is None or model is None):
        print("\n[DEBUG] Could not fully parse 'show version'. Raw output:\n")
        print(output)
        print("\n[DEBUG] End of raw output.\n")

    return model, version


def collect_inventory_row(device: dict, debug: bool = False) -> dict:
    """
    به یک دستگاه وصل می‌شود و یک ردیف inventory (hostname, IP, model,
    serial, IOS version) برمی‌گرداند. اگر اتصال ناموفق بود، فیلدهای
    model/serial/version روی None می‌مانند و پیغام خطا در 'error' ثبت
    می‌شود - این‌طوری یک دستگاه خراب کل گزارش چند-دستگاهی را متوقف نمی‌کند.
    """
    params = device_manager.to_connection_params(device)
    row = {
        "label": device.get("name", params["host"]),
        "host": params["host"],
        "hostname": None,
        "model": None,
        "serial": None,
        "version": None,
        "error": None,
    }

    try:
        conn = ConnectHandler(**params)
    except NetmikoAuthenticationException:
        row["error"] = "authentication failed"
        audit_log.log_event(
            "DEVICE_AUTH_FAILURE",
            f"host={params['host']} context=inventory_report",
            level="WARNING",
        )
        return row
    except NetmikoTimeoutException:
        row["error"] = "connection timed out"
        return row
    except Exception as e:  # noqa: BLE001 - report any other connection failure per-device
        row["error"] = str(e)
        return row

    row["hostname"] = conn.find_prompt().strip("#>").strip()
    ensure_enable_mode(conn, params["host"])
    row["model"], row["version"] = get_version_and_model(conn, debug=debug)
    row["serial"] = get_serial_number(conn, debug=debug)
    conn.disconnect()
    return row


def print_inventory_table(rows: list) -> None:
    print(f"\n{'Device':<18}{'Host':<16}{'Model':<20}{'Serial':<16}{'IOS Version':<20}")
    print("-" * 90)
    for row in rows:
        if row["error"]:
            print(f"{row['label']:<18}{row['host']:<16}ERROR: {row['error']}")
            continue
        print(
            f"{row['hostname'] or row['label']:<18}"
            f"{row['host']:<16}"
            f"{(row['model'] or '?'):<20}"
            f"{(row['serial'] or '?'):<16}"
            f"{(row['version'] or '?'):<20}"
        )
    print()
    print(VERSION_CHECK_NOTICE)
    print()


def run_inventory_report_one(selected_device: dict) -> None:
    row = collect_inventory_row(selected_device, debug=True)
    print_inventory_table([row])


def run_inventory_report_all(devices: list) -> None:
    if not devices:
        print("No devices stored yet. Add a device first.")
        return

    rows = []
    for device in devices:
        print(f"Connecting to {device.get('name', device.get('host'))}...")
        rows.append(collect_inventory_row(device, debug=False))
    print_inventory_table(rows)


# ---------------------------------------------------------------------------
# اجرای اصلی
# ---------------------------------------------------------------------------
def get_device_identity(device_params: dict, debug: bool = False):
    """
    مستقیماً به یک دستگاه وصل می‌شود و هم hostname و هم شماره سریال آن را
    برمی‌گرداند، سپس قطع می‌کند. (hostname, serial_or_None)
    """
    conn = ConnectHandler(**device_params)
    hostname = conn.find_prompt().strip("#>").strip()
    serial = get_serial_number(conn, debug=debug)
    conn.disconnect()
    return hostname, serial


def filter_entries_by_serial(entries, target_serial: str):
    """
    فیلتر بر اساس شماره سریال سخت‌افزاری - قابل‌اعتمادترین شناسه، چون
    کارخانه‌ای است و به هیچ کانفیگی (hostname یا IP) وابسته نیست.
    """
    target = target_serial.strip().lower()
    return [e for e in entries if (e["device_serial"] or "").strip().lower() == target]


def filter_entries_by_hostname(entries, target_hostname: str):
    """
    fallback برای وقتی که سریال قابل خواندن نبود. برخلاف فیلتر بر اساس
    IP (که به‌خاطر چند SVI/VLAN می‌تواند گمراه‌کننده باشد)، حداقل بهتر
    از IP است - ولی هنوز به یکتا بودن hostname روی کل شبکه وابسته است.
    """
    target = target_hostname.strip().lower()
    return [e for e in entries if e["device"].strip().lower() == target]


def get_topology_report_data(selected_device: dict, devices: list, debug: bool = True) -> dict:
    """
    نسخه‌ی داده‌محور run_topology_report - همان منطق کامل (تشخیص
    core/access، اسکن توپولوژی، ping-refresh، فیلتر بر اساس سریال/hostname)
    ولی به‌جای print کردن، یک دیکشنری ساختاریافته برمی‌گرداند. هم CLI
    (که خودش نتیجه را چاپ می‌کند) و هم GUI از همین یک تابع استفاده
    می‌کنند - منطق فقط یک‌جا نوشته شده.

    خروجی موفق: {"ok": True, "mode": "core"|"access"|"access_not_found",
                  "entries": [...], "match_desc": str|None}
    خروجی ناموفق: {"ok": False, "error": "..."}
    """
    is_core = selected_device.get("is_core", False)
    target_hostname = None
    target_serial = None

    if is_core:
        seed_params = device_manager.to_connection_params(selected_device)
    else:
        core_device = device_manager.get_core_device(devices)
        if core_device is None:
            return {
                "ok": False,
                "error": (
                    "No device is marked as core/L3 switch. Add or edit a device and "
                    "mark it as core first (the ARP table can only be read correctly "
                    "from the core switch)."
                ),
            }

        # اول مستقیم به خود سوییچ access وصل می‌شیم تا hostname و سریال
        # واقعی‌اش رو بفهمیم - بعداً برای فیلتر کردن استفاده می‌شه
        selected_params = device_manager.to_connection_params(selected_device)
        logger.info("Connecting to %s to identify the device...", selected_params["host"])
        try:
            target_hostname, target_serial = get_device_identity(selected_params, debug=debug)
        except NetmikoAuthenticationException:
            return {"ok": False, "error": f"Authentication failed on {selected_params['host']}."}
        except NetmikoTimeoutException:
            return {"ok": False, "error": f"Connection to {selected_params['host']} timed out."}
        except Exception as e:
            return {"ok": False, "error": f"Could not identify device {selected_params['host']}: {e}"}

        if target_serial is None:
            logger.warning(
                "Could not read a unique hardware serial number for '%s'. Falling back to hostname-based matching.",
                target_hostname,
            )

        seed_params = core_device

    logger.info("Connecting to %s ...", seed_params["host"])
    try:
        seed_conn, seed_hostname, arp_entries, mac_location = scan_topology(seed_params, debug=debug)
    except NetmikoAuthenticationException:
        return {"ok": False, "error": "Authentication failed (wrong username or password)."}
    except NetmikoTimeoutException:
        return {"ok": False, "error": "Connection timed out. Check IP and network reachability."}
    except Exception as e:
        return {"ok": False, "error": f"Topology scan failed: {e}"}

    # اگر بعد از یک دور کامل scan هنوز چیزی resolve نشده، ping بزن و
    # کل توپولوژی رو یک‌بار دیگه scan کن (چون ping مسیر رو تازه می‌کنه)
    if refresh_unresolved_via_ping(seed_conn, arp_entries, mac_location):
        seed_conn.disconnect()
        seed_conn, seed_hostname, arp_entries, mac_location = scan_topology(seed_params, debug=debug)

    resolved_entries = build_resolved_entries(arp_entries, mac_location)
    seed_conn.disconnect()

    if is_core:
        return {"ok": True, "mode": "core", "entries": resolved_entries, "match_desc": None}

    if target_serial:
        filtered = filter_entries_by_serial(resolved_entries, target_serial)
        match_desc = f"'{target_hostname}' (Serial: {target_serial})"
    else:
        filtered = filter_entries_by_hostname(resolved_entries, target_hostname)
        match_desc = f"'{target_hostname}' (matched by hostname - serial unavailable)"

    if not filtered:
        return {"ok": True, "mode": "access_not_found", "entries": resolved_entries, "match_desc": match_desc}

    return {"ok": True, "mode": "access", "entries": filtered, "match_desc": match_desc}


def run_topology_report(selected_device: dict, devices: list) -> None:
    """
    نسخه‌ی CLI: get_topology_report_data را صدا می‌زند و نتیجه را دقیقاً
    مثل قبل چاپ می‌کند - رفتار خروجی CLI بدون تغییر مانده است.
    """
    result = get_topology_report_data(selected_device, devices, debug=True)

    if not result["ok"]:
        print(f"Error: {result['error']}")
        return

    if result["mode"] == "core":
        print_arp_table(result["entries"])
        return

    if result["mode"] == "access_not_found":
        logger.info("No ports found for %s in the topology.", result["match_desc"])
        print_discovered_devices(result["entries"])
        return

    logger.info("Filtered to show only ports on %s", result["match_desc"])
    print_arp_table(result["entries"])


def run_backup(selected_device: dict, settings: dict) -> None:
    """
    مستقیماً به دستگاه انتخابی وصل می‌شود (فارغ از اینکه core باشد یا
    access) و از کانفیگ خودش بک‌آپ می‌گیرد. این تابع کاملاً مستقل از
    فرآیند استخراج توپولوژی است. مسیر ذخیره و تعداد نگه‌داشت از
    backup_settings خوانده می‌شود.

    برای دستگاه‌های سیسکو: 'show running-config' + پاک‌سازی اختصاصی
    (clean_config_for_restore).
    برای دستگاه‌های غیر سیسکو که دستور بک‌آپ سفارشی تعریف شده: همان
    دستور دلخواه کاربر ارسال و خروجی خام (بدون پاک‌سازی، چون سینتکس
    کانفیگ بین وندورها فرق دارد) ذخیره می‌شود.
    """
    params = device_manager.to_connection_params(selected_device)
    logger.info("Connecting to %s for config backup...", params["host"])

    try:
        conn = ConnectHandler(**params)
    except NetmikoAuthenticationException:
        logger.error("Authentication failed on %s (wrong username or password).", params["host"])
        audit_log.log_event(
            "DEVICE_AUTH_FAILURE",
            f"host={params['host']} context=backup",
            level="WARNING",
        )
        return
    except NetmikoTimeoutException:
        logger.error("Connection to %s timed out.", params["host"])
        audit_log.log_event(
            "DEVICE_CONNECT_TIMEOUT",
            f"host={params['host']} context=backup",
            level="WARNING",
        )
        return

    hostname = conn.find_prompt().strip("#>").strip()

    device_type = selected_device.get("device_type", "")
    is_cisco = device_manager.is_cisco_device_type(device_type)
    backup_command = selected_device.get("backup_command")

    if not is_cisco:
        # مهم: این شاخه فقط بر اساس نوع دستگاه تصمیم می‌گیرد، نه وجود
        # backup_command - یعنی حتی اگر داده‌ی دستگاه به هر دلیلی (مثلاً
        # داده‌ی قدیمی از قبل این قابلیت) ناسازگار بود و backup_command
        # خالی بود، هرگز به مسیر سیسکو (show running-config +
        # clean_config_for_restore) نمی‌افتد - چون آن پردازش کاملاً
        # مخصوص سینتکس سیسکوست و روی خروجی یک دستگاه دیگر بی‌معنی و حتی
        # گمراه‌کننده خواهد بود (یک فایل "بک‌آپ" ذخیره می‌شود که در واقع
        # پیام خطای دستگاه غیر سیسکو، پاک‌سازی‌شده با قوانین سیسکو، است).
        if not backup_command:
            logger.error(
                "Device '%s' (%s) has a non-Cisco device type ('%s') but no "
                "backup command is configured for it. Skipping backup - edit "
                "the device and set a backup command first.",
                selected_device.get("name", hostname),
                params["host"],
                device_type,
            )
            audit_log.log_event(
                "BACKUP_SKIPPED",
                f"hostname={hostname} host={params['host']} reason=non-cisco device with no backup_command configured",
                level="WARNING",
            )
            conn.disconnect()
            return

        disable_paging_command = selected_device.get("disable_paging_command")
        if disable_paging_command:
            try:
                conn.send_command(disable_paging_command, read_timeout=15)
            except Exception as e:  # noqa: BLE001 - best-effort, backup still proceeds without it
                logger.warning(
                    "Failed to send the pagination-disable command on %s: %s", params["host"], e
                )
        raw_output = conn.send_command(backup_command, read_timeout=30)
        filepath = save_backup(hostname, raw_output, settings["backup_path"], settings["retention_count"])
        logger.info("Config backup (custom command: '%s') saved to: %s", backup_command, filepath)
    else:
        ensure_enable_mode(conn, params["host"])
        raw_config = get_running_config(conn)
        cleaned = clean_config_for_restore(raw_config)
        filepath = save_backup(hostname, cleaned, settings["backup_path"], settings["retention_count"])
        logger.info("Config backup saved to: %s", filepath)

    audit_log.log_event("BACKUP_SUCCESS", f"hostname={hostname} host={params['host']} file={filepath}")
    conn.disconnect()


def run_scheduled_backup_job(devices: list, settings: dict) -> None:
    """
    یک دور کامل بک‌آپ روی همه‌ی دستگاه‌هایی که auto_backup=True دارند.
    این تابع همانی است که APScheduler به‌صورت دوره‌ای صدا می‌زند.
    خطای هر دستگاه مستقل مدیریت می‌شود تا یک دستگاه از‌کاراُفتاده بقیه
    را متوقف نکند (run_backup خودش try/except دارد).
    """
    auto_devices = [d for d in devices if d.get("auto_backup")]
    if not auto_devices:
        logger.info("No devices are marked for scheduled auto-backup (see 'Edit device').")
        return

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info("Running scheduled backup for %d device(s) at %s", len(auto_devices), timestamp)
    for d in auto_devices:
        run_backup(d, settings)


def start_scheduler(devices: list, settings: dict) -> None:
    """
    APScheduler را با فاصله‌ی زمانی تنظیم‌شده در settings راه‌اندازی
    می‌کند. اولین اجرا بلافاصله انجام می‌شود، بعد طبق interval تکرار
    می‌شود. این حالت بلاک‌کننده است (تا Ctrl+C).
    """
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
    except ModuleNotFoundError:
        logger.error("APScheduler is not installed. Install it with: pip install apscheduler")
        return

    scheduler = BlockingScheduler()
    audit_log.log_event(
        "SCHEDULER_STARTED",
        f"schedule_type={settings.get('schedule_type')} time={settings.get('schedule_time')} "
        f"devices_marked_for_auto_backup={sum(1 for d in devices if d.get('auto_backup'))}",
    )

    schedule_type = settings.get("schedule_type", "daily")
    schedule_time = settings.get("schedule_time", "00:00")
    try:
        hour, minute = map(int, schedule_time.split(":"))
    except Exception as e:
        logger.error("Invalid schedule_time value %r: %s", schedule_time, e)
        return

    if schedule_type == "weekly":
        weekday = settings.get("schedule_day_of_week", "monday")
        weekday_aliases = {
            "monday": "mon",
            "tuesday": "tue",
            "wednesday": "wed",
            "thursday": "thu",
            "friday": "fri",
            "saturday": "sat",
            "sunday": "sun",
        }
        weekday = weekday_aliases.get(str(weekday).strip().lower(), str(weekday))
        if weekday not in weekday_aliases.values():
            logger.error("Invalid schedule_day_of_week value %r. Use monday..sunday.", settings.get("schedule_day_of_week"))
            return

        scheduler.add_job(
            run_scheduled_backup_job,
            "cron",
            day_of_week=weekday,
            hour=hour,
            minute=minute,
            args=[devices, settings],
        )
        logger.info(
            "Scheduled auto-backup started - every %s at %s. Press Ctrl+C to stop and return to the menu.",
            schedule_type,
            schedule_time,
        )
    elif schedule_type == "monthly":
        try:
            day_of_month = int(settings.get("schedule_day_of_month", 1))
        except Exception as e:
            logger.error("Invalid schedule_day_of_month value %r: %s", settings.get("schedule_day_of_month"), e)
            return

        scheduler.add_job(
            run_scheduled_backup_job,
            "cron",
            day=day_of_month,
            hour=hour,
            minute=minute,
            args=[devices, settings],
        )
        logger.info(
            "Scheduled auto-backup started - every %s day %s at %s. Press Ctrl+C to stop and return to the menu.",
            schedule_type,
            day_of_month,
            schedule_time,
        )
    else:
        scheduler.add_job(
            run_scheduled_backup_job,
            "cron",
            hour=hour,
            minute=minute,
            args=[devices, settings],
        )
        logger.info(
            "Scheduled auto-backup started - every %s at %s. Press Ctrl+C to stop and return to the menu.",
            schedule_type,
            schedule_time,
        )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")


def print_auto_backup_configuration_summary(devices: list, settings: dict) -> None:
    auto_devices = [d for d in devices if d.get("auto_backup")]
    print("\n--- Scheduled auto-backup configuration summary ---")
    if auto_devices:
        print("Devices included in scheduled auto-backup:")
        for d in auto_devices:
            core_tag = " [CORE]" if d.get("is_core") else ""
            print(f"  - {d['name']} ({d['host']}){core_tag}")
    else:
        print("No devices are currently selected for scheduled auto-backup.")

    print(f"Schedule type: {settings.get('schedule_type', 'daily')}")
    print(f"Schedule time: {settings.get('schedule_time', '00:00')}")
    if settings.get('schedule_type') == 'weekly':
        print(f"Day of week: {settings.get('schedule_day_of_week')}")
    if settings.get('schedule_type') == 'monthly':
        print(f"Day of month: {settings.get('schedule_day_of_month')}")
    print(f"Backups to keep per device: {settings.get('retention_count')}")
    print(f"Backup path: {settings.get('backup_path')}")
    print("---------------------------------------------------\n")


# ---------------------------------------------------------------------------
# بخش ۱۰: اجرای بدون تعامل (headless) - برای استارتاپ خودکار ویندوز
# ---------------------------------------------------------------------------
def _running_as_frozen_exe() -> bool:
    """True اگر برنامه با PyInstaller به exe تبدیل شده و همین‌طور اجرا می‌شود."""
    return getattr(sys, "frozen", False)


def enable_unattended_startup_interactive(master_password: str) -> None:
    """
    پسورد master را (با تأیید صریح کاربر) با DPAPI رمزنگاری و ذخیره
    می‌کند، سپس دستور دقیق ثبت Task Scheduler را برای اجرای خودکار در
    استارتاپ ویندوز چاپ می‌کند.
    """
    import windows_credential_store as wcs

    if not wcs.is_available():
        print(
            "This feature requires Windows with the 'pywin32' package installed "
            "(pip install pywin32). Not available on this system."
        )
        return

    print(
        "\nThis will save your master password locally, encrypted with "
        "Windows' Data Protection API (DPAPI). It can only be decrypted by "
        "this exact Windows user account on this exact machine - it is not "
        "stored in plain text, and copying the file to another PC or user "
        "account will not work there.\n"
        "\n"
        "Important: anyone who can log in as this Windows user (or run code "
        "as this user) will effectively be able to unlock your encrypted "
        "device list too, since unattended mode needs to decrypt it without "
        "asking anyone anything. Only enable this on a machine/account you "
        "trust and control.\n"
    )
    confirm = input("Proceed and save the master password for unattended mode? (y/n): ").strip().lower()
    if confirm != "y":
        print("Cancelled.")
        return

    wcs.save_master_password(master_password, BASE_DIR)
    audit_log.log_event(
        "UNATTENDED_STARTUP_ENABLED",
        "Master password saved via DPAPI for headless/unattended mode",
        level="WARNING",
    )

    if _running_as_frozen_exe():
        program = sys.executable
        arguments = "--service"
    else:
        program = sys.executable
        arguments = f'"{os.path.abspath(__file__)}" --service'

    print(
        "\nMaster password saved securely for unattended mode.\n\n"
        "Next step: register a Windows Task Scheduler entry so this program "
        "starts automatically at boot and only runs the scheduler (no menu, "
        "no prompts). From an elevated Command Prompt:\n\n"
        "  schtasks /create /tn \"CiscoMgmtAutoBackup\" "
        f"/tr \"\\\"{program}\\\" {arguments}\" "
        "/sc onstart /ru SYSTEM /rl highest\n\n"
        "Or, in Task Scheduler's GUI: create a task with trigger 'At "
        "startup', action = run the program above with the arguments shown, "
        "and check 'Run whether user is logged on or not'.\n\n"
        "To verify it's working after a reboot, check Task Scheduler's "
        "history for 'CiscoMgmtAutoBackup', or look for new files under "
        f"your backup path ({backup_settings.load_settings()['backup_path']})."
    )


def disable_unattended_startup_interactive() -> None:
    import windows_credential_store as wcs

    if not wcs.is_available():
        print("This feature requires Windows with the 'pywin32' package installed.")
        return

    if not wcs.has_saved_password(BASE_DIR):
        print("Unattended mode is not currently enabled (no saved password found).")
        return

    wcs.remove_saved_master_password(BASE_DIR)
    audit_log.log_event("UNATTENDED_STARTUP_DISABLED", "Saved master password removed")
    print(
        "Saved master password removed - unattended mode will no longer work.\n"
        "Don't forget to also remove the Task Scheduler entry if you created "
        "one:\n"
        "  schtasks /delete /tn \"CiscoMgmtAutoBackup\" /f"
    )


def run_headless_service() -> None:
    """
    نقطه‌ی ورود حالت headless - بدون منو، بدون درخواست پسورد از کاربر.
    فقط زمانی کار می‌کند که پسورد master قبلاً از طریق منوی
    'Backup > Enable unattended startup' با DPAPI ذخیره شده باشد.
    این تابع مستقیماً از '--service' در انتهای فایل صدا زده می‌شود.
    """
    import windows_credential_store as wcs

    if not wcs.is_available():
        logger.error(
            "Unattended mode requires Windows with the 'pywin32' package "
            "installed (pip install pywin32). Exiting."
        )
        audit_log.log_event(
            "HEADLESS_SERVICE_START_FAILED",
            "pywin32/DPAPI not available on this system",
            level="ERROR",
        )
        sys.exit(1)

    master_password = wcs.load_master_password(BASE_DIR)
    if master_password is None:
        logger.error(
            "No saved master password found for unattended mode. Run the "
            "program interactively first and use 'Backup > Enable "
            "unattended startup' to save it."
        )
        audit_log.log_event(
            "HEADLESS_SERVICE_START_FAILED",
            "No saved master password found",
            level="ERROR",
        )
        sys.exit(1)

    try:
        devices = device_manager.load_devices(master_password)
    except ValueError as e:
        logger.error("Could not decrypt the device list with the saved master password: %s", e)
        audit_log.log_event(
            "HEADLESS_SERVICE_START_FAILED",
            "Saved master password could not decrypt the device list (may have been changed)",
            level="ERROR",
        )
        sys.exit(1)

    settings = backup_settings.load_settings()
    logger.info("Starting in unattended (service) mode - scheduled auto-backup only.")
    audit_log.log_event("HEADLESS_SERVICE_STARTED", f"{len(devices)} device(s) loaded")
    start_scheduler(devices, settings)


def print_main_menu() -> None:
    print("\n=== Cisco Switch Management Tool ===")
    print("[1] Device Management")
    print("[2] IP Discovery by Port")
    print("[3] Backup")
    print("[4] Config Drift Detection")
    print("[5] Idle Ports Report")
    print("[6] Device Inventory Report (model / serial / IOS version)")
    print("[7] Exit")


MAX_MASTER_PASSWORD_ATTEMPTS = 3


def main():
    print("=== Cisco Switch Management Tool ===")
    audit_log.log_event("APP_START", "Interactive session started")

    devices = None
    master_password = None
    for attempt in range(1, MAX_MASTER_PASSWORD_ATTEMPTS + 1):
        master_password = getpass.getpass("Enter master password (used to encrypt/decrypt the device list): ")
        try:
            devices = device_manager.load_devices(master_password)
            break
        except ValueError as e:
            remaining = MAX_MASTER_PASSWORD_ATTEMPTS - attempt
            if remaining > 0:
                print(f"Error: {e} ({remaining} attempt(s) remaining)")
            else:
                print(f"Error: {e}")
                print("Too many failed master password attempts. Exiting.")
                audit_log.log_event(
                    "MASTER_PW_LOCKOUT",
                    f"Exceeded {MAX_MASTER_PASSWORD_ATTEMPTS} failed master password attempts - exiting",
                    level="ERROR",
                )
                return

    settings = backup_settings.load_settings()

    while True:
        print_main_menu()
        choice = input("Enter your choice (1-7): ").strip()

        if choice == "1":
            while True:
                print("\n--- Device Management ---")
                print("1. Add device")
                print("2. Edit device")
                print("3. List of devices")
                print("4. Remove device")
                print("0. Back to main menu")
                sub_choice = input("Enter your choice: ").strip()
                if sub_choice == "1":
                    device_manager.add_device_interactive(devices)
                    device_manager.save_devices(devices, master_password)
                elif sub_choice == "2":
                    device_manager.edit_device_interactive(devices)
                    device_manager.save_devices(devices, master_password)
                elif sub_choice == "3":
                    device_manager.list_devices_cli(devices)
                elif sub_choice == "4":
                    device_manager.remove_device_interactive(devices)
                    device_manager.save_devices(devices, master_password)
                elif sub_choice == "0":
                    break
                else:
                    logger.warning("Invalid option selected: %s", sub_choice)
        elif choice == "2":
            while True:
                print("\n--- IP Discovery by Port ---")
                print("1. Show topology report")
                print("0. Back to main menu")
                sub_choice = input("Enter your choice: ").strip()
                if sub_choice == "1":
                    selected = device_manager.select_device_raw(devices)
                    if selected:
                        run_topology_report(selected, devices)
                elif sub_choice == "0":
                    break
                else:
                    logger.warning("Invalid option selected: %s", sub_choice)
        elif choice == "3":
            while True:
                print("\n--- Backup ---")
                print("1. One-time backup")
                print("2. Configure auto-backup")
                print("3. Start scheduled backup")
                print("4. Enable unattended startup on Windows boot (Task Scheduler)")
                print("5. Disable unattended startup")
                print("0. Back to main menu")
                sub_choice = input("Enter your choice: ").strip()
                if sub_choice == "1":
                    selected = device_manager.select_device_raw(devices)
                    if selected:
                        run_backup(selected, settings)
                elif sub_choice == "2":
                    device_manager.configure_auto_backup_devices_interactive(devices)
                    device_manager.save_devices(devices, master_password)
                    settings = backup_settings.configure_settings_interactive()
                    print_auto_backup_configuration_summary(devices, settings)
                elif sub_choice == "3":
                    start_scheduler(devices, settings)
                elif sub_choice == "4":
                    enable_unattended_startup_interactive(master_password)
                elif sub_choice == "5":
                    disable_unattended_startup_interactive()
                elif sub_choice == "0":
                    break
                else:
                    logger.warning("Invalid option selected: %s", sub_choice)
        elif choice == "4":
            while True:
                print("\n--- Config Drift Detection ---")
                print("1. Check drift for one device")
                print("2. Check drift for all devices with backups")
                print("3. View backup history for a device")
                print("0. Back to main menu")
                sub_choice = input("Enter your choice: ").strip()
                if sub_choice == "1":
                    hostname = select_backup_hostname(settings["backup_path"])
                    if hostname:
                        check_drift_for_device(hostname, settings["backup_path"])
                elif sub_choice == "2":
                    check_drift_all_devices(settings["backup_path"])
                elif sub_choice == "3":
                    hostname = select_backup_hostname(settings["backup_path"])
                    if hostname:
                        print_backup_history(hostname, settings["backup_path"])
                elif sub_choice == "0":
                    break
                else:
                    logger.warning("Invalid option selected: %s", sub_choice)
        elif choice == "5":
            while True:
                print("\n--- Idle Ports Report ---")
                print("1. Run report for a device")
                print("0. Back to main menu")
                sub_choice = input("Enter your choice: ").strip()
                if sub_choice == "1":
                    selected = device_manager.select_device_raw(devices)
                    if selected:
                        run_idle_ports_report(selected)
                elif sub_choice == "0":
                    break
                else:
                    logger.warning("Invalid option selected: %s", sub_choice)
        elif choice == "6":
            while True:
                print("\n--- Device Inventory Report ---")
                print("1. Run report for one device")
                print("2. Run report for all stored devices")
                print("0. Back to main menu")
                sub_choice = input("Enter your choice: ").strip()
                if sub_choice == "1":
                    selected = device_manager.select_device_raw(devices)
                    if selected:
                        run_inventory_report_one(selected)
                elif sub_choice == "2":
                    run_inventory_report_all(devices)
                elif sub_choice == "0":
                    break
                else:
                    logger.warning("Invalid option selected: %s", sub_choice)
        elif choice == "7":
            logger.info("Goodbye.")
            audit_log.log_event("APP_EXIT", "Interactive session ended normally")
            break
        else:
            logger.warning("Invalid option selected: %s", choice)


if __name__ == "__main__":
    if "--service" in sys.argv:
        run_headless_service()
    else:
        main()