"""
ui/components/status_orb.py
----------------------------
Premium breathing AI status orb component.
Uses QRadialGradient and a QPropertyAnimation to pulse the glow radius dynamically
based on centralized UI state.
"""

from PyQt5.QtWidgets import QWidget
from PyQt5.QtGui import QPainter, QRadialGradient, QColor
from PyQt5.QtCore import QPropertyAnimation, pyqtProperty, QEasingCurve, Qt
from ui.theme import Colors, UIState

class StatusOrb(QWidget):
    """
    A minimal, intelligent breathing status indicator.
    Dynamic colors, glow, and animations are derived entirely from UIState.
    """
    def __init__(self, parent=None, size: int = 18):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._glow_factor = 1.0
        self._state = UIState.IDLE
        
        # Configure the gentle breathing animation
        self._pulse_anim = QPropertyAnimation(self, b"glow_factor")
        self._pulse_anim.setDuration(2200) # Very calm, 2.2 second breath cycle
        self._pulse_anim.setStartValue(0.5)
        self._pulse_anim.setEndValue(1.0)
        self._pulse_anim.setEasingCurve(QEasingCurve.InOutQuad)
        self._pulse_anim.setLoopCount(-1) # Loop forever
        self._pulse_anim.start()

    @pyqtProperty(float)
    def glow_factor(self) -> float:
        return self._glow_factor

    @glow_factor.setter
    def glow_factor(self, value: float):
        self._glow_factor = value
        self.update() # Force repaint

    def set_state(self, state: str):
        """Updates the internal UIState and repaints the orb immediately."""
        if self._state != state:
            self._state = state
            # Adjust breathing speed depending on state
            if state in (UIState.THINKING, UIState.RECOVERING):
                self._pulse_anim.setDuration(1200) # Faster pulse
            else:
                self._pulse_anim.setDuration(2200) # Muted calm pulse
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Get semantic state color
        color_hex = Colors.get_state_color(self._state)
        base_color = QColor(color_hex)
        
        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0
        r = min(w, h) / 2.0
        
        # Draw breathing radial glow
        gradient = QRadialGradient(cx, cy, r)
        core_color = QColor(base_color)
        
        # Idle state has very light glowing presence
        if self._state == UIState.IDLE:
            core_color.setAlpha(120)
            glow_alpha = int(40 * self._glow_factor)
        else:
            core_color.setAlpha(255)
            glow_alpha = int(140 * self._glow_factor)
            
        glow_color = QColor(base_color)
        glow_color.setAlpha(glow_alpha)
        
        gradient.setColorAt(0.0, core_color)
        gradient.setColorAt(0.3, core_color)
        gradient.setColorAt(0.5, glow_color)
        gradient.setColorAt(1.0, Qt.transparent)
        
        painter.setBrush(gradient)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(self.rect())
        painter.end()
