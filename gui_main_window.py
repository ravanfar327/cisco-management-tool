"""
main_window.py
پنجره‌ی اصلی برنامه: یک نوار کناری برای ناوبری + یک QStackedWidget برای
صفحات. تمام صفحه‌ها کاملاً کاربردی‌اند و به همان توابع بک‌اند تست‌شده‌ی
CLI وصل‌اند - هیچ منطقی اینجا بازنویسی نشده.
"""

import re

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QStackedWidget, QButtonGroup, QFrame, QStatusBar, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView,
)

import backup_settings
import audit_log
from gui_theme import build_stylesheet
from gui_pages_devices import DevicesPage
from gui_pages_backup import BackupPage
from gui_pages_settings import SettingsPage
from gui_pages_drift import ConfigDriftPage
from gui_pages_idle_ports import IdlePortsPage
from gui_pages_inventory import InventoryPage
from gui_pages_audit_log import AuditLogPage
from gui_pages_ip_discovery import IpDiscoveryPage


def _get_last_backup_times() -> dict:
    """
    از security_audit.log آخرین زمان هر رویداد BACKUP_SUCCESS را بر
    اساس host= استخراج می‌کند. چون خطوط لاگ به ترتیب زمانی نوشته
    می‌شوند، کافی است فایل را خط‌به‌خط بخوانیم؛ آخرین مقداری که برای هر
    host نوشته می‌شود همان جدیدترین بک‌آپ موفق است.
    """
    times: dict[str, str] = {}
    try:
        with open(audit_log.AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if "BACKUP_SUCCESS" not in line:
                    continue
                match = re.search(r"host=(\S+)", line)
                if not match:
                    continue
                timestamp = line.split(" | ", 1)[0].strip()
                times[match.group(1)] = timestamp
    except FileNotFoundError:
        pass
    return times


class DashboardPage(QWidget):
    def __init__(self, devices: list, settings: dict, parent=None):
        super().__init__(parent)
        self.devices = devices
        self.settings = settings

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        title = QLabel("Dashboard")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Quick overview of your network devices.")
        subtitle.setObjectName("PageSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(14)
        self._device_count_label = self._add_stat_card(cards_row, "Devices", "0")
        self._auto_backup_count_label = self._add_stat_card(cards_row, "Auto-backup enabled", "0")
        self._schedule_label = self._add_stat_card(cards_row, "Schedule", "-")
        self._schedule_label.setStyleSheet("font-size: 16px; font-weight: 700;")
        layout.addLayout(cards_row)

        last_backup_label = QLabel("Last successful backup per device")
        last_backup_label.setStyleSheet("font-weight: 600; font-size: 14px; margin-top: 8px;")
        layout.addWidget(last_backup_label)

        self.last_backup_table = QTableWidget(0, 3)
        self.last_backup_table.setHorizontalHeaderLabels(["Device", "Host", "Last successful backup"])
        self.last_backup_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.last_backup_table.horizontalHeader().setStretchLastSection(True)
        self.last_backup_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.last_backup_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.last_backup_table.setAlternatingRowColors(True)
        self.last_backup_table.verticalHeader().setVisible(False)
        layout.addWidget(self.last_backup_table, stretch=1)

        self.refresh()

    def _add_stat_card(self, row: QHBoxLayout, label: str, value: str) -> QLabel:
        card = QFrame()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 16, 18, 16)

        value_label = QLabel(value)
        value_label.setStyleSheet("font-size: 26px; font-weight: 700;")
        caption_label = QLabel(label)
        caption_label.setObjectName("FieldLabel")

        card_layout.addWidget(value_label)
        card_layout.addWidget(caption_label)
        row.addWidget(card)
        return value_label

    def refresh(self) -> None:
        self._device_count_label.setText(str(len(self.devices)))
        auto_count = sum(1 for d in self.devices if d.get("auto_backup"))
        self._auto_backup_count_label.setText(str(auto_count))
        schedule_type = self.settings.get("schedule_type", "daily")
        schedule_time = self.settings.get("schedule_time", "00:00")
        if schedule_type == "weekly":
            weekday = self.settings.get("schedule_day_of_week", "mon").capitalize()
            schedule_text = f"weekly · {weekday} @ {schedule_time}"
        elif schedule_type == "monthly":
            day_of_month = self.settings.get("schedule_day_of_month", 1)
            schedule_text = f"monthly · day {day_of_month} @ {schedule_time}"
        else:
            schedule_text = f"daily @ {schedule_time}"
        self._schedule_label.setText(schedule_text)

        last_backup_times = _get_last_backup_times()
        self.last_backup_table.setRowCount(len(self.devices))
        for row, d in enumerate(self.devices):
            host = d.get("host", "")
            last_backup = last_backup_times.get(host, "Never")
            self.last_backup_table.setItem(row, 0, QTableWidgetItem(d.get("name", "")))
            self.last_backup_table.setItem(row, 1, QTableWidgetItem(host))
            self.last_backup_table.setItem(row, 2, QTableWidgetItem(last_backup))


class MainWindow(QMainWindow):
    def __init__(self, devices: list, master_password: str, app):
        super().__init__()
        self.devices = devices
        self.master_password = master_password
        self.app = app
        self.settings = backup_settings.load_settings()

        self.setWindowTitle("Cisco Switch Management Tool")
        self.resize(1080, 680)
        self.setMinimumSize(900, 560)

        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # --- Sidebar ---
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(220)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 12)
        sidebar_layout.setSpacing(2)

        app_title = QLabel("Cisco Mgmt Tool")
        app_title.setObjectName("AppTitle")
        app_subtitle = QLabel("Switch management & backup")
        app_subtitle.setObjectName("AppSubtitle")
        sidebar_layout.addWidget(app_title)
        sidebar_layout.addWidget(app_subtitle)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)

        self.stack = QStackedWidget()

        self.dashboard_page = DashboardPage(self.devices, self.settings)
        self.devices_page = DevicesPage(self.devices, self.master_password)
        self.ip_discovery_page = IpDiscoveryPage(self.devices)
        self.backup_page = BackupPage(self.devices, self.settings)
        self.drift_page = ConfigDriftPage(self.settings)
        self.idle_ports_page = IdlePortsPage(self.devices)
        self.inventory_page = InventoryPage(self.devices)
        self.settings_page = SettingsPage(
            self.settings,
            self.devices,
            self.master_password,
            self._on_password_changed,
            self._on_theme_changed,
        )
        self.audit_log_page = AuditLogPage()

        nav_items = [
            ("Dashboard", self.dashboard_page, True),
            ("Devices", self.devices_page, True),
            ("IP Discovery", self.ip_discovery_page, True),
            ("Backup", self.backup_page, True),
            ("Config Drift", self.drift_page, True),
            ("Idle Ports", self.idle_ports_page, True),
            ("Inventory", self.inventory_page, True),
            ("Settings", self.settings_page, True),
            ("Audit Log", self.audit_log_page, True),
        ]

        for index, (label, page, enabled) in enumerate(nav_items):
            button = QPushButton(label)
            button.setObjectName("NavButton")
            button.setCheckable(True)
            button.setEnabled(enabled)
            if not enabled:
                button.setToolTip("Coming soon - available in the CLI today")
            self.nav_group.addButton(button, index)
            sidebar_layout.addWidget(button)
            self.stack.addWidget(page)

        sidebar_layout.addStretch()
        self.nav_group.buttons()[0].setChecked(True)
        self.nav_group.idClicked.connect(self.stack.setCurrentIndex)

        root_layout.addWidget(sidebar)
        root_layout.addWidget(self.stack, stretch=1)

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage(f"{len(self.devices)} device(s) loaded")

        # وقتی دستگاه‌ها از صفحه‌ی Devices تغییر می‌کنند، Dashboard و Backup
        # هم باید به‌روزرسانی شوند - چون DevicesPage روی همان لیست self.devices
        # (به‌صورت رفرنس) کار می‌کند، کافی است بعد از هر تغییر رفرش کنیم.
        self.stack.currentChanged.connect(self._on_page_changed)

    def _on_page_changed(self, index: int) -> None:
        self.dashboard_page.refresh()
        self.backup_page.refresh_devices(self.devices)
        self.ip_discovery_page.refresh_devices(self.devices)
        self.idle_ports_page.refresh_devices(self.devices)
        self.inventory_page.refresh_devices(self.devices)
        if self.stack.widget(index) is self.audit_log_page:
            self.audit_log_page._refresh()
        self.statusBar().showMessage(f"{len(self.devices)} device(s) loaded")

    def _on_password_changed(self, new_password: str) -> None:
        """
        وقتی از صفحه‌ی Settings پسورد master تغییر کند، این callback صدا
        زده می‌شود تا همه‌ی صفحاتی که یک کپی از پسورد قدیمی نگه داشته‌اند
        (برای صدا زدن device_manager.save_devices) به‌روز شوند.
        """
        self.master_password = new_password
        self.devices_page.master_password = new_password

    def _on_theme_changed(self, theme: str) -> None:
        self.app.setStyleSheet(build_stylesheet(theme))
