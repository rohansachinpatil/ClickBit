"""
overlay/floating_prompt.py
--------------------------
ClickBit Floating Spotlight Assistant.
Spotlight/Raycast-inspired translucent pill assistant bar.
Derives layout visual aesthetics, glows, and animations dynamically from centralized UI State.
"""

from PyQt5.QtCore import Qt, pyqtSignal, QPoint, pyqtSlot, QTimer, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QColor, QFont, QCursor
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QLabel, QApplication,
    QGraphicsDropShadowEffect, QFrame,
)
from utils.logger import get_logger
from ui.theme import Colors, UIState, Typography, Spacing, Effects, CI_MODE
from ui.components import GlassCard, StatusOrb, IconButton, AnimatedChip

logger = get_logger(__name__)

class PromptLineEdit(QLineEdit):
    """Custom QLineEdit with advanced styling and escape handle."""
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.parentWidget().parentWidget().hide()
        else:
            super().keyPressEvent(event)

class FloatingPrompt(QWidget):
    """
    Spotlight/Raycast hybrid translucent assistant bar.
    Fades and slides on cursor invocation.
    """
    task_submitted = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        
        if CI_MODE:
            self.setWindowFlags(Qt.Window | Qt.CustomizeWindowHint)
        else:
            self.setWindowFlags(
                Qt.FramelessWindowHint |      # Frameless
                Qt.WindowStaysOnTopHint |     # Pinned on top
                Qt.Tool |                     # No taskbar entry
                Qt.MSWindowsFixedSizeDialogHint
            )
            self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(580, 150) # Extremely clean, compact spotlight proportions
        
        self._is_planning = False
        self._current_state = UIState.IDLE

        self._setup_ui()
        self._setup_animations()

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

    def _setup_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        
        # 1. Main outer dark glassmorphism card
        self.card = GlassCard(self, rounded_radius=16)
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        card_layout.setSpacing(Spacing.MD)

        # 2. Main Row (Orb -> Input -> Run Button)
        main_row = QHBoxLayout()
        main_row.setSpacing(Spacing.MD)

        # A. AI Status Orb
        self.status_orb = StatusOrb(self.card, size=20)
        self.status_orb.set_state(UIState.IDLE)
        main_row.addWidget(self.status_orb, 0, Qt.AlignVCenter)

        # B. Spotlight Input Field
        self.input_field = PromptLineEdit(self.card)
        self.input_field.setPlaceholderText("What would you like me to do?")
        self.input_field.setStyleSheet(f"""
            QLineEdit {{
                background: transparent; 
                color: {Colors.TEXT_PRIMARY}; 
                border: none; 
                font-family: {Typography.FAMILY};
                font-size: 18px;
                font-weight: 300;
                padding: 0;
            }}
        """)
        self.input_field.returnPressed.connect(self._on_submit)
        main_row.addWidget(self.input_field, 1, Qt.AlignVCenter)

        # C. Translucent Active Run Button
        self.run_btn = QPushButton("Run", self.card)
        self.run_btn.setCursor(Qt.PointingHandCursor)
        self.run_btn.setFixedHeight(30)
        self.run_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Colors.TRANSLUCENT_WHITE};
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER_GLASS};
                border-radius: 8px;
                padding: 0 16px;
                font-family: {Typography.FAMILY};
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: rgba(0, 0, 0, 0.08);
                border-color: rgba(0, 0, 0, 0.12);
            }}
            QPushButton:pressed {{
                background-color: rgba(0, 0, 0, 0.12);
            }}
        """)
        self.run_btn.clicked.connect(self._on_submit)
        main_row.addWidget(self.run_btn, 0, Qt.AlignVCenter)

        card_layout.addLayout(main_row)

        # 3. Footer Row (Action Info -> Shortcut indicator)
        footer_row = QHBoxLayout()
        
        self.status_label = QLabel("ClickBit Intelligent Agent")
        self.status_label.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_SECONDARY};
                font-family: {Typography.FAMILY};
                font-size: 11px;
                font-weight: 400;
                background: transparent;
                border: none;
            }}
        """)
        footer_row.addWidget(self.status_label, 1, Qt.AlignVCenter)

        # Inline indicator tag
        self.shortcut_chip = AnimatedChip("Enter to Run", self.card, UIState.IDLE)
        footer_row.addWidget(self.shortcut_chip, 0, Qt.AlignVCenter)

        card_layout.addLayout(footer_row)
        
        root_layout.addWidget(self.card)
        self.setLayout(root_layout)

    def _setup_animations(self):
        self.opacity_anim = QPropertyAnimation(self, b"windowOpacity")
        self.opacity_anim.setDuration(220)
        self.opacity_anim.setEasingCurve(QEasingCurve.OutCubic)

    def _set_ui_state(self, state: str):
        self._current_state = state
        self.status_orb.set_state(state)
        self.shortcut_chip.set_state(state)
        
        # Color borders of outer glass card depending on state
        state_color = Colors.get_state_color(state)
        if state != UIState.IDLE:
            self.card.setStyleSheet(f"""
                QFrame {{
                    background-color: {Colors.CARD_BG};
                    border: 1px solid rgba({QColor(state_color).red()}, {QColor(state_color).green()}, {QColor(state_color).blue()}, 0.35);
                    border-radius: 16px;
                }}
            """)
            Effects.apply_soft_glow(self.card, state_color, blur_radius=20, alpha=25)
        else:
            self.card.setStyleSheet(f"""
                QFrame {{
                    background-color: {Colors.CARD_BG};
                    border: 1px solid {Colors.BORDER_GLASS};
                    border-radius: 16px;
                }}
            """)
            Effects.apply_ambient_shadow(self.card, blur_radius=30, alpha=20, y_offset=8)

    @pyqtSlot(int, int)
    def show_at(self, x: int, y: int):
        if self.isVisible() or self._is_planning:
            return

        logger.debug(f"Showing prompt at ({x}, {y})")
        
        self.input_field.clear()
        self.input_field.setEnabled(True)
        self.run_btn.setEnabled(True)
        
        self.status_label.setText("ClickBit Intelligent Agent ready")
        self.shortcut_chip.set_text("Enter to Run")
        self._set_ui_state(UIState.IDLE)

        target_pos = QPoint(x + 15, y + 15)

        if CI_MODE:
            self.move(target_pos)
            self.show()
            self.activateWindow()
            self.input_field.setFocus()
        else:
            self.setWindowOpacity(0.0)
            self.move(target_pos)
            self.show()
            self.activateWindow()
            self.input_field.setFocus()

            self.opacity_anim.setStartValue(0.0)
            self.opacity_anim.setEndValue(1.0)
            self.opacity_anim.start()

    def _on_submit(self):
        if self._is_planning:
            return
            
        text = self.input_field.text().strip()
        if not text:
            self.hide()
            return
            
        logger.info(f"Task submitted: {text}")
        
        self._is_planning = True
        self.input_field.setEnabled(False)
        self.run_btn.setEnabled(False)
        
        self.status_label.setText("Thinking...")
        self.shortcut_chip.set_text("Thinking")
        self._set_ui_state(UIState.THINKING)
        
        self.task_submitted.emit(text)

    # ── Slot triggers connected to Executor / agent loop ──
    @pyqtSlot(str)
    def on_task_started(self, prompt: str):
        self.status_label.setText("Planning autonomous steps...")
        self.shortcut_chip.set_text("Planning")
        self._set_ui_state(UIState.THINKING)

    @pyqtSlot(str)
    def on_task_finished(self, msg: str):
        self.status_label.setText(f"Task Completed: {msg}")
        self.shortcut_chip.set_text("Completed")
        self._set_ui_state(UIState.SUCCESS)
        
        self.input_field.setEnabled(True)
        self._is_planning = False
        self._hide_timer.start(1800)

    @pyqtSlot(str)
    def on_task_error(self, err_msg: str):
        self.status_label.setText(f"Error: {err_msg}")
        self.shortcut_chip.set_text("Failed")
        self._set_ui_state(UIState.ERROR)
        
        self.input_field.setEnabled(True)
        self.run_btn.setEnabled(True)
        self._is_planning = False

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start = event.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and hasattr(self, "_drag_start"):
            self.move(event.globalPos() - self._drag_start)
