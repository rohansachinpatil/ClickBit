"""
ui/theme.py
-----------
Centralized design system for ClickBit.
Implements a premium Apple-inspired light theme.
"""

from PyQt5.QtGui import QColor, QFont, QFontDatabase
from PyQt5.QtWidgets import QGraphicsDropShadowEffect
from PyQt5.QtCore import Qt

class Colors:
    """Core color palette inspired by modern AI SaaS (Mint/White aesthetic)."""
    # Outer container mint green
    MINT_BG = "#eaf2eb" 
    MINT_BORDER = "#d1e3d0"
    
    # Inner input/card white
    WHITE_CARD = "#ffffff"
    WHITE_FROST_SOLID = "rgba(255, 255, 255, 250)"
    
    TEXT_PRIMARY = "#2d3748"
    TEXT_SECONDARY = "#718096"
    TEXT_PLACEHOLDER = "#a0aec0"
    
    BORDER_LIGHT = "rgba(0, 0, 0, 8)"
    
    # Accent colors
    GREEN_CURSOR = "#38a169"
    GREEN = "#48bb78"
    BLUE = "#3182ce"
    RED = "#e53e3e"
    GRAY_BG = "rgba(0, 0, 0, 0.04)"
    GRAY_HOVER = "rgba(0, 0, 0, 0.08)"

class Fonts:
    """Typography system favoring native system fonts."""
    @staticmethod
    def get_family():
        return "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"

def apply_glass_effect(widget, shadow_radius=30, shadow_alpha=40, y_offset=10):
    """
    Applies a sleek, large-radius drop shadow to simulate a floating window
    and soften the edges for a premium feel.
    """
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(shadow_radius)
    shadow.setColor(QColor(0, 0, 0, shadow_alpha))
    shadow.setOffset(0, y_offset)
    widget.setGraphicsEffect(shadow)

def get_base_stylesheet():
    """Returns the base styling for modern scrollbars and general widgets."""
    return f"""
        QScrollArea {{
            background: transparent;
            border: none;
        }}
        QScrollBar:vertical {{
            border: none;
            background: transparent;
            width: 8px;
            margin: 0px 0px 0px 0px;
        }}
        QScrollBar::handle:vertical {{
            background: {Colors.TEXT_PLACEHOLDER};
            min-height: 20px;
            border-radius: 4px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {Colors.TEXT_SECONDARY};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            border: none;
            background: none;
        }}
        QListWidget {{
            background: transparent;
            border: none;
            outline: none;
        }}
        QListWidget::item {{
            border-bottom: 1px solid {Colors.BORDER_LIGHT};
            padding: 5px;
        }}
        QListWidget::item:selected {{
            background: transparent;
            color: {Colors.TEXT_PRIMARY};
        }}
    """
