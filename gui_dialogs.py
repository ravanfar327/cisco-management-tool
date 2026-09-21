"""
dialogs.py
دو دیالوگ اصلی برنامه:

- UnlockDialog: صفحه‌ی ورود پسورد master (همان منطق سه‌تلاشه‌ی CLI،
  دوباره‌نویسی‌شده روی همان توابع بک‌اند - device_manager.load_devices
  و audit_log، تا رفتار هر دو رابط کاملاً یکسان بماند).
- DeviceDialog: فرم افزودن/ویرایش دستگاه - شامل پورت SSH، تشخیص خودکار
  سیسکو/غیر سیسکو، و بخش تنظیمات بک‌آپ سفارشی برای دستگاه‌های غیر سیسکو.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QComboBox, QSpinBox, QCheckBox, QPushButton, QMessageBox, QGroupBox,
    QDialogButtonBox,
)
from PySide6.QtCore import Qt

import device_manager
import audit_log
from cisco_mgmt import MAX_MASTER_PASSWORD_ATTEMPTS


COMMON_DEVICE_TYPES = [
    "cisco_ios",
    "cisco_xe",
    "cisco_nxos",
    "cisco_asa",
    "mikrotik_routeros",
    "hp_comware",
    "arista_eos",
    "juniper_junos",
]


class UnlockDialog(QDialog):
    """
    دیالوگ ورود پسورد master. اگر با موفقیت رمزگشایی شود، لیست دستگاه‌ها
    و خود پسورد را در self.devices / self.master_password نگه می‌دارد و
    accept() فراخوانی می‌شود. بعد از MAX_MASTER_PASSWORD_ATTEMPTS تلاش
    ناموفق، دیالوگ کاملاً بسته می‌شود (reject) - دقیقاً مثل رفتار CLI.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cisco Switch Management Tool - Unlock")
        self.setFixedSize(420, 220)
        self.setModal(True)

        self.devices: list = []
        self.master_password: str = ""
        self._attempts_used = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 24)
        layout.setSpacing(10)

        title = QLabel("Cisco Switch Management Tool")
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        layout.addWidget(title)

        subtitle = QLabel("Enter the master password to decrypt your device list.")
        subtitle.setObjectName("HintLabel")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        layout.addSpacing(8)

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("Master password")
        self.password_input.returnPressed.connect(self._try_unlock)
        layout.addWidget(self.password_input)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #f24545; font-size: 12px;")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        layout.addStretch()

        button_row = QHBoxLayout()
        button_row.addStretch()
        self.unlock_button = QPushButton("Unlock")
        self.unlock_button.setObjectName("PrimaryButton")
        self.unlock_button.clicked.connect(self._try_unlock)
        button_row.addWidget(self.unlock_button)
        layout.addLayout(button_row)

        self.password_input.setFocus()

    def _try_unlock(self) -> None:
        password = self.password_input.text()
        if not password:
            self.error_label.setText("Enter the master password.")
            return

        self.unlock_button.setEnabled(False)
        try:
            devices = device_manager.load_devices(password)
        except ValueError as e:
            self._attempts_used += 1
            remaining = MAX_MASTER_PASSWORD_ATTEMPTS - self._attempts_used
            if remaining > 0:
                self.error_label.setText(f"Wrong password. ({remaining} attempt(s) remaining)")
                self.password_input.clear()
                self.password_input.setFocus()
                self.unlock_button.setEnabled(True)
            else:
                audit_log.log_event(
                    "MASTER_PW_LOCKOUT",
                    f"Exceeded {MAX_MASTER_PASSWORD_ATTEMPTS} failed master password attempts (GUI) - exiting",
                    level="ERROR",
                )
                QMessageBox.critical(
                    self,
                    "Too many attempts",
                    "Too many failed master password attempts. The application will now close.",
                )
                self.reject()
            return

        self.devices = devices
        self.master_password = password
        self.accept()


class DeviceDialog(QDialog):
    """
    فرم افزودن یا ویرایش یک دستگاه. اگر existing_device داده شود، فرم با
    مقادیر آن پر می‌شود (حالت ویرایش)؛ در غیر این صورت فرم خالی (حالت
    افزودن) است. نتیجه‌ی نهایی از self.result_device (دیکشنری دستگاه)
    بعد از exec() موفق قابل خواندن است.
    """

    def __init__(self, existing_device: dict | None = None, parent=None):
        super().__init__(parent)
        self.is_edit_mode = existing_device is not None
        self._original = dict(existing_device) if existing_device else {}
        self.result_device: dict | None = None

        self.setWindowTitle("Edit device" if self.is_edit_mode else "Add device")
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.name_input = QLineEdit(self._original.get("name", ""))
        self.name_input.setPlaceholderText("e.g. Core-SW")
        form.addRow("Name/label:", self.name_input)

        self.host_input = QLineEdit(self._original.get("host", ""))
        self.host_input.setPlaceholderText("e.g. 10.0.0.1")
        form.addRow("IP address:", self.host_input)

        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(self._original.get("port", 22))
        form.addRow("SSH port:", self.port_input)

        self.username_input = QLineEdit(self._original.get("username", ""))
        form.addRow("Username:", self.username_input)

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText(
            "Leave empty to keep current" if self.is_edit_mode else ""
        )
        form.addRow("Password:", self.password_input)

        self.secret_input = QLineEdit()
        self.secret_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.secret_input.setPlaceholderText(
            "Leave empty to keep current" if self.is_edit_mode else "Leave empty if none"
        )
        form.addRow("Enable secret:", self.secret_input)

        self.device_type_input = QComboBox()
        self.device_type_input.setEditable(True)
        self.device_type_input.addItems(COMMON_DEVICE_TYPES)
        current_type = self._original.get("device_type", "cisco_ios")
        if current_type not in COMMON_DEVICE_TYPES:
            self.device_type_input.addItem(current_type)
        self.device_type_input.setCurrentText(current_type)
        self.device_type_input.currentTextChanged.connect(self._on_device_type_changed)
        form.addRow("Device type:", self.device_type_input)

        self.is_core_checkbox = QCheckBox("This is the core/L3 switch (has the VLAN gateways/SVIs)")
        self.is_core_checkbox.setChecked(bool(self._original.get("is_core", False)))
        form.addRow("", self.is_core_checkbox)

        layout.addLayout(form)

        # --- Cisco auto-backup (simple checkbox) ---
        self.cisco_auto_backup_checkbox = QCheckBox("Include this device in scheduled auto-backup")
        self.cisco_auto_backup_checkbox.setChecked(bool(self._original.get("auto_backup", False)))
        layout.addWidget(self.cisco_auto_backup_checkbox)

        # --- Non-Cisco backup settings (shown only for non-Cisco device types) ---
        self.non_cisco_group = QGroupBox("Automatic backup for this non-Cisco device")
        non_cisco_layout = QVBoxLayout(self.non_cisco_group)

        explanation = QLabel(
            "This tool connects over SSH and sends exactly ONE command - the "
            "output of that command becomes the backup file, saved exactly as "
            "returned (no Cisco-specific processing is applied). The command "
            "must print the configuration directly to the terminal.\n"
            "Examples: Mikrotik -> /export | HP/Aruba, Arista -> show running-config "
            "| Juniper -> show configuration"
        )
        explanation.setObjectName("HintLabel")
        explanation.setWordWrap(True)
        non_cisco_layout.addWidget(explanation)

        self.non_cisco_auto_backup_checkbox = QCheckBox("Enable automatic backup for this device")
        self.non_cisco_auto_backup_checkbox.setChecked(bool(self._original.get("auto_backup", False)))
        self.non_cisco_auto_backup_checkbox.toggled.connect(self._on_non_cisco_toggle)
        non_cisco_layout.addWidget(self.non_cisco_auto_backup_checkbox)

        non_cisco_form = QFormLayout()
        self.backup_command_input = QLineEdit(self._original.get("backup_command", ""))
        self.backup_command_input.setPlaceholderText("e.g. /export  or  show running-config")
        non_cisco_form.addRow("Backup command:", self.backup_command_input)

        self.disable_paging_input = QLineEdit(self._original.get("disable_paging_command", ""))
        self.disable_paging_input.setPlaceholderText("optional - leave empty if not needed")
        non_cisco_form.addRow("Disable paging first:", self.disable_paging_input)
        non_cisco_layout.addLayout(non_cisco_form)

        layout.addWidget(self.non_cisco_group)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #f24545; font-size: 12px;")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._on_device_type_changed(current_type)
        self._on_non_cisco_toggle(self.non_cisco_auto_backup_checkbox.isChecked())

    def _on_device_type_changed(self, text: str) -> None:
        is_cisco = device_manager.is_cisco_device_type(text)
        self.cisco_auto_backup_checkbox.setVisible(is_cisco)
        self.non_cisco_group.setVisible(not is_cisco)

    def _on_non_cisco_toggle(self, checked: bool) -> None:
        self.backup_command_input.setEnabled(checked)
        self.disable_paging_input.setEnabled(checked)

    def _on_accept(self) -> None:
        name = self.name_input.text().strip()
        host = self.host_input.text().strip()
        username = self.username_input.text().strip()
        device_type = self.device_type_input.currentText().strip() or "cisco_ios"

        if not name or not host or not username:
            self.error_label.setText("Name, IP address, and username are required.")
            return

        is_cisco = device_manager.is_cisco_device_type(device_type)

        if is_cisco:
            auto_backup = self.cisco_auto_backup_checkbox.isChecked()
            backup_command = ""
            disable_paging_command = ""
        else:
            auto_backup = self.non_cisco_auto_backup_checkbox.isChecked()
            backup_command = self.backup_command_input.text().strip()
            disable_paging_command = self.disable_paging_input.text().strip()
            if auto_backup and not backup_command:
                self.error_label.setText(
                    "A backup command is required to enable automatic backup on a non-Cisco device."
                )
                return

        password = self.password_input.text()
        if not password:
            password = self._original.get("password", "")

        if not self.is_edit_mode and not password:
            self.error_label.setText("Password is required.")
            return

        secret = self.secret_input.text()
        if not secret:
            secret = self._original.get("secret", "")

        self.result_device = {
            "name": name,
            "device_type": device_type,
            "host": host,
            "username": username,
            "password": password,
            "secret": secret,
            "port": self.port_input.value(),
            "timeout": self._original.get("timeout", 10),
            "is_core": self.is_core_checkbox.isChecked(),
            "auto_backup": auto_backup,
            "backup_command": backup_command,
            "disable_paging_command": disable_paging_command,
        }
        self.accept()
