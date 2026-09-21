"""
pages_devices.py
صفحه‌ی «Devices» - جدول دستگاه‌های ذخیره‌شده + افزودن/ویرایش/حذف.
هر تغییر بلافاصله با device_manager.save_devices روی دیسک (رمزنگاری‌شده)
ذخیره می‌شود و در audit_log هم ثبت می‌شود - دقیقاً همان رفتار CLI.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QMessageBox, QDialog,
)

import device_manager
import audit_log
from gui_dialogs import DeviceDialog


class DevicesPage(QWidget):
    def __init__(self, devices: list, master_password: str, parent=None):
        super().__init__(parent)
        self.devices = devices
        self.master_password = master_password

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        header_row = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Devices")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Switches and other devices managed by this tool.")
        subtitle.setObjectName("PageSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header_row.addLayout(title_box)
        header_row.addStretch()

        self.add_button = QPushButton("+ Add device")
        self.add_button.setObjectName("PrimaryButton")
        self.add_button.clicked.connect(self._add_device)
        header_row.addWidget(self.add_button)
        layout.addLayout(header_row)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Name", "Host", "Port", "Type", "Core", "Auto-backup"]
        )
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self._update_button_states)
        self.table.doubleClicked.connect(lambda _: self._edit_device())
        layout.addWidget(self.table)

        action_row = QHBoxLayout()
        action_row.addStretch()
        self.edit_button = QPushButton("Edit selected")
        self.edit_button.clicked.connect(self._edit_device)
        self.remove_button = QPushButton("Remove selected")
        self.remove_button.setObjectName("DangerButton")
        self.remove_button.clicked.connect(self._remove_device)
        action_row.addWidget(self.edit_button)
        action_row.addWidget(self.remove_button)
        layout.addLayout(action_row)

        self._refresh_table()
        self._update_button_states()

    def _refresh_table(self) -> None:
        self.table.setRowCount(len(self.devices))
        for row, d in enumerate(self.devices):
            self.table.setItem(row, 0, QTableWidgetItem(d.get("name", "")))
            self.table.setItem(row, 1, QTableWidgetItem(d.get("host", "")))
            self.table.setItem(row, 2, QTableWidgetItem(str(d.get("port", 22))))
            self.table.setItem(row, 3, QTableWidgetItem(d.get("device_type", "")))
            self.table.setItem(row, 4, QTableWidgetItem("Yes" if d.get("is_core") else ""))
            self.table.setItem(row, 5, QTableWidgetItem("Yes" if d.get("auto_backup") else ""))

    def _selected_row(self) -> int | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        return rows[0].row()

    def _update_button_states(self) -> None:
        has_selection = self._selected_row() is not None
        self.edit_button.setEnabled(has_selection)
        self.remove_button.setEnabled(has_selection)

    def _persist(self) -> None:
        device_manager.save_devices(self.devices, self.master_password)

    def _add_device(self) -> None:
        dialog = DeviceDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.result_device:
            new_device = dialog.result_device
            self.devices.append(new_device)
            audit_log.log_event(
                "DEVICE_ADDED",
                f"name={new_device['name']} host={new_device['host']} port={new_device['port']} "
                f"type={new_device['device_type']} is_core={new_device['is_core']} "
                f"auto_backup={new_device['auto_backup']} (GUI)",
            )
            self._persist()
            self._refresh_table()

    def _edit_device(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        original = self.devices[row]
        dialog = DeviceDialog(existing_device=original, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.result_device:
            updated = dialog.result_device
            self.devices[row] = updated
            audit_log.log_event(
                "DEVICE_EDITED",
                f"device={original.get('name')} host={updated['host']} (GUI)",
            )
            self._persist()
            self._refresh_table()

    def _remove_device(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        device = self.devices[row]
        confirm = QMessageBox.question(
            self,
            "Remove device",
            f"Remove '{device.get('name')}' ({device.get('host')})? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self.devices.pop(row)
        audit_log.log_event(
            "DEVICE_REMOVED",
            f"name={device.get('name')} host={device.get('host')} (GUI)",
            level="WARNING",
        )
        self._persist()
        self._refresh_table()
        self._update_button_states()
