"""
gui_pages_audit_log.py
صفحه‌ی «Audit Log» - نمایش محتوای security_audit.log (همان فایلی که
audit_log.py می‌نویسد). فقط خواندن فایل - هیچ منطق ثبت رویدادی اینجا
نیست، آن همه در audit_log.py است.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QPlainTextEdit,
    QCheckBox,
)

import audit_log

MAX_LINES = 500


class AuditLogPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        title = QLabel("Security Audit Log")
        title.setObjectName("PageTitle")
        subtitle = QLabel(f"Last {MAX_LINES} lines of {audit_log.AUDIT_LOG_FILE}")
        subtitle.setObjectName("PageSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        control_row = QHBoxLayout()
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setObjectName("PrimaryButton")
        self.refresh_button.clicked.connect(self._refresh)
        control_row.addWidget(self.refresh_button)

        self.warnings_only_checkbox = QCheckBox("Show WARNING/ERROR/CRITICAL only")
        self.warnings_only_checkbox.toggled.connect(self._refresh)
        control_row.addWidget(self.warnings_only_checkbox)

        control_row.addStretch()
        layout.addLayout(control_row)

        self.console = QPlainTextEdit()
        self.console.setObjectName("LogConsole")
        self.console.setReadOnly(True)
        layout.addWidget(self.console, stretch=1)

        self._refresh()

    def _refresh(self) -> None:
        try:
            with open(audit_log.AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except FileNotFoundError:
            self.console.setPlainText("No audit log events have been recorded yet.")
            return

        lines = lines[-MAX_LINES:]

        if self.warnings_only_checkbox.isChecked():
            lines = [
                line for line in lines
                if any(level in line for level in (" WARNING ", " ERROR ", " CRITICAL "))
            ]

        self.console.setPlainText("".join(lines) if lines else "No matching events.")
        scrollbar = self.console.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
