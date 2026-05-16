"""
overlay/debug_panel.py
-----------------------
A live dashboard for visualizing agent reasoning, planning, and execution steps.
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QScrollArea, QFrame, QPushButton, QListWidget, QListWidgetItem)
from PyQt5.QtCore import Qt, pyqtSlot, QDateTime, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QIcon

class DebugEventItem(QWidget):
    """Custom widget for a single timeline event."""
    def __init__(self, timestamp, event_type, message, status="info"):
        super().__init__()
        layout = QHBoxLayout()
        layout.setContentsMargins(10, 5, 10, 5)
        
        # Icon/Status
        self.icon_label = QLabel()
        icons = {
            "planning": "🧠",
            "memory": "📦",
            "action": "🚀",
            "success": "✅",
            "error": "❌",
            "retry": "🔄",
            "info": "ℹ️",
            "observation": "👁️"
        }
        self.icon_label.setText(icons.get(event_type, "•"))
        self.icon_label.setFixedWidth(25)
        
        # Timestamp
        self.time_label = QLabel(timestamp)
        self.time_label.setStyleSheet("color: #888; font-size: 10px;")
        self.time_label.setFixedWidth(60)
        
        # Message
        self.msg_label = QLabel(message)
        self.msg_label.setWordWrap(True)
        self.msg_label.setStyleSheet("color: #eee; font-weight: 500;")
        
        layout.addWidget(self.icon_label)
        layout.addWidget(self.time_label)
        layout.addWidget(self.msg_label, 1)
        self.setLayout(layout)

class DebugPanel(QWidget):
    """
    Collapsible dashboard for monitoring agent activity.
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ClickBit Timeline")
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(400, 500)
        
        # Main Layout
        self.main_layout = QVBoxLayout()
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Content Container (Dark glass effect)
        self.container = QFrame()
        self.container.setObjectName("debug_container")
        self.container.setStyleSheet("""
            #debug_container {
                background-color: rgba(25, 25, 35, 240);
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 12px;
            }
        """)
        
        container_layout = QVBoxLayout(self.container)
        
        # Header
        header = QHBoxLayout()
        title = QLabel("AGENT TIMELINE")
        title.setStyleSheet("color: #00ffaa; font-weight: bold; letter-spacing: 1px;")
        
        self.close_btn = QPushButton("×")
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.setStyleSheet("background: none; color: #888; font-size: 20px; border: none;")
        self.close_btn.clicked.connect(self.hide)
        
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.close_btn)
        container_layout.addLayout(header)
        
        # Event List
        self.event_list = QListWidget()
        self.event_list.setStyleSheet("""
            QListWidget {
                background: transparent;
                border: none;
            }
            QListWidget::item {
                border-bottom: 1px solid rgba(255, 255, 255, 10);
            }
        """)
        container_layout.addWidget(self.event_list)
        
        # Footer
        footer = QHBoxLayout()
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setStyleSheet("background: #333; color: #ccc; border-radius: 4px; padding: 4px 10px;")
        self.clear_btn.clicked.connect(self.event_list.clear)
        
        footer.addStretch()
        footer.addWidget(self.clear_btn)
        container_layout.addLayout(footer)
        
        self.main_layout.addWidget(self.container)
        self.setLayout(self.main_layout)

    @pyqtSlot(str, str, str)
    def add_event(self, event_type, message, status="info"):
        """Adds a new event to the timeline."""
        timestamp = QDateTime.currentDateTime().toString("hh:mm:ss")
        
        item = QListWidgetItem(self.event_list)
        widget = DebugEventItem(timestamp, event_type, message, status)
        item.setSizeHint(widget.sizeHint())
        
        self.event_list.addItem(item)
        self.event_list.setItemWidget(item, widget)
        self.event_list.scrollToBottom()
        
        # Auto-show on major events if hidden
        if event_type in ["planning", "error"] and not self.isVisible():
            self.show_at_default()

    def show_at_default(self):
        """Shows the panel at the right side of the screen."""
        screen = self.screen().availableGeometry()
        self.move(screen.width() - self.width() - 20, 100)
        self.show()
