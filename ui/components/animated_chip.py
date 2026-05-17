"""
ui/components/animated_chip.py
------------------------------
Translucent, sleek inline status badge/chip widget.
Style colors dynamically mirror target UIState values.
"""

from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel
from PyQt5.QtGui import QColor
from ui.theme import Colors, Typography, Spacing

class AnimatedChip(QFrame):
    """
    A premium badge tag for displaying metadata, confidence metrics, or subgoals.
    Derives borders and transparent backgrounds dynamically from target colors.
    """
    def __init__(self, text: str, parent=None, state: str = "default"):
        super().__init__(parent)
        self.text_val = text
        self._setup_ui()
        self.set_state(state)

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.SM, Spacing.XS, Spacing.SM, Spacing.XS)
        layout.setSpacing(Spacing.XS)
        
        self.label = QLabel(self.text_val)
        self.label.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_PRIMARY};
                font-family: {Typography.FAMILY};
                font-size: 11px;
                font-weight: 500;
                background: transparent;
                border: none;
            }}
        """)
        layout.addWidget(self.label)

    def set_state(self, state: str):
        """Derives translucent chip color styling based on UIState."""
        color_hex = Colors.get_state_color(state)
        color = QColor(color_hex)
        
        # Build performance-safe translucent style
        self.setStyleSheet(f"""
            QFrame {{
                background-color: rgba({color.red()}, {color.green()}, {color.blue()}, 0.12);
                border: 1px solid rgba({color.red()}, {color.green()}, {color.blue()}, 0.25);
                border-radius: 6px;
            }}
        """)

    def set_text(self, text: str):
        self.label.setText(text)
