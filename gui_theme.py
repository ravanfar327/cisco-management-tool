"""
gui_theme.py
پالت رنگ و QSS (Qt Style Sheet) برای ظاهر برنامه - دو تم (dark/light)
با یک رنگ تأکیدی (accent) واحد، مناسب یک ابزار مدیریت شبکه.

این ماژول فقط رشته و ثابت تعریف می‌کند - هیچ وابستگی به PySide6 ندارد،
پس import کردنش هزینه‌ای ندارد.
"""

FONT_FAMILY = "Segoe UI, Tahoma, Arial, sans-serif"

DARK_PALETTE = {
    "BG_APP": "#0f1420",
    "BG_SIDEBAR": "#0b0f19",
    "BG_CARD": "#161d2e",
    "BG_CARD_HOVER": "#1c2540",
    "BG_INPUT": "#0f1420",
    "BORDER": "#232c42",
    "BORDER_LIGHT": "#2c3652",
    "TEXT_PRIMARY": "#e7eaf3",
    "TEXT_SECONDARY": "#8b93a7",
    "TEXT_MUTED": "#5b6478",
    "ACCENT": "#3ba7ff",
    "ACCENT_HOVER": "#5db8ff",
    "ACCENT_DARK": "#2a7fc9",
    "ACCENT_TEXT_ON": "#0b0f19",
    "SUCCESS": "#22c55e",
    "WARNING": "#f5a524",
    "DANGER": "#f24545",
    "CONSOLE_BG": "#090c14",
    "CONSOLE_TEXT": "#9fe3a8",
}

LIGHT_PALETTE = {
    "BG_APP": "#f4f6fb",
    "BG_SIDEBAR": "#ffffff",
    "BG_CARD": "#ffffff",
    "BG_CARD_HOVER": "#eef2fa",
    "BG_INPUT": "#ffffff",
    "BORDER": "#dde2ee",
    "BORDER_LIGHT": "#c7cedd",
    "TEXT_PRIMARY": "#1a2033",
    "TEXT_SECONDARY": "#5b6478",
    "TEXT_MUTED": "#8b93a7",
    "ACCENT": "#2f7fd6",
    "ACCENT_HOVER": "#4a95e6",
    "ACCENT_DARK": "#1f5f9e",
    "ACCENT_TEXT_ON": "#ffffff",
    "SUCCESS": "#1a9e4f",
    "WARNING": "#c07a00",
    "DANGER": "#d23c3c",
    "CONSOLE_BG": "#0f1420",
    "CONSOLE_TEXT": "#8fe0a0",
}

PALETTES = {"dark": DARK_PALETTE, "light": LIGHT_PALETTE}

_TEMPLATE = """
    * {{
        font-family: {FONT_FAMILY};
        outline: none;
    }}

    QMainWindow, QDialog {{
        background-color: {BG_APP};
        color: {TEXT_PRIMARY};
    }}

    QWidget#Sidebar {{
        background-color: {BG_SIDEBAR};
        border-right: 1px solid {BORDER};
    }}

    QLabel#AppTitle {{
        color: {TEXT_PRIMARY};
        font-size: 15px;
        font-weight: 600;
        padding: 18px 16px 4px 16px;
    }}

    QLabel#AppSubtitle {{
        color: {TEXT_MUTED};
        font-size: 11px;
        padding: 0px 16px 18px 16px;
    }}

    QPushButton#NavButton {{
        background-color: transparent;
        color: {TEXT_SECONDARY};
        border: none;
        border-radius: 8px;
        padding: 10px 14px;
        text-align: left;
        font-size: 13px;
        margin: 2px 10px;
    }}

    QPushButton#NavButton:hover {{
        background-color: {BG_CARD_HOVER};
        color: {TEXT_PRIMARY};
    }}

    QPushButton#NavButton:checked {{
        background-color: {ACCENT};
        color: {ACCENT_TEXT_ON};
        font-weight: 600;
    }}

    QPushButton#NavButton:disabled {{
        color: {TEXT_MUTED};
    }}

    QLabel#PageTitle {{
        color: {TEXT_PRIMARY};
        font-size: 20px;
        font-weight: 600;
    }}

    QLabel#PageSubtitle {{
        color: {TEXT_SECONDARY};
        font-size: 12px;
    }}

    QFrame#Card {{
        background-color: {BG_CARD};
        border: 1px solid {BORDER};
        border-radius: 10px;
    }}

    QLabel {{
        color: {TEXT_PRIMARY};
    }}

    QLabel#FieldLabel {{
        color: {TEXT_SECONDARY};
        font-size: 12px;
    }}

    QLabel#HintLabel {{
        color: {TEXT_MUTED};
        font-size: 11px;
    }}

    QLineEdit, QComboBox, QSpinBox, QTextEdit, QPlainTextEdit {{
        background-color: {BG_INPUT};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER_LIGHT};
        border-radius: 6px;
        padding: 7px 10px;
        font-size: 13px;
        selection-background-color: {ACCENT_DARK};
    }}

    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QTextEdit:focus {{
        border: 1px solid {ACCENT};
    }}

    /* دکمه‌های +/- بومی QSpinBox حذف شده‌اند (SteppedSpinBox در
       gui_widgets.py جایگزینشان شده) - محدودیت شناخته‌شده‌ی Qt این بود
       که با QSS نمی‌شد هم هندسه‌ی کلیک دو دکمه را درست کرد و هم شکل
       فلش را، بدون تصویر واقعی. استایل زیر مربوط به همان ویجت جایگزین
       است: یک QSpinBox بدون دکمه + دو QToolButton معمولی با متن ▲/▼،
       طوری چیده شده‌اند که یک باکس یکپارچه به‌نظر برسند. */
    QSpinBox#SteppedSpinBoxField {{
        border-top-right-radius: 0px;
        border-bottom-right-radius: 0px;
        border-right: none;
    }}

    QWidget#SteppedSpinBoxButtonColumn {{
        background-color: {BG_INPUT};
        border: 1px solid {BORDER_LIGHT};
        border-left: none;
        border-top-right-radius: 6px;
        border-bottom-right-radius: 6px;
    }}

    QToolButton#SpinUpButton, QToolButton#SpinDownButton {{
        background-color: transparent;
        border: none;
        color: {TEXT_SECONDARY};
        font-size: 8px;
        padding: 0px;
    }}

    QToolButton#SpinUpButton {{
        border-top-right-radius: 6px;
        border-bottom: 1px solid {BORDER_LIGHT};
    }}

    QToolButton#SpinDownButton {{
        border-bottom-right-radius: 6px;
    }}

    QToolButton#SpinUpButton:hover, QToolButton#SpinDownButton:hover {{
        background-color: {BG_CARD_HOVER};
        color: {TEXT_PRIMARY};
    }}

    QToolButton#SpinUpButton:pressed, QToolButton#SpinDownButton:pressed {{
        background-color: {ACCENT_DARK};
        color: white;
    }}

    QToolButton#SpinUpButton:disabled, QToolButton#SpinDownButton:disabled {{
        color: {TEXT_MUTED};
    }}

    QComboBox::drop-down {{
        border: none;
        width: 22px;
    }}

    QComboBox QAbstractItemView {{
        background-color: {BG_CARD};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER_LIGHT};
        selection-background-color: {ACCENT_DARK};
        outline: none;
    }}

    QCheckBox, QRadioButton {{
        color: {TEXT_PRIMARY};
        font-size: 13px;
        spacing: 8px;
    }}

    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border-radius: 4px;
        border: 1px solid {BORDER_LIGHT};
        background-color: {BG_INPUT};
    }}

    QCheckBox::indicator:checked {{
        background-color: {ACCENT};
        border: 1px solid {ACCENT};
    }}

    QRadioButton::indicator {{
        width: 16px;
        height: 16px;
        border-radius: 8px;
        border: 1px solid {BORDER_LIGHT};
        background-color: {BG_INPUT};
    }}

    QRadioButton::indicator:checked {{
        background-color: {ACCENT};
        border: 1px solid {ACCENT};
    }}

    QPushButton {{
        background-color: {BG_CARD};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER_LIGHT};
        border-radius: 6px;
        padding: 8px 16px;
        font-size: 13px;
    }}

    QPushButton:hover {{
        background-color: {BG_CARD_HOVER};
        border: 1px solid {ACCENT};
    }}

    QPushButton:disabled {{
        color: {TEXT_MUTED};
        border: 1px solid {BORDER};
    }}

    QPushButton#PrimaryButton {{
        background-color: {ACCENT};
        color: {ACCENT_TEXT_ON};
        border: none;
        font-weight: 600;
    }}

    QPushButton#PrimaryButton:hover {{
        background-color: {ACCENT_HOVER};
    }}

    QPushButton#PrimaryButton:disabled {{
        background-color: {BORDER_LIGHT};
        color: {TEXT_MUTED};
    }}

    QPushButton#DangerButton {{
        background-color: transparent;
        color: {DANGER};
        border: 1px solid {DANGER};
    }}

    QPushButton#DangerButton:hover {{
        background-color: {DANGER};
        color: white;
    }}

    QTableWidget {{
        background-color: {BG_CARD};
        alternate-background-color: {BG_APP};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER};
        border-radius: 8px;
        gridline-color: {BORDER};
        font-size: 13px;
        selection-background-color: {ACCENT_DARK};
        selection-color: white;
    }}

    QHeaderView::section {{
        background-color: {BG_SIDEBAR};
        color: {TEXT_SECONDARY};
        padding: 8px;
        border: none;
        border-bottom: 1px solid {BORDER};
        font-size: 11px;
        font-weight: 600;
    }}

    QTableWidget::item {{
        padding: 6px;
    }}

    QPlainTextEdit#LogConsole {{
        background-color: {CONSOLE_BG};
        color: {CONSOLE_TEXT};
        border: 1px solid {BORDER};
        border-radius: 8px;
        font-family: Consolas, "Courier New", monospace;
        font-size: 12px;
    }}

    QScrollArea {{
        background: transparent;
        border: none;
    }}

    QScrollArea > QWidget {{
        background: transparent;
    }}

    QScrollArea > QWidget > QWidget {{
        background: transparent;
    }}

    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
    }}

    QScrollBar::handle:vertical {{
        background: {BORDER_LIGHT};
        border-radius: 5px;
        min-height: 24px;
    }}

    QScrollBar::handle:vertical:hover {{
        background: {ACCENT_DARK};
    }}

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}

    QStatusBar {{
        background-color: {BG_SIDEBAR};
        color: {TEXT_SECONDARY};
        border-top: 1px solid {BORDER};
    }}

    QMessageBox {{
        background-color: {BG_APP};
    }}

    QToolTip {{
        background-color: {BG_CARD};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER_LIGHT};
        padding: 4px 6px;
    }}
"""


def build_stylesheet(theme: str = "dark") -> str:
    """
    QSS کامل برنامه را برای تم داده‌شده می‌سازد. مقدار نامعتبر theme
    بی‌سروصدا به 'dark' برمی‌گردد (هرگز نباید باعث کرش شود).
    """
    palette = PALETTES.get(theme, DARK_PALETTE)
    return _TEMPLATE.format(FONT_FAMILY=FONT_FAMILY, **palette)
