"""
gui_widgets.py
ویجت‌های سفارشی مشترک بین صفحات مختلف GUI.

SteppedSpinBox
--------------
سبک‌سازی دکمه‌های +/- بومی QSpinBox از طریق QSS به یک محدودیت واقعی
Qt خورد: یا هندسه‌ی کلیک دو دکمه درست می‌شد و فلش‌ها اصلاً رسم نمی‌شدند،
یا برعکس. به‌جای گیر کردن تو این تناقض، این ویجت دکمه‌های داخلی
QSpinBox را کلاً مخفی می‌کند (setButtonSymbols(NoButtons)) و به‌جایش دو
QToolButton معمولی با متن یونیکد ▲/▼ کنارش می‌سازد - رندر متن روی یک
دکمه‌ی معمولی همیشه صددرصد قابل‌اعتماد است، برخلاف زیربخش‌های
::up-arrow/::down-arrow که رفتارشان بین نسخه‌ها/استایل‌های Qt فرق دارد.

از نظر API، این کلاس یک جایگزین drop-in برای QSpinBox در حد نیاز این
پروژه است: setRange, setValue, value, setEnabled. اگر جای دیگری از
پروژه به امکانات بیشتری از QSpinBox نیاز پیدا کرد (مثل سیگنال
valueChanged)، باید اینجا هم proxy شود.
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QSpinBox, QAbstractSpinBox, QToolButton,
)
from PySide6.QtCore import Qt


class SteppedSpinBox(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SteppedSpinBox")

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._spinbox = QSpinBox()
        self._spinbox.setObjectName("SteppedSpinBoxField")
        self._spinbox.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        outer.addWidget(self._spinbox, 1)

        button_column = QWidget()
        button_column.setObjectName("SteppedSpinBoxButtonColumn")
        button_layout = QVBoxLayout(button_column)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(0)

        self._up_button = QToolButton()
        self._up_button.setObjectName("SpinUpButton")
        self._up_button.setText("\u25b2")  # ▲
        self._up_button.setAutoRepeat(True)
        self._up_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._up_button.setFixedWidth(20)
        self._up_button.clicked.connect(self._spinbox.stepUp)

        self._down_button = QToolButton()
        self._down_button.setObjectName("SpinDownButton")
        self._down_button.setText("\u25bc")  # ▼
        self._down_button.setAutoRepeat(True)
        self._down_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._down_button.setFixedWidth(20)
        self._down_button.clicked.connect(self._spinbox.stepDown)

        button_layout.addWidget(self._up_button, 1)
        button_layout.addWidget(self._down_button, 1)
        outer.addWidget(button_column)

        self._sync_button_states()
        self._spinbox.valueChanged.connect(self._sync_button_states)

    def _sync_button_states(self, _value: int = 0) -> None:
        """دکمه‌ی بالا/پایین را وقتی به سقف/کف بازه رسیدیم غیرفعال می‌کند - دقیقاً رفتار QSpinBox بومی."""
        self._up_button.setEnabled(self.isEnabled() and self._spinbox.value() < self._spinbox.maximum())
        self._down_button.setEnabled(self.isEnabled() and self._spinbox.value() > self._spinbox.minimum())

    # --- API هم‌ارز با QSpinBox، در حد نیاز این پروژه ---
    def setRange(self, minimum: int, maximum: int) -> None:
        self._spinbox.setRange(minimum, maximum)
        self._sync_button_states()

    def setValue(self, value: int) -> None:
        self._spinbox.setValue(value)

    def value(self) -> int:
        return self._spinbox.value()

    def setEnabled(self, enabled: bool) -> None:
        super().setEnabled(enabled)
        self._spinbox.setEnabled(enabled)
        self._sync_button_states()
