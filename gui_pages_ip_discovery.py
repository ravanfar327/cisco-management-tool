"""
gui_pages_ip_discovery.py
صفحه‌ی «IP Discovery by Port» - معادل GUI منوی CLI شماره ۲. دقیقاً از
get_topology_report_data (تابع بک‌اند مشترک با CLI) استفاده می‌کند.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
)

import cisco_mgmt
from gui_workers import Worker


class IpDiscoveryPage(QWidget):
    def __init__(self, devices: list, parent=None):
        super().__init__(parent)
        self.devices = devices
        self._worker: Worker | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        title = QLabel("IP Discovery by Port")
        title.setObjectName("PageTitle")
        subtitle = QLabel(
            "Find which switch and physical port an IP/MAC address is connected to. "
            "Select the core switch to see the full topology, or an access switch to "
            "see only its own ports."
        )
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        control_row = QHBoxLayout()
        self.device_selector = QComboBox()
        self.device_selector.setMinimumWidth(240)
        control_row.addWidget(self.device_selector)

        self.run_button = QPushButton("Run topology report")
        self.run_button.setObjectName("PrimaryButton")
        self.run_button.clicked.connect(self._run_report)
        control_row.addWidget(self.run_button)
        control_row.addStretch()
        layout.addLayout(control_row)

        self.status_label = QLabel("")
        self.status_label.setObjectName("HintLabel")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Device", "Port", "IP Address", "MAC Address", "VLAN"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setMinimumSectionSize(60)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table, stretch=1)

        self._refresh_device_list()

    def refresh_devices(self, devices: list) -> None:
        self.devices = devices
        self._refresh_device_list()

    def _refresh_device_list(self) -> None:
        current = self.device_selector.currentText()
        self.device_selector.clear()
        for d in self.devices:
            core_tag = " [CORE]" if d.get("is_core") else ""
            self.device_selector.addItem(f"{d.get('name')} ({d.get('host')}){core_tag}", d)
        if current:
            idx = self.device_selector.findText(current)
            if idx >= 0:
                self.device_selector.setCurrentIndex(idx)
        self.run_button.setEnabled(self.device_selector.count() > 0)

    def _run_report(self) -> None:
        index = self.device_selector.currentIndex()
        if index < 0:
            return
        device = self.device_selector.itemData(index)
        if device is None:
            return

        self.run_button.setEnabled(False)
        self.status_label.setText(f"Scanning topology from {device.get('host')} - this can take a while...")
        self.table.setRowCount(0)

        self._worker = Worker(cisco_mgmt.get_topology_report_data, device, self.devices, False)
        self._worker.finished_ok.connect(self._on_report_done)
        self._worker.finished_error.connect(self._on_report_error)
        self._worker.start()

    def _on_report_done(self, result: dict) -> None:
        self.run_button.setEnabled(True)

        if not result["ok"]:
            self.status_label.setText(f"Error: {result['error']}")
            return

        entries = result["entries"]
        mode = result["mode"]

        if mode == "core":
            self.status_label.setText(f"Full topology - {len(entries)} entrie(s) found.")
        elif mode == "access_not_found":
            known = sorted({e["device"] for e in entries if e.get("device_serial")})
            if known:
                self.status_label.setText(
                    f"No ports found for {result['match_desc']}. Devices actually discovered in "
                    f"the topology: {', '.join(known)}"
                )
            else:
                self.status_label.setText(
                    "No devices were discovered in the topology at all "
                    "(check core connectivity/CDP)."
                )
            entries = []  # nothing device-specific to show in the table
        else:
            self.status_label.setText(f"Showing ports on {result['match_desc']} - {len(entries)} entrie(s).")

        rows = sorted(entries, key=lambda e: (e["device"], e["physical_port"]))
        self.table.setRowCount(len(rows))
        for row, e in enumerate(rows):
            values = [e["device"], e["physical_port"], e["ip"], e["mac"], e["vlan_interface"]]
            for col, value in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(str(value)))

        self.table.resizeColumnsToContents()

    def _on_report_error(self, error_text: str) -> None:
        self.run_button.setEnabled(True)
        self.status_label.setText(f"Topology scan failed unexpectedly: {error_text}")
