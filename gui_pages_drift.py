"""
gui_pages_drift.py
صفحه‌ی «Config Drift» - مقایسه‌ی دو بک‌آپ آخر یک دستگاه (یا همه‌ی
دستگاه‌ها) و نمایش diff. مستقیماً از همان توابع بک‌اند CLI استفاده
می‌کند (list_backed_up_hostnames, diff_latest_two_backups) - هیچ منطق
مقایسه‌ای اینجا بازنویسی نشده.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QPlainTextEdit,
)

import cisco_mgmt


class ConfigDriftPage(QWidget):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.settings = settings

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        title = QLabel("Config Drift Detection")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Compare each device's latest backup against the one before it.")
        subtitle.setObjectName("PageSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        selector_row = QHBoxLayout()
        selector_row.addWidget(QLabel("Device:"))
        self.device_selector = QComboBox()
        selector_row.addWidget(self.device_selector, stretch=1)
        layout.addLayout(selector_row)

        button_row = QHBoxLayout()
        self.check_selected_button = QPushButton("Check drift for this device")
        self.check_selected_button.setObjectName("PrimaryButton")
        self.check_selected_button.clicked.connect(self._check_selected)
        button_row.addWidget(self.check_selected_button)

        self.check_all_button = QPushButton("Check drift for all devices")
        self.check_all_button.clicked.connect(self._check_all)
        button_row.addWidget(self.check_all_button)

        self.refresh_button = QPushButton("Refresh device list")
        self.refresh_button.clicked.connect(self._refresh_device_list)
        button_row.addWidget(self.refresh_button)

        button_row.addStretch()
        layout.addLayout(button_row)

        self.output = QPlainTextEdit()
        self.output.setObjectName("LogConsole")
        self.output.setReadOnly(True)
        layout.addWidget(self.output, stretch=1)

        self._refresh_device_list()

    def _backup_dir(self) -> str:
        return self.settings.get("backup_path", "")

    def _refresh_device_list(self) -> None:
        self.device_selector.clear()
        hostnames = cisco_mgmt.list_backed_up_hostnames(self._backup_dir())
        if not hostnames:
            self.device_selector.addItem("(no backups found yet)")
            self.check_selected_button.setEnabled(False)
        else:
            self.device_selector.addItems(hostnames)
            self.check_selected_button.setEnabled(True)

    def _check_selected(self) -> None:
        hostname = self.device_selector.currentText()
        if not hostname or hostname.startswith("("):
            return
        self._print_drift_for_device(hostname)

    def _print_drift_for_device(self, hostname: str) -> bool:
        """پرینت وضعیت درفت یک دستگاه در کنسول. True یعنی تغییری پیدا شد."""
        diff_text = cisco_mgmt.diff_latest_two_backups(self._backup_dir(), hostname)
        if diff_text is None:
            self.output.appendPlainText(f"{hostname}: fewer than 2 backups exist yet - nothing to compare.")
            return False
        if diff_text == "":
            self.output.appendPlainText(f"{hostname}: no configuration changes since the previous backup.")
            return False

        self.output.appendPlainText(f"\n=== Config drift detected: {hostname} ===")
        self.output.appendPlainText(diff_text)
        self.output.appendPlainText("")
        return True

    def _check_all(self) -> None:
        hostnames = cisco_mgmt.list_backed_up_hostnames(self._backup_dir())
        if not hostnames:
            self.output.appendPlainText("No backups have been taken yet.")
            return

        self.output.appendPlainText(f"--- Checking {len(hostnames)} device(s) for config drift ---")
        changed_count = 0
        for hostname in hostnames:
            if self._print_drift_for_device(hostname):
                changed_count += 1
        self.output.appendPlainText(
            f"--- Checked {len(hostnames)} device(s); {changed_count} had configuration drift. ---\n"
        )
