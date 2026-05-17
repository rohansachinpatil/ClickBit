"""
ui/components/icon_button.py
-----------------------------
Monochrome vector SVG-driven custom QPushButton.
Handles hover transitions with dynamic vector recoloring.
"""

from PyQt5.QtWidgets import QPushButton
from PyQt5.QtCore import Qt, QSize
from ui.theme import Colors, get_svg_icon

class IconButton(QPushButton):
    """
    A premium flat icon button rendering high-dpi vector SVGs.
    Swaps monochrome icon colors dynamically on hover.
    """
    def __init__(self, icon_name: str, parent=None, size: int = 24, icon_size: int = 14, 
                 default_color: str = Colors.TEXT_SECONDARY, hover_color: str = Colors.TEXT_PRIMARY):
        super().__init__(parent)
        self.icon_name = icon_name
        self.icon_size_val = icon_size
        self.default_color = default_color
        self.hover_color = hover_color
        
        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)
        self._setup_style()
        self._update_icon(self.default_color)

    def _setup_style(self):
        self.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                border-radius: 6px;
            }}
            QPushButton:hover {{
                background-color: {Colors.TRANSLUCENT_WHITE};
            }}
            QPushButton:pressed {{
                background-color: rgba(0, 0, 0, 0.08);
            }}
        """)

    def _update_icon(self, color: str):
        icon = get_svg_icon(self.icon_name, color, self.icon_size_val)
        self.setIcon(icon)
        self.setIconSize(QSize(self.icon_size_val, self.icon_size_val))

    def enterEvent(self, event):
        self._update_icon(self.hover_color)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._update_icon(self.default_color)
        super().leaveEvent(event)
