"""
overlay/confirmation.py
-----------------------
A glassmorphic modal dialog to review and approve/reject planned actions.
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QFrame, QScrollArea, QWidget
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont

class ConfirmationDialog(QDialog):
    """
    Sleek modal to show planned steps before execution.
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
        self.layout = QVBoxLayout(self)
        self.card = QFrame()
        self.card.setObjectName("ConfirmCard")
        self.card.setFixedWidth(400)
        self.card.setStyleSheet("""
            #ConfirmCard {
                background-color: rgba(30, 30, 35, 230);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 15px;
            }
            QLabel { color: white; }
            QPushButton {
                border-radius: 8px;
                padding: 10px;
                font-weight: bold;
                font-size: 13px;
            }
            #ApproveBtn {
                background-color: #4CAF50;
                color: white;
            }
            #ApproveBtn:hover { background-color: #45a049; }
            #RejectBtn {
                background-color: rgba(255, 255, 255, 0.1);
                color: #ff5555;
            }
            #RejectBtn:hover { background-color: rgba(255, 255, 255, 0.2); }
        """)
        
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(20, 20, 20, 20)

        # Title
        title = QLabel("Confirm Actions")
        title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        card_layout.addWidget(title)

        subtitle = QLabel("ClickBit has planned the following steps:")
        subtitle.setStyleSheet("color: rgba(255, 255, 255, 0.6); margin-bottom: 10px;")
        card_layout.addWidget(subtitle)

        # Steps Area (Scrollable)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")
        
        scroll_content = QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        step_layout = QVBoxLayout(scroll_content)
        
        for i, step in enumerate(self.steps):
            step_label = QLabel(f"{i+1}. {step}")
            step_label.setWordWrap(True)
            step_label.setStyleSheet("""
                background: rgba(255, 255, 255, 0.05);
                padding: 8px;
                border-radius: 5px;
                margin-bottom: 2px;
                font-family: 'Consolas';
                font-size: 11px;
            """)
            step_layout.addWidget(step_label)
        
        step_layout.addStretch()
        scroll.setWidget(scroll_content)
        scroll.setMaximumHeight(200)
        card_layout.addWidget(scroll)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        reject_btn = QPushButton("Reject")
        reject_btn.setObjectName("RejectBtn")
        reject_btn.setCursor(Qt.PointingHandCursor)
        reject_btn.clicked.connect(self._on_reject)
        
        approve_btn = QPushButton("Approve && Run")
        approve_btn.setObjectName("ApproveBtn")
        approve_btn.setCursor(Qt.PointingHandCursor)
        approve_btn.clicked.connect(self._on_approve)
        
        btn_layout.addWidget(reject_btn)
        btn_layout.addWidget(approve_btn)
        
        card_layout.addLayout(btn_layout)
        self.layout.addWidget(self.card, 0, Qt.AlignCenter)

    def _on_approve(self):
        self.approved.emit()
        self.accept()

    def _on_reject(self):
        self.rejected.emit()
        self.reject()
