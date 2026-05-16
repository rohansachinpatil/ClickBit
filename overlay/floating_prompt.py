"""
overlay/floating_prompt.py
--------------------------
[BEGINNER GUIDE]
What is this file?
This is the "Face" of ClickBit. It's the beautiful, semi-transparent text box that pops
up when you hold the Left and Right mouse buttons. 
It captures what you type and sends it to the Executor (the Brain) to start a task.
"""

from PyQt5.QtCore import Qt, pyqtSignal, QPoint, pyqtSlot, QTimer, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QColor, QFont, QCursor
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QLabel, QApplication,
    QGraphicsDropShadowEffect, QFrame,
)
from utils.logger import get_logger

logger = get_logger(__name__)

class PromptLineEdit(QLineEdit):
    """Custom line edit that handles focus/escape events if needed."""
    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        # Optional: hide if focus is lost
        # self.parent().hide()

class FloatingPrompt(QWidget):
    """
    [BEGINNER GUIDE]
    This class builds the visual window. 
    It doesn't have a normal Windows border (FramelessWindowHint), and it stays 
    on top of all other windows (WindowStaysOnTopHint).
    """
    # Signal emitted when user presses Enter
    task_submitted = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 1. Set up the window rules
        self.setWindowFlags(
            Qt.FramelessWindowHint |      # No window border or title bar
            Qt.WindowStaysOnTopHint |     # Always float above other apps
            Qt.Tool |                     # Don't show in the Windows taskbar
            Qt.MSWindowsFixedSizeDialogHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground) # Make the background see-through
        self.setFixedSize(420, 150)
        
        # We track if we are currently "thinking" so we don't accidentally run 2 tasks at once
        self._is_planning = False

        self._setup_ui()
        self._setup_animations()

        # Timer to hide the window if you accidentally open it and click away
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

    def _setup_ui(self):
        """Builds all the text boxes, buttons, and layouts inside the window."""
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)

        # Create a container with rounded corners and a dark glass look
        self.container = QFrame(self)
        self.container.setObjectName("container")
        self.container.setStyleSheet("""
            #container {
                background-color: rgba(20, 20, 25, 240);
                border: 1px solid rgba(255, 255, 255, 20);
                border-radius: 12px;
            }
        """)
        
        # Set up a shadow so it looks like it's floating above the screen
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 150))
        shadow.setOffset(0, 5)
        self.container.setGraphicsEffect(shadow)

        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(15, 15, 15, 15)
        container_layout.setSpacing(10)

        # Create the title at the top
        header_layout = QHBoxLayout()
        self.title_label = QLabel("✨ ClickBit Assistant")
        self.title_label.setStyleSheet("color: #aaccff; font-weight: bold; font-size: 13px; letter-spacing: 1px;")
        
        # Create a little status light (green circle)
        self.status_light = QLabel()
        self.status_light.setFixedSize(8, 8)
        self.status_light.setStyleSheet("background-color: #00ffaa; border-radius: 4px;")
        
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        header_layout.addWidget(self.status_light)
        container_layout.addLayout(header_layout)

        # Create the actual input box where you type
        self.input_field = PromptLineEdit(self)
        self.input_field.setPlaceholderText("What would you like me to do?")
        self.input_field.setStyleSheet("background: transparent; color: white; border: none; font-size: 16px;")
        self.input_field.returnPressed.connect(self._on_submit)
        container_layout.addWidget(self.input_field)

        # Create the small status text at the bottom (e.g. "Ready")
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #888888; font-size: 11px;")
        container_layout.addWidget(self.status_label)

        layout.addWidget(self.container)
        self.setLayout(layout)

    def _setup_animations(self):
        """Sets up the smooth fade-in and slide-up animations when the window appears."""
        self.opacity_anim = QPropertyAnimation(self, b"windowOpacity")
        self.opacity_anim.setDuration(200)
        self.opacity_anim.setEasingCurve(QEasingCurve.OutCubic)

        self.pos_anim = QPropertyAnimation(self, b"pos")
        self.pos_anim.setDuration(250)
        self.pos_anim.setEasingCurve(QEasingCurve.OutBack)

    @pyqtSlot(int, int)
    def show_at(self, x: int, y: int):
        """
        [BEGINNER GUIDE]
        Called automatically when you hold Left + Right mouse buttons.
        Moves the window to your cursor's exact (x, y) location and plays an animation.
        """
        # If the window is already open, or we are busy thinking, don't do anything
        if self.isVisible() or self._is_planning:
            return

        logger.debug(f"Showing prompt at ({x}, {y})")
        
        # Reset the input box so it's clean for the next command
        self.input_field.clear()
        self.input_field.setEnabled(True)
        self.status_label.setText("Ready")
        self.status_light.setStyleSheet("background-color: #00ffaa; border-radius: 4px;")

        # Move the window slightly to the bottom right of the cursor
        target_pos = QPoint(x + 15, y + 15)
        start_pos = target_pos + QPoint(0, 10)

        self.setWindowOpacity(0.0)
        self.move(start_pos)
        self.show()
        self.activateWindow()
        self.input_field.setFocus()

        # Play animations
        self.opacity_anim.setStartValue(0.0)
        self.opacity_anim.setEndValue(1.0)
        
        self.pos_anim.setStartValue(start_pos)
        self.pos_anim.setEndValue(target_pos)

        self.opacity_anim.start()
        self.pos_anim.start()

    def _on_submit(self):
        """
        [BEGINNER GUIDE]
        Called when you press "Enter" inside the text box.
        """
        # Don't do anything if we are already busy or if you typed nothing
        if self._is_planning:
            return
            
        text = self.input_field.text().strip()
        if not text:
            self.hide()
            return
            
        logger.info(f"Task submitted: {text}")
        
        # Lock the UI so you can't submit twice by mashing Enter
        self._is_planning = True
        self.input_field.setEnabled(False)
        self.status_label.setText("Submitting task...")
        
        # Tell the Executor to start working on the task
        self.task_submitted.emit(text)

    # ── These methods are called by the Executor to update the UI ──
    @pyqtSlot(str)
    def on_task_started(self, prompt: str):
        self.status_label.setText("🧠 Planning...")
        self.status_light.setStyleSheet("background-color: #ffaa00; border-radius: 4px;")

    @pyqtSlot(str)
    def on_task_finished(self, msg: str):
        self.status_label.setText(f"✅ {msg}")
        self.status_light.setStyleSheet("background-color: #00ffaa; border-radius: 4px;")
        
        # Unlock the UI so you can type a new command
        self.input_field.setEnabled(True)
        self._is_planning = False
        self._hide_timer.start(1500)

    @pyqtSlot(str)
    def on_task_error(self, err_msg: str):
        """Called when the executor reports an error."""
        self.status_label.setText(f"❌ Error: {err_msg}")
        self.status_label.setStyleSheet("color: #ff5555; font-size: 11px;")
        self.status_light.setStyleSheet("background-color: #ff5555; border-radius: 4px;")
        
        # Unlock the UI so you can try again
        self.input_field.setEnabled(True)
        self._is_planning = False

    # ── Allows you to drag the window around with your mouse ──
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start = event.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and hasattr(self, "_drag_start"):
            self.move(event.globalPos() - self._drag_start)
