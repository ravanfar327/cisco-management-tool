"""
gui_pages_inventory.py
صفحه‌ی «Device Inventory Report» - مدل، سریال، و ورژن IOS هر دستگاه.
مستقیماً از collect_inventory_row (تابع بک‌اند موجود که خودش خطای هر
دستگاه را مستقل مدیریت می‌کند) استفاده می‌کند.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView,
)
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtCore import QUrl

import cisco_mgmt
from gui_workers import Worker

ERROR_ROW_COLOR = QColor("#3a1414")


def _collect_all(devices: list) -> list:
    return [cisco_mgmt.collect_inventory_row(d, debug=False) for d in devices]


class InventoryPage(QWidget):
    def __init__(self, devices: list, parent=None):
        super().__init__(parent)
        self.devices = devices
        self._worker: Worker | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        title = QLabel("Device Inventory Report")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Model, serial number, and IOS version for every stored device.")
        subtitle.setObjectName("PageSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        control_row = QHBoxLayout()
        self.run_button = QPushButton("Run inventory report")
        self.run_button.setObjectName("PrimaryButton")
        self.run_button.clicked.connect(self._run_report)
        control_row.addWidget(self.run_button)
        control_row.addStretch()
        layout.addLayout(control_row)

        self.status_label = QLabel("")
        self.status_label.setObjectName("HintLabel")
        layout.addWidget(self.status_label)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Device", "Host", "Model", "Serial", "IOS Version"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setMinimumSectionSize(60)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table, stretch=1)

        notice = QLabel(cisco_mgmt.VERSION_CHECK_NOTICE)
        notice.setObjectName("HintLabel")
        notice.setWordWrap(True)
        layout.addWidget(notice)

        link_row = QHBoxLayout()
        open_link_button = QPushButton("Open Cisco Software Download page")
        open_link_button.clicked.connect(self._open_cisco_download_page)
        link_row.addWidget(open_link_button)
        link_row.addStretch()
        layout.addLayout(link_row)

        self._update_button_state()

    def _open_cisco_download_page(self) -> None:
        QDesktopServices.openUrl(QUrl(cisco_mgmt.CISCO_SOFTWARE_DOWNLOAD_URL))

    def refresh_devices(self, devices: list) -> None:
        self.devices = devices
        self._update_button_state()

    def _update_button_state(self) -> None:
        busy = self._worker is not None and self._worker.isRunning()
        self.run_button.setEnabled(not busy and len(self.devices) > 0)

    def _run_report(self) -> None:
        if not self.devices:
            return
        self.run_button.setEnabled(False)
        self.status_label.setText(f"Connecting to {len(self.devices)} device(s)...")
        self.table.setRowCount(0)

        self._worker = Worker(_collect_all, self.devices)
        self._worker.finished_ok.connect(self._on_report_done)
        self._worker.finished_error.connect(self._on_report_error)
        self._worker.start()

    def _on_report_done(self, rows: list) -> None:
        self._worker = None
        self._update_button_state()

        error_count = sum(1 for r in rows if r.get("error"))
        self.status_label.setText(f"{len(rows)} device(s) checked, {error_count} error(s).")

        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            if row.get("error"):
                values = [row["label"], row["host"], f"ERROR: {row['error']}", "", ""]
            else:
                values = [
                    row.get("hostname") or row["label"],
                    row["host"],
                    row.get("model") or "?",
                    row.get("serial") or "?",
                    row.get("version") or "?",
                ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if row.get("error"):
                    item.setBackground(ERROR_ROW_COLOR)
                self.table.setItem(row_index, col, item)

        self.table.resizeColumnsToContents()

    def _on_report_error(self, error_text: str) -> None:
        self._worker = None
        self._update_button_state()
        self.status_label.setText(f"Report failed unexpectedly: {error_text}")
