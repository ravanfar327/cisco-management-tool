"""
gui_pages_settings.py
صفحه‌ی «Settings» - سه بخش:
  1. تنظیمات زمان‌بندی بک‌آپ خودکار (همان فیلدهای backup_settings.py)
  2. تغییر پسورد master (رمزگشایی/رمزنگاری مجدد فایل دستگاه‌ها)
  3. انتخاب تم (روشن/تیره)

توجه: خود تنظیمات زمان‌بندی فقط پارامترهای scheduler را مشخص می‌کنند -
برای اجرای واقعی بک‌آپ خودکار در پس‌زمینه، باید یا این برنامه باز
بماند، یا حالت headless CLI ('--service') از طریق Windows Task
Scheduler تنظیم شود (همان چیزی که در منوی Backup نسخه‌ی CLI هست).
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QLineEdit, QFormLayout, QFileDialog, QMessageBox, QFrame,
    QRadioButton, QButtonGroup, QScrollArea,
)
from PySide6.QtCore import Qt

import backup_settings
import device_manager
import audit_log
import gui_preferences
from gui_widgets import SteppedSpinBox

WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


class SettingsPage(QWidget):
    def __init__(
        self,
        settings: dict,
        devices: list,
        master_password: str,
        on_password_changed,
        on_theme_changed,
        parent=None,
    ):
        super().__init__(parent)
        self.settings = settings
        self.devices = devices
        self.master_password = master_password
        self.on_password_changed = on_password_changed
        self.on_theme_changed = on_theme_changed
        self.preferences = gui_preferences.load_preferences()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        title = QLabel("Settings")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Scheduled auto-backup configuration, security, and appearance.")
        subtitle.setObjectName("PageSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        # نکته: عمداً هیچ setStyleSheet() مستقیمی روی scroll_area یا
        # فرزندانش گذاشته نمی‌شود - یک استایل‌شیت instance-level روی یک
        # ویجت میانی، cascade شدن قوانین global (مثل border کارت‌ها یا
        # رنگ دکمه‌ی Save) به فرزندانش را در Qt مختل می‌کند. شفافیت
        # پس‌زمینه‌ی QScrollArea از طریق قوانین 'QScrollArea' در
        # gui_theme.py (همان استایل‌شیت سراسری اپ) تأمین می‌شود که این
        # مشکل تداخل را ندارد.
        layout.addWidget(scroll_area, stretch=1)

        scroll_content = QWidget()
        scroll_area.setWidget(scroll_content)
        content_layout = QVBoxLayout(scroll_content)
        content_layout.setContentsMargins(0, 0, 4, 0)
        content_layout.setSpacing(16)

        card = QFrame()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(12)

        schedule_heading = QLabel("Scheduled auto-backup")
        schedule_heading.setStyleSheet("font-weight: 600; font-size: 14px;")
        card_layout.addWidget(schedule_heading)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.schedule_type_input = QComboBox()
        self.schedule_type_input.addItems(["daily", "weekly", "monthly"])
        self.schedule_type_input.setCurrentText(self.settings.get("schedule_type", "daily"))
        self.schedule_type_input.currentTextChanged.connect(self._on_schedule_type_changed)
        form.addRow("Schedule type:", self.schedule_type_input)

        self.time_input = QLineEdit(self.settings.get("schedule_time", "00:00"))
        self.time_input.setPlaceholderText("HH:MM")
        form.addRow("Time (24h):", self.time_input)

        self.weekday_input = QComboBox()
        self.weekday_input.addItems(WEEKDAYS)
        self.weekday_input.setCurrentText(self.settings.get("schedule_day_of_week", "mon"))
        form.addRow("Day of week:", self.weekday_input)

        self.day_of_month_input = SteppedSpinBox()
        self.day_of_month_input.setRange(1, 28)
        self.day_of_month_input.setValue(int(self.settings.get("schedule_day_of_month", 1)))
        form.addRow("Day of month:", self.day_of_month_input)

        self.retention_input = SteppedSpinBox()
        self.retention_input.setRange(1, 1000)
        self.retention_input.setValue(int(self.settings.get("retention_count", 10)))
        form.addRow("Backups to keep per device:", self.retention_input)

        path_row = QHBoxLayout()
        self.backup_path_input = QLineEdit(self.settings.get("backup_path", ""))
        path_browse_button = QPushButton("Browse...")
        path_browse_button.clicked.connect(self._browse_backup_path)
        path_row.addWidget(self.backup_path_input)
        path_row.addWidget(path_browse_button)
        form.addRow("Backup path:", path_row)

        card_layout.addLayout(form)
        content_layout.addWidget(card)

        save_row = QHBoxLayout()
        save_row.addStretch()
        self.save_button = QPushButton("Save settings")
        self.save_button.setObjectName("PrimaryButton")
        self.save_button.clicked.connect(self._save)
        save_row.addWidget(self.save_button)
        content_layout.addLayout(save_row)

        # --- کارت تغییر پسورد master ---
        password_card = QFrame()
        password_card.setObjectName("Card")
        password_card_layout = QVBoxLayout(password_card)
        password_card_layout.setContentsMargins(20, 20, 20, 20)
        password_card_layout.setSpacing(12)

        password_heading = QLabel("Master password")
        password_heading.setStyleSheet("font-weight: 600; font-size: 14px;")
        password_card_layout.addWidget(password_heading)

        password_hint = QLabel(
            "Changing this re-encrypts your entire device list (including all stored "
            "device passwords) with the new master password."
        )
        password_hint.setObjectName("HintLabel")
        password_hint.setWordWrap(True)
        password_card_layout.addWidget(password_hint)

        password_form = QFormLayout()
        password_form.setSpacing(10)
        password_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.current_password_input = QLineEdit()
        self.current_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        password_form.addRow("Current password:", self.current_password_input)

        self.new_password_input = QLineEdit()
        self.new_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        password_form.addRow("New password:", self.new_password_input)

        self.confirm_password_input = QLineEdit()
        self.confirm_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        password_form.addRow("Confirm new password:", self.confirm_password_input)

        password_card_layout.addLayout(password_form)

        self.password_status_label = QLabel("")
        self.password_status_label.setWordWrap(True)
        password_card_layout.addWidget(self.password_status_label)

        password_button_row = QHBoxLayout()
        password_button_row.addStretch()
        self.change_password_button = QPushButton("Change master password")
        self.change_password_button.clicked.connect(self._change_master_password)
        password_button_row.addWidget(self.change_password_button)
        password_card_layout.addLayout(password_button_row)

        content_layout.addWidget(password_card)

        # --- کارت انتخاب تم ---
        theme_card = QFrame()
        theme_card.setObjectName("Card")
        theme_card_layout = QVBoxLayout(theme_card)
        theme_card_layout.setContentsMargins(20, 20, 20, 20)
        theme_card_layout.setSpacing(12)

        theme_heading = QLabel("Appearance")
        theme_heading.setStyleSheet("font-weight: 600; font-size: 14px;")
        theme_card_layout.addWidget(theme_heading)

        theme_row = QHBoxLayout()
        self.theme_group = QButtonGroup(self)
        self.dark_theme_radio = QRadioButton("Dark")
        self.light_theme_radio = QRadioButton("Light")
        self.theme_group.addButton(self.dark_theme_radio)
        self.theme_group.addButton(self.light_theme_radio)
        theme_row.addWidget(self.dark_theme_radio)
        theme_row.addWidget(self.light_theme_radio)
        theme_row.addStretch()
        theme_card_layout.addLayout(theme_row)

        current_theme = self.preferences.get("theme", "dark")
        if current_theme == "light":
            self.light_theme_radio.setChecked(True)
        else:
            self.dark_theme_radio.setChecked(True)
        self.dark_theme_radio.toggled.connect(self._on_theme_toggled)

        content_layout.addWidget(theme_card)

        content_layout.addStretch()

        self._on_schedule_type_changed(self.schedule_type_input.currentText())

    def _on_schedule_type_changed(self, schedule_type: str) -> None:
        self.weekday_input.setEnabled(schedule_type == "weekly")
        self.day_of_month_input.setEnabled(schedule_type == "monthly")

    def _browse_backup_path(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self, "Select backup folder", self.backup_path_input.text() or "."
        )
        if chosen:
            self.backup_path_input.setText(chosen)

    def _save(self) -> None:
        time_value = self.time_input.text().strip()
        try:
            hours, minutes = time_value.split(":")
            hours, minutes = int(hours), int(minutes)
            if not (0 <= hours < 24 and 0 <= minutes < 60):
                raise ValueError
        except ValueError:
            QMessageBox.warning(self, "Invalid time", "Enter the time as HH:MM, e.g. 23:30.")
            return

        self.settings["schedule_type"] = self.schedule_type_input.currentText()
        self.settings["schedule_time"] = f"{hours:02d}:{minutes:02d}"
        self.settings["schedule_day_of_week"] = self.weekday_input.currentText()
        self.settings["schedule_day_of_month"] = self.day_of_month_input.value()
        self.settings["retention_count"] = self.retention_input.value()
        self.settings["backup_path"] = self.backup_path_input.text().strip() or self.settings["backup_path"]

        backup_settings.save_settings(self.settings)
        QMessageBox.information(self, "Saved", "Backup settings saved.")

    def _on_theme_toggled(self, dark_checked: bool) -> None:
        theme = "dark" if dark_checked else "light"
        self.preferences["theme"] = theme
        gui_preferences.save_preferences(self.preferences)
        self.on_theme_changed(theme)

    def _change_master_password(self) -> None:
        current = self.current_password_input.text()
        new = self.new_password_input.text()
        confirm = self.confirm_password_input.text()

        if current != self.master_password:
            self._set_password_status("Current password is incorrect.", error=True)
            return
        if not new:
            self._set_password_status("Enter a new password.", error=True)
            return
        if new != confirm:
            self._set_password_status("New password and confirmation do not match.", error=True)
            return
        if new == current:
            self._set_password_status("New password must be different from the current one.", error=True)
            return

        confirmed = QMessageBox.question(
            self,
            "Change master password",
            "This will re-encrypt your entire device list with the new password. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return

        try:
            device_manager.save_devices(self.devices, new)
        except Exception as e:  # noqa: BLE001 - any failure here must be shown, not crash the app
            self._set_password_status(f"Failed to change password: {e}", error=True)
            return

        audit_log.log_event("MASTER_PW_CHANGED", "Master password changed (GUI)", level="WARNING")
        self.master_password = new
        self.on_password_changed(new)

        self.current_password_input.clear()
        self.new_password_input.clear()
        self.confirm_password_input.clear()
        self._set_password_status("Master password changed successfully.", error=False)

    def _set_password_status(self, text: str, error: bool) -> None:
        color = "#f24545" if error else "#22c55e"
        self.password_status_label.setStyleSheet(f"color: {color}; font-size: 12px;")
        self.password_status_label.setText(text)
