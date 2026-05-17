"""
ui/components/glass_card.py
----------------------------
Reusable custom QFrame component implementing a visionOS-inspired glass card.
Designed to avoid expensive realtime blurs by using translucent alpha overlays
and performance-safe ambient shadows.
"""

from PyQt5.QtWidgets import QFrame
from ui.theme import Colors, Spacing, Effects

class GlassCard(QFrame):
    """
    A premium dark glassmorphic card container.
    Constructs a layered translucent surface with micro-thin borders and soft corner rounding.
    """
    def __init__(self, parent=None, rounded_radius: int = 16, border_color: str = Colors.BORDER_GLASS):
        super().__init__(parent)
        self.rounded_radius = rounded_radius
        self.border_color = border_color
        self._setup_style()

    def _setup_style(self):
        # Set stylesheet with translucent gradient background and thin white border
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {Colors.CARD_BG};
                border: 1px solid {self.border_color};
                border-radius: {self.rounded_radius}px;
            }}
        """)
        # Apply high-end low-overhead drop shadow
        Effects.apply_ambient_shadow(self, blur_radius=30, alpha=20, y_offset=8)
