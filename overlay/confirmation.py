"""
overlay/confirmation.py
-----------------------
A premium glassmorphic modal dialog to review and approve/reject planned actions.
Strictly maps layout visual design to Design Tokens System.
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QFrame, QScrollArea, QWidget
)
from PyQt5.QtCore import Qt, pyqtSignal, QSize
from PyQt5.QtGui import QFont, QCursor, QPixmap
from ui.theme import Colors, Typography, Spacing, Effects, get_svg_pixmap
from ui.components import GlassCard

class ConfirmationDialog(QDialog):
    """
    Sleek translucent modal to show planned steps before execution.
    """
    approved = pyqtSignal()
    rejected = pyqtSignal()

    def __init__(self, steps: list[str], parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        self.steps = steps
        self._init_ui()

    def _init_ui(self):
        # Main Layout container (The "Glass" card)
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        
        self.card = GlassCard(self, rounded_radius=20)
        self.card.setFixedWidth(440)
        
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        card_layout.setSpacing(Spacing.MD)

        # Title Row with monochrome warning icon
        title_row = QHBoxLayout()
        title_row.setSpacing(Spacing.SM)
        
        warn_pixmap = get_svg_pixmap("alert_triangle", Colors.AMBER, size=22)
        warn_icon = QLabel()
        warn_icon.setPixmap(warn_pixmap)
        warn_icon.setFixedSize(22, 22)
        title_row.addWidget(warn_icon)
        
        title = QLabel("Confirm Plan")
        title.setStyleSheet(f"""
            color: {Colors.TEXT_PRIMARY};
            font-family: {Typography.FAMILY};
            font-size: 16px;
            font-weight: 600;
            background: transparent;
            border: none;
        """)
        title_row.addWidget(title)
        title_row.addStretch()
        
        card_layout.addLayout(title_row)

        subtitle = QLabel("ClickBit has planned the following autonomous steps:")
        subtitle.setStyleSheet(f"""
            color: {Colors.TEXT_SECONDARY};
            font-family: {Typography.FAMILY};
            font-size: 12px;
            background: transparent;
            border: none;
            margin-bottom: 4px;
        """)
        card_layout.addWidget(subtitle)

        # Steps Area (Scrollable)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical {
                border: none;
                background: transparent;
                width: 6px;
            }
            QScrollBar::handle:vertical {
                background: rgba(0, 0, 0, 0.12);
                min-height: 20px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(0, 0, 0, 0.20);
            }
        """)
        
        scroll_content = QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        step_layout = QVBoxLayout(scroll_content)
        step_layout.setContentsMargins(0, 0, 0, 0)
        step_layout.setSpacing(Spacing.SM)
        
        for i, step in enumerate(self.steps):
            step_label = QLabel(f"{i+1}. {step}")
            step_label.setWordWrap(True)
            step_label.setStyleSheet(f"""
                background: rgba(0, 0, 0, 0.03);
                color: {Colors.TEXT_PRIMARY};
                border: 1px solid {Colors.BORDER_LIGHT};
                padding: 10px 12px;
                border-radius: 8px;
                font-family: Consolas, monospace;
                font-size: 11px;
            """)
            step_layout.addWidget(step_label)
        
        step_layout.addStretch()
        scroll.setWidget(scroll_content)
        scroll.setMaximumHeight(180)
        card_layout.addWidget(scroll)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(Spacing.SM)
        
        reject_btn = QPushButton("Reject")
        reject_btn.setCursor(Qt.PointingHandCursor)
        reject_btn.setFixedHeight(34)
        reject_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {Colors.TEXT_SECONDARY};
                border: 1px solid transparent;
                border-radius: 8px;
                font-family: {Typography.FAMILY};
                font-weight: 500;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {Colors.TRANSLUCENT_WHITE};
                color: {Colors.RED};
            }}
        """)
        reject_btn.clicked.connect(self._on_reject)
        
        approve_btn = QPushButton("Approve && Run")
        approve_btn.setCursor(Qt.PointingHandCursor)
        approve_btn.setFixedHeight(34)
        approve_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Colors.TRANSLUCENT_WHITE};
                color: {Colors.GREEN};
                border: 1px solid rgba(16, 185, 129, 0.25);
                border-radius: 8px;
                font-family: {Typography.FAMILY};
                font-weight: 600;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: rgba(16, 185, 129, 0.12);
                border-color: rgba(16, 185, 129, 0.40);
            }}
        """)
        approve_btn.clicked.connect(self._on_approve)
        
        btn_layout.addWidget(reject_btn)
        btn_layout.addWidget(approve_btn, 1)
        
        card_layout.addLayout(btn_layout)
        
        root_layout.addWidget(self.card, 0, Qt.AlignCenter)

    def _on_approve(self):
        self.approved.emit()
        self.accept()

    def _on_reject(self):
        self.rejected.emit()
        self.reject()
