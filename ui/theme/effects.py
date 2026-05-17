"""
ui/theme/effects.py
-------------------
Performance-tuned visual effects and ambient shadow generators for ClickBit.
Supports a rock-solid SAFE_RENDERING_MODE for Windows DWM translucency stability.
"""

import sys
import os
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QGraphicsDropShadowEffect

# Windows DWM has severe heap allocation/repaint bugs when combiningWA_TranslucentBackground
# frameless layered window resizes, and QGraphicsDropShadowEffect.
# Standardise on Safe Rendering Mode on Windows.
SAFE_RENDERING_MODE = sys.platform == "win32" or os.environ.get("CLICKBIT_SAFE_RENDERING", "1") == "1"

class Effects:
    @staticmethod
    def apply_ambient_shadow(widget, blur_radius: int = 15, alpha: int = 15, y_offset: int = 4):
        """
        Applies a low-overhead drop shadow to simulated floating surfaces.
        Completely bypassed on Windows under SAFE_RENDERING_MODE to prevent DWM crashes.
        """
        widget.setGraphicsEffect(None)
        
        if SAFE_RENDERING_MODE:
            # Under Windows, we bypass graphics drop shadows entirely to guarantee 100% stability.
            # Visual hierarchy is maintained using micro-thin premium solid card boundaries.
            return
            
        shadow = QGraphicsDropShadowEffect(widget)
        shadow.setBlurRadius(blur_radius)
        shadow.setColor(QColor(0, 0, 0, alpha))
        shadow.setOffset(0, y_offset)
        widget.setGraphicsEffect(shadow)

    @staticmethod
    def apply_soft_glow(widget, color_hex: str, blur_radius: int = 15, alpha: int = 15):
        """
        Applies a low-latency, soft ambient color halo (for warning or recovery states).
        Completely bypassed on Windows under SAFE_RENDERING_MODE.
        """
        widget.setGraphicsEffect(None)
        
        if SAFE_RENDERING_MODE:
            return
            
        glow = QGraphicsDropShadowEffect(widget)
        glow.setBlurRadius(blur_radius)
        
        color = QColor(color_hex)
        color.setAlpha(alpha)
        
        glow.setColor(color)
        glow.setOffset(0, 0)
        widget.setGraphicsEffect(glow)
