"""
pages_backup.py
صفحه‌ی «Backup» - اجرای بک‌آپ فوری (یک دستگاه یا همه‌ی دستگاه‌های
auto-backup) روی یک QThread جدا (چون اتصال SSH بلاک‌کننده است)، با یک
کنسول لاگ زنده که خروجی همان logger عملیاتی cisco_mgmt.py را نشان
می‌دهد.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QPlainTextEdit,
)
from PySide6.QtGui import QTextCursor
import logging

import cisco_mgmt
from gui_workers import Worker
from gui_log_bridge import QtLogHandler


class BackupPage(QWidget):
    def __init__(self, devices: list, settings: dict, parent=None):
        super().__init__(parent)
        self.devices = devices
        self.settings = settings
        self._worker: Worker | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        title = QLabel("Backup")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Run an on-demand backup. Scheduled auto-backup runs separately in the background.")
        subtitle.setObjectName("PageSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Name", "Host", "Auto-backup"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self._update_button_states)
        layout.addWidget(self.table, stretch=1)

        action_row = QHBoxLayout()
        self.run_selected_button = QPushButton("Run backup for selected device")
        self.run_selected_button.setObjectName("PrimaryButton")
        self.run_selected_button.clicked.connect(self._run_selected)
        self.run_all_button = QPushButton("Run backup for all auto-backup devices")
        self.run_all_button.clicked.connect(self._run_all)
        action_row.addWidget(self.run_selected_button)
        action_row.addWidget(self.run_all_button)
        action_row.addStretch()
        layout.addLayout(action_row)

        console_label = QLabel("Activity log")
        console_label.setObjectName("FieldLabel")
        layout.addWidget(console_label)

        self.console = QPlainTextEdit()
        self.console.setObjectName("LogConsole")
        self.console.setReadOnly(True)
        self.console.setMaximumBlockCount(2000)
        layout.addWidget(self.console, stretch=1)

        self._log_handler = QtLogHandler()
        self._log_handler.bridge.message.connect(self._append_log)
        logging.getLogger("cisco_mgmt").addHandler(self._log_handler)

        self._refresh_table()
        self._update_button_states()

    def refresh_devices(self, devices: list) -> None:
        """صدا زده می‌شود اگر لیست دستگاه‌ها از صفحه‌ی Devices تغییر کرده باشد."""
        self.devices = devices
        self._refresh_table()

    def _refresh_table(self) -> None:
        self.table.setRowCount(len(self.devices))
        for row, d in enumerate(self.devices):
            self.table.setItem(row, 0, QTableWidgetItem(d.get("name", "")))
            self.table.setItem(row, 1, QTableWidgetItem(d.get("host", "")))
            self.table.setItem(row, 2, QTableWidgetItem("Yes" if d.get("auto_backup") else ""))

    def _selected_device(self) -> dict | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        return self.devices[rows[0].row()]

    def _update_button_states(self) -> None:
        busy = self._worker is not None and self._worker.isRunning()
        self.run_selected_button.setEnabled(not busy and self._selected_device() is not None)
        self.run_all_button.setEnabled(not busy and any(d.get("auto_backup") for d in self.devices))

    def _append_log(self, text: str, level: str) -> None:
        self.console.appendPlainText(text)
        self.console.moveCursor(QTextCursor.MoveOperation.End)

    def _start_worker(self, fn, *args) -> None:
        self.run_selected_button.setEnabled(False)
        self.run_all_button.setEnabled(False)
        self._worker = Worker(fn, *args)
        self._worker.finished_ok.connect(self._on_worker_done)
        self._worker.finished_error.connect(self._on_worker_error)
        self._worker.start()

    def _run_selected(self) -> None:
        device = self._selected_device()
        if device is None:
            return
        self._append_log(f"--- Starting backup for {device.get('name')} ({device.get('host')}) ---", "INFO")
        self._start_worker(cisco_mgmt.run_backup, device, self.settings)

    def _run_all(self) -> None:
        count = sum(1 for d in self.devices if d.get("auto_backup"))
        self._append_log(f"--- Starting backup for {count} auto-backup device(s) ---", "INFO")
        self._start_worker(cisco_mgmt.run_scheduled_backup_job, self.devices, self.settings)

    def _on_worker_done(self, _result) -> None:
        self._append_log("--- Done ---", "INFO")
        self._worker = None
        self._update_button_states()

    def _on_worker_error(self, error_text: str) -> None:
        self._append_log(f"--- Backup failed unexpectedly: {error_text} ---", "ERROR")
        self._worker = None
        self._update_button_states()
