"""
gui_pages_idle_ports.py
صفحه‌ی «Idle Ports Report» - اتصال SSH به دستگاه (روی ترد جدا)، خواندن
وضعیت پورت‌ها و شمارنده‌ی ترافیک، و نمایش جدولی پورت‌های notconnect،
err-disabled، و پورت‌های connected بدون ترافیک اخیر.

اتصال و پردازش دقیقاً از همان توابع بک‌اند cisco_mgmt.py استفاده می‌کند
(get_interfaces_status, get_interfaces_counters, update_traffic_state_for_device,
find_traffic_idle_ports) - فقط لایه‌ی نمایش اینجا جدید است؛ منطق تشخیص
idle بازنویسی نشده.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QFrame,
)
from PySide6.QtGui import QColor

import device_manager
import cisco_mgmt
import gui_preferences
from gui_workers import Worker
from gui_widgets import SteppedSpinBox

# رنگ‌های تیره (برای پس‌زمینه‌ی تیره‌ی کارت‌ها) و رنگ‌های روشن (برای
# پس‌زمینه‌ی سفید تم روشن) کاملاً جدا تعریف شده‌اند - یک ست رنگ برای هر
# دو تم مناسب نیست (مثلاً یک قهوه‌ای تیره روی پس‌زمینه‌ی تیره خوب دیده
# می‌شود ولی روی سفید تقریباً غیرقابل‌تشخیص است).
STATUS_COLORS_DARK = {
    "notconnect": QColor("#3a2a12"),
    "err-disabled": QColor("#3a1414"),
    "disabled": QColor("#232c42"),
}
TRAFFIC_IDLE_COLOR_DARK = QColor("#2a2a12")

STATUS_COLORS_LIGHT = {
    "notconnect": QColor("#ffe3b3"),
    "err-disabled": QColor("#ffd2d2"),
    "disabled": QColor("#e3e7f0"),
}
TRAFFIC_IDLE_COLOR_LIGHT = QColor("#fff3b0")


def _current_colors() -> tuple[dict, QColor]:
    """
    بر اساس تم فعلاً ذخیره‌شده (gui_preferences)، ست رنگ مناسب را
    برمی‌گرداند: (status_colors_dict, traffic_idle_color)
    """
    theme = gui_preferences.load_preferences().get("theme", "dark")
    if theme == "light":
        return STATUS_COLORS_LIGHT, TRAFFIC_IDLE_COLOR_LIGHT
    return STATUS_COLORS_DARK, TRAFFIC_IDLE_COLOR_DARK


def _build_legend_row() -> QHBoxLayout:
    """یک ردیف کوچک شامل مربع رنگ + توضیح، برای هر رنگ استفاده‌شده در جدول."""
    status_colors, traffic_idle_color = _current_colors()
    legend_items = [
        (status_colors["notconnect"], "Idle (notconnect) - nothing plugged in, candidate for hardening"),
        (status_colors["err-disabled"], "Err-disabled - needs attention"),
        (status_colors["disabled"], "Administratively shut down (already safe)"),
        (traffic_idle_color, "Connected, but no traffic since the last check"),
    ]
    theme = gui_preferences.load_preferences().get("theme", "dark")
    swatch_border = "#2c3652" if theme == "dark" else "#c7cedd"

    row = QHBoxLayout()
    row.setSpacing(18)
    for color, description in legend_items:
        swatch = QFrame()
        swatch.setFixedSize(14, 14)
        swatch.setStyleSheet(f"background-color: {color.name()}; border-radius: 3px; border: 1px solid {swatch_border};")
        label = QLabel(description)
        label.setObjectName("HintLabel")

        item_box = QHBoxLayout()
        item_box.setSpacing(6)
        item_box.addWidget(swatch)
        item_box.addWidget(label)
        row.addLayout(item_box)
    row.addStretch()
    return row


def _fetch_idle_ports_data(device: dict, idle_days_threshold: int):
    """
    به دستگاه وصل می‌شود، وضعیت پورت‌ها و شمارنده‌ها را می‌خواند، با
    آخرین snapshot ذخیره‌شده مقایسه می‌کند (و آن snapshot را به‌روز
    می‌کند)، و (hostname, interfaces, traffic_idle) را برمی‌گرداند. این
    تابع روی یک QThread جدا اجرا می‌شود - نباید هیچ ویجت Qt را مستقیم
    لمس کند.
    """
    params = device_manager.to_connection_params(device)
    conn = cisco_mgmt.ConnectHandler(**params)
    try:
        hostname = conn.find_prompt().strip("#>").strip()
        cisco_mgmt.ensure_enable_mode(conn, params["host"])
        interfaces = cisco_mgmt.get_interfaces_status(conn, debug=False)
        counters = cisco_mgmt.get_interfaces_counters(conn, debug=False)
    finally:
        conn.disconnect()

    traffic_idle = {}
    if counters:
        device_state = cisco_mgmt.update_traffic_state_for_device(hostname, counters)
        traffic_idle = cisco_mgmt.find_traffic_idle_ports(device_state, interfaces, idle_days_threshold)

    return hostname, interfaces, traffic_idle


class IdlePortsPage(QWidget):
    def __init__(self, devices: list, parent=None):
        super().__init__(parent)
        self.devices = devices
        self._worker: Worker | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        title = QLabel("Idle Ports Report")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Find unused switch ports - candidates for security hardening.")
        subtitle.setObjectName("PageSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        self.legend_container = QWidget()
        self.legend_container.setLayout(_build_legend_row())
        layout.addWidget(self.legend_container)

        control_row = QHBoxLayout()
        self.device_selector = QComboBox()
        self.device_selector.setMinimumWidth(220)
        control_row.addWidget(self.device_selector)

        control_row.addWidget(QLabel("Idle threshold (days):"))
        self.threshold_input = SteppedSpinBox()
        self.threshold_input.setRange(1, 365)
        self.threshold_input.setValue(14)
        control_row.addWidget(self.threshold_input)

        self.run_button = QPushButton("Run report")
        self.run_button.setObjectName("PrimaryButton")
        self.run_button.clicked.connect(self._run_report)
        control_row.addWidget(self.run_button)
        control_row.addStretch()
        layout.addLayout(control_row)

        self.summary_label = QLabel("")
        self.summary_label.setObjectName("HintLabel")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Port", "Status", "Vlan", "Name", "Note"])
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table, stretch=1)

        note = QLabel(
            "Note: notconnect/err-disabled reflect only the current link status - verify manually "
            "before shutting a port down. The traffic-idle note needs at least one prior run of this "
            "report on the device to compare against."
        )
        note.setObjectName("HintLabel")
        note.setWordWrap(True)
        layout.addWidget(note)

        self._refresh_device_list()

    def refresh_devices(self, devices: list) -> None:
        self.devices = devices
        self._refresh_device_list()
        self._rebuild_legend()

    def _rebuild_legend(self) -> None:
        """
        legend را دوباره می‌سازد - چون رنگ‌ها به تم فعلی وابسته‌اند و تم
        ممکن است از صفحه‌ی Settings عوض شده باشد، هر بار که کاربر به این
        صفحه برمی‌گردد (از طریق refresh_devices) رنگ‌های legend به‌روز
        می‌شوند.
        """
        main_layout = self.layout()
        index = main_layout.indexOf(self.legend_container)
        main_layout.removeWidget(self.legend_container)
        self.legend_container.deleteLater()

        self.legend_container = QWidget()
        self.legend_container.setLayout(_build_legend_row())
        main_layout.insertWidget(index, self.legend_container)

    def _refresh_device_list(self) -> None:
        current = self.device_selector.currentText()
        self.device_selector.clear()
        for d in self.devices:
            self.device_selector.addItem(f"{d.get('name')} ({d.get('host')})", d)
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
        self.summary_label.setText(f"Connecting to {device.get('host')}...")
        self.table.setRowCount(0)

        self._worker = Worker(_fetch_idle_ports_data, device, self.threshold_input.value())
        self._worker.finished_ok.connect(self._on_report_done)
        self._worker.finished_error.connect(self._on_report_error)
        self._worker.start()

    def _on_report_done(self, result) -> None:
        hostname, interfaces, traffic_idle = result
        self.run_button.setEnabled(True)

        notconnect = sum(1 for d in interfaces.values() if d["status"].lower() == "notconnect")
        err_disabled = sum(1 for d in interfaces.values() if "err" in d["status"].lower())
        connected = sum(1 for d in interfaces.values() if d["status"].lower() == "connected")
        self.summary_label.setText(
            f"{hostname}: {len(interfaces)} port(s) total | {connected} connected | "
            f"{notconnect} idle (notconnect) | {err_disabled} err-disabled | "
            f"{len(traffic_idle)} traffic-idle"
        )

        status_colors, traffic_idle_color = _current_colors()

        rows = sorted(interfaces.items())
        self.table.setRowCount(len(rows))
        for row, (port, d) in enumerate(rows):
            status = d["status"]
            note = ""
            if port in traffic_idle:
                note = f"idle {traffic_idle[port]['days_idle']}d (no traffic)"

            values = [port, status, d.get("vlan", ""), d.get("name", ""), note]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                color = status_colors.get(status.lower())
                if color is None and note:
                    color = traffic_idle_color
                if color is not None:
                    item.setBackground(color)
                self.table.setItem(row, col, item)

    def _on_report_error(self, error_text: str) -> None:
        self.run_button.setEnabled(True)
        self.summary_label.setText(f"Failed to fetch the report: {error_text}")
