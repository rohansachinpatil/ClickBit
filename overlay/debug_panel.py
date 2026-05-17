"""
overlay/debug_panel.py
-----------------------
ClickBit Premium Observability Dashboard.
VISION-OS inspired dark translucent glassmorphism timeline and status tracker.
Derives layout styles, border highlights, and status orb glows from centralized UI State.
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QFrame, QPushButton, QListWidget, QListWidgetItem,
                             QProgressBar)
from PyQt5.QtCore import Qt, pyqtSlot, QDateTime, pyqtSignal, QSize
from PyQt5.QtGui import QColor, QFont, QCursor, QPixmap
from ui.theme import Colors, UIState, Typography, Spacing, Effects, get_svg_pixmap, get_svg_icon
from ui.components import GlassCard, StatusOrb, IconButton, AnimatedChip

def clean_emoji_prefixes(msg: str) -> str:
    """Strips any legacy emoji prefixes from messages to ensure professional styling."""
    emojis = ["🚀", "📋", "🔄", "👁", "✅", "🛑", "❌", "⚡", "💭", "⚠️", "🎯", "•", "🧠", "📦", "🛠", "🧩"]
    for e in emojis:
        msg = msg.replace(e, "")
    # Clean up common double space or prefix artifact patterns
    msg = msg.replace("Executing:", "").replace("Starting autonomous task:", "").strip()
    return msg

# ── Debug Timeline Row ─────────────────────────────────────────────────────────

class DebugEventItem(QWidget):
    """
    Sleek, monochrome-driven timeline row.
    Maps legacy emojis directly to professional vector Lucide paths.
    """
    EVENT_ICONS = {
        "planning": ("sparkles", Colors.BLUE),
        "memory": ("brain", Colors.INDIGO),
        "action": ("play", Colors.INDIGO),
        "success": ("check", Colors.GREEN),
        "error": ("x", Colors.RED),
        "retry": ("refresh_cw", Colors.AMBER),
        "info": ("activity", Colors.TEXT_SECONDARY),
        "observation": ("search", Colors.BLUE),
        "warning": ("alert_triangle", Colors.AMBER),
        "selector_resolution": ("search", Colors.INDIGO),
        "plan_update": ("activity", Colors.BLUE),
        "json_repair": ("refresh_cw", Colors.AMBER),
        "schema_warning": ("alert_triangle", Colors.AMBER),
        "malformed_output": ("alert_triangle", Colors.RED),
        "primitive_intent": ("play", Colors.BLUE),
        "primitive_success": ("check", Colors.GREEN),
        "primitive_failure": ("x", Colors.RED),
        "transition_score": ("activity", Colors.BLUE),
        "ineffective_action": ("alert_triangle", Colors.AMBER),
    }

    def __init__(self, timestamp: str, event_type: str, message: str):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(Spacing.SM, Spacing.XS, Spacing.SM, Spacing.XS)
        layout.setSpacing(Spacing.SM)

        # Vector Icon Loader
        icon_name, icon_color = self.EVENT_ICONS.get(event_type, ("activity", Colors.TEXT_SECONDARY))
        pixmap = get_svg_pixmap(icon_name, icon_color, size=13)
        
        icon = QLabel()
        icon.setPixmap(pixmap)
        icon.setFixedSize(14, 14)
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("background: transparent; border: none;")

        ts = QLabel(timestamp)
        ts.setFixedWidth(56)
        ts.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_SECONDARY};
                font-size: 10px;
                font-family: {Typography.FAMILY};
                background: transparent;
                border: none;
            }}
        """)

        clean_msg = clean_emoji_prefixes(message)
        msg_lbl = QLabel(clean_msg)
        msg_lbl.setWordWrap(True)
        msg_lbl.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_PRIMARY};
                font-size: 12px;
                font-family: {Typography.FAMILY};
                font-weight: 400;
                background: transparent;
                border: none;
            }}
        """)

        layout.addWidget(icon)
        layout.addWidget(ts)
        layout.addWidget(msg_lbl, 1)
        self.setLayout(layout)


# ── Observability Dashboard Panel ──────────────────────────────────────────────

class DebugPanel(QWidget):
    resumeClicked = pyqtSignal()
    abortClicked = pyqtSignal()
    emergency_stop = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ClickBit Dashboard")
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(450, 620)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(Spacing.SM)

        # 1. Main outer dark glassmorphism card
        self.container = GlassCard(self, rounded_radius=16)
        inner_layout = QVBoxLayout(self.container)
        inner_layout.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        inner_layout.setSpacing(Spacing.MD)

        # 2. Header Row
        header = QHBoxLayout()
        header.setSpacing(Spacing.SM)
        
        # Centralized State Indicator
        self.panel_orb = StatusOrb(self.container, size=16)
        self.panel_orb.set_state(UIState.IDLE)
        header.addWidget(self.panel_orb, 0, Qt.AlignVCenter)

        title = QLabel("ClickBit Dashboard")
        title.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_PRIMARY};
                font-family: {Typography.FAMILY};
                font-weight: 600;
                font-size: 14px;
                background: transparent;
                border: none;
            }}
        """)
        header.addWidget(title, 1, Qt.AlignVCenter)

        # Translucent Stop Button
        self._stop_btn = QPushButton("Stop", self.container)
        self._stop_btn.setCursor(Qt.PointingHandCursor)
        self._stop_btn.setFixedHeight(26)
        self._stop_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(239, 68, 68, 0.12);
                color: {Colors.RED};
                border: 1px solid rgba(239, 68, 68, 0.25);
                border-radius: 6px;
                padding: 0 12px;
                font-family: {Typography.FAMILY};
                font-size: 11px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: rgba(239, 68, 68, 0.20);
                border-color: rgba(239, 68, 68, 0.40);
            }}
            QPushButton:pressed {{
                background-color: rgba(239, 68, 68, 0.15);
            }}
        """)
        self._stop_btn.clicked.connect(self.emergency_stop.emit)
        header.addWidget(self._stop_btn, 0, Qt.AlignVCenter)

        # Flat Vector Close Button
        self._close_btn = IconButton("x", self.container, size=24, icon_size=12)
        self._close_btn.clicked.connect(self.hide)
        header.addWidget(self._close_btn, 0, Qt.AlignVCenter)
        
        inner_layout.addLayout(header)

        # 3. Pinned Live State Card (Sub-surface Glass)
        self._state_card = GlassCard(self.container, rounded_radius=10, border_color=Colors.BORDER_LIGHT)
        state_layout = QVBoxLayout(self._state_card)
        state_layout.setSpacing(Spacing.SM)
        state_layout.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)

        # Goal row
        goal_row = QHBoxLayout()
        goal_row.setSpacing(Spacing.SM)
        
        goal_icon = QLabel()
        goal_icon.setPixmap(get_svg_pixmap("sparkles", Colors.BLUE, 14))
        goal_icon.setFixedSize(14, 14)
        goal_icon.setStyleSheet("background: transparent; border: none;")
        
        self._goal_label = QLabel("Waiting for task…")
        self._goal_label.setWordWrap(True)
        self._goal_label.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_PRIMARY};
                font-size: 12px;
                font-family: {Typography.FAMILY};
                font-weight: 600;
                background: transparent;
                border: none;
            }}
        """)
        goal_row.addWidget(goal_icon)
        goal_row.addWidget(self._goal_label, 1)
        state_layout.addLayout(goal_row)

        # Reasoning row
        reason_row = QHBoxLayout()
        reason_row.setSpacing(Spacing.SM)
        
        reason_icon = QLabel()
        reason_icon.setPixmap(get_svg_pixmap("brain", Colors.TEXT_SECONDARY, 14))
        reason_icon.setFixedSize(14, 14)
        reason_icon.setStyleSheet("background: transparent; border: none;")
        
        self._reasoning_label = QLabel("—")
        self._reasoning_label.setWordWrap(True)
        self._reasoning_label.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_SECONDARY};
                font-size: 11px;
                font-family: {Typography.FAMILY};
                font-style: italic;
                background: transparent;
                border: none;
            }}
        """)
        reason_row.addWidget(reason_icon)
        reason_row.addWidget(self._reasoning_label, 1)
        state_layout.addLayout(reason_row)

        # Action row
        action_row = QHBoxLayout()
        action_row.setSpacing(Spacing.SM)
        
        action_icon = QLabel()
        action_icon.setPixmap(get_svg_pixmap("play", Colors.INDIGO, 14))
        action_icon.setFixedSize(14, 14)
        action_icon.setStyleSheet("background: transparent; border: none;")
        
        self._action_label = QLabel("—")
        self._action_label.setStyleSheet(f"""
            QLabel {{
                color: {Colors.INDIGO};
                font-size: 11px;
                font-family: Consolas, monospace;
                font-weight: 600;
                background: transparent;
                border: none;
            }}
        """)
        action_row.addWidget(action_icon)
        action_row.addWidget(self._action_label, 1)
        state_layout.addLayout(action_row)

        # Confidence bar
        conf_row = QHBoxLayout()
        conf_row.setSpacing(Spacing.SM)
        
        conf_lbl = QLabel("Confidence")
        conf_lbl.setFixedWidth(72)
        conf_lbl.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_SECONDARY};
                font-size: 10px;
                font-family: {Typography.FAMILY};
                background: transparent;
                border: none;
            }}
        """)
        
        self._conf_bar = QProgressBar()
        self._conf_bar.setRange(0, 100)
        self._conf_bar.setValue(0)
        self._conf_bar.setFixedHeight(6)
        self._conf_bar.setTextVisible(False)
        self._conf_bar.setStyleSheet(f"""
            QProgressBar {{
                background: rgba(0, 0, 0, 0.06);
                border-radius: 3px;
                border: none;
            }}
            QProgressBar::chunk {{
                background: {Colors.INDIGO};
                border-radius: 3px;
            }}
        """)
        
        self._conf_pct = QLabel("0%")
        self._conf_pct.setFixedWidth(32)
        self._conf_pct.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._conf_pct.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_SECONDARY};
                font-size: 10px;
                font-family: {Typography.FAMILY};
                background: transparent;
                border: none;
            }}
        """)
        
        conf_row.addWidget(conf_lbl)
        conf_row.addWidget(self._conf_bar, 1)
        conf_row.addWidget(self._conf_pct)
        state_layout.addLayout(conf_row)

        inner_layout.addWidget(self._state_card)

        # 4. Intervention Card (hidden by default)
        self._intervention_card = GlassCard(self.container, rounded_radius=10, border_color=Colors.RED)
        self._intervention_card.hide()
        inter_layout = QVBoxLayout(self._intervention_card)
        inter_layout.setSpacing(Spacing.SM)
        inter_layout.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        
        # Title row with alert icon
        inter_title_row = QHBoxLayout()
        inter_title_row.setSpacing(Spacing.SM)
        
        alert_icon = QLabel()
        alert_icon.setPixmap(get_svg_pixmap("alert_triangle", Colors.RED, 14))
        alert_icon.setFixedSize(14, 14)
        alert_icon.setStyleSheet("background: transparent; border: none;")
        inter_title_row.addWidget(alert_icon)
        
        self._intervention_issue = QLabel("Issue: ")
        self._intervention_issue.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_PRIMARY};
                font-size: 12px;
                font-family: {Typography.FAMILY};
                font-weight: 600;
                background: transparent;
                border: none;
            }}
        """)
        inter_title_row.addWidget(self._intervention_issue, 1)
        inter_layout.addLayout(inter_title_row)
        
        self._intervention_desc = QLabel("Human verification required.")
        self._intervention_desc.setWordWrap(True)
        self._intervention_desc.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_SECONDARY};
                font-size: 11px;
                font-family: {Typography.FAMILY};
                background: transparent;
                border: none;
            }}
        """)
        inter_layout.addWidget(self._intervention_desc)
        
        btn_row = QHBoxLayout()
        btn_row.setSpacing(Spacing.SM)
        
        self._resume_btn = QPushButton("Resume", self._intervention_card)
        self._resume_btn.setCursor(Qt.PointingHandCursor)
        self._resume_btn.setFixedHeight(28)
        self._resume_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(16, 185, 129, 0.12);
                color: {Colors.GREEN};
                border: 1px solid rgba(16, 185, 129, 0.25);
                border-radius: 6px;
                font-family: {Typography.FAMILY};
                font-size: 11px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: rgba(16, 185, 129, 0.20);
                border-color: rgba(16, 185, 129, 0.40);
            }}
        """)
        
        self._abort_btn = QPushButton("Abort", self._intervention_card)
        self._abort_btn.setCursor(Qt.PointingHandCursor)
        self._abort_btn.setFixedHeight(28)
        self._abort_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(239, 68, 68, 0.12);
                color: {Colors.RED};
                border: 1px solid rgba(239, 68, 68, 0.25);
                border-radius: 6px;
                font-family: {Typography.FAMILY};
                font-size: 11px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: rgba(239, 68, 68, 0.20);
                border-color: rgba(239, 68, 68, 0.40);
            }}
        """)
        btn_row.addWidget(self._resume_btn, 1)
        btn_row.addWidget(self._abort_btn, 1)
        inter_layout.addLayout(btn_row)
        
        inner_layout.addWidget(self._intervention_card)
        
        self._resume_btn.clicked.connect(self.resumeClicked.emit)
        self._resume_btn.clicked.connect(self._intervention_card.hide)
        self._abort_btn.clicked.connect(self.abortClicked.emit)

        # 5. Activity Feed Section
        feed_label = QLabel("Activity Timeline")
        feed_label.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_SECONDARY};
                font-size: 10px;
                font-weight: 600;
                font-family: {Typography.FAMILY};
                letter-spacing: 0.5px;
                background: transparent;
                border: none;
                margin-top: 4px;
            }}
        """)
        inner_layout.addWidget(feed_label)

        self.event_list = QListWidget()
        self.event_list.setStyleSheet(f"""
            QListWidget {{
                background: rgba(0, 0, 0, 0.03);
                border: 1px solid {Colors.BORDER_LIGHT};
                border-radius: 10px;
                padding: 4px;
                outline: none;
            }}
            QScrollBar:vertical {{
                border: none;
                background: transparent;
                width: 6px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(0, 0, 0, 0.12);
                min-height: 20px;
                border-radius: 3px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: rgba(0, 0, 0, 0.20);
            }}
            QListWidget::item {{
                border-bottom: 1px solid rgba(0, 0, 0, 0.04);
                padding: 2px 0px;
            }}
            QListWidget::item:selected {{
                background: transparent;
            }}
        """)
        inner_layout.addWidget(self.event_list, 1)

        # 6. Footer Layout
        footer = QHBoxLayout()
        self._iter_label = QLabel("Iteration: 0")
        self._iter_label.setStyleSheet(f"""
            QLabel {{
                color: {Colors.TEXT_SECONDARY};
                font-size: 10px;
                font-family: {Typography.FAMILY};
                background: transparent;
                border: none;
            }}
        """)
        footer.addWidget(self._iter_label)
        footer.addStretch()

        clear_btn = QPushButton("Clear Timeline", self.container)
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.setFixedHeight(24)
        clear_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {Colors.TEXT_SECONDARY};
                border: 1px solid {Colors.BORDER_GLASS};
                border-radius: 6px;
                padding: 0 10px;
                font-family: {Typography.FAMILY};
                font-size: 11px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {Colors.TRANSLUCENT_WHITE};
                color: {Colors.TEXT_PRIMARY};
            }}
        """)
        clear_btn.clicked.connect(self.event_list.clear)
        footer.addWidget(clear_btn)
        
        inner_layout.addLayout(footer)

        root.addWidget(self.container)
        self.setLayout(root)
        self._drag_start = None

    # ── Public Slots ───────────────────────────────────────────────────────────

    @pyqtSlot(str, str, str)
    def add_event(self, event_type: str, message: str, status: str = "info"):
        """Add one row to the timeline feed AND update the live state card."""
        timestamp = QDateTime.currentDateTime().toString("hh:mm:ss")

        # Map state and color panel orb based on event type
        if event_type == "error":
            self.panel_orb.set_state(UIState.ERROR)
        elif event_type == "success":
            self.panel_orb.set_state(UIState.SUCCESS)
        elif event_type == "planning":
            self.panel_orb.set_state(UIState.THINKING)
        elif event_type == "action":
            self.panel_orb.set_state(UIState.EXECUTING)
        elif event_type in ("warning", "json_repair", "schema_warning"):
            self.panel_orb.set_state(UIState.WARNING)
        elif event_type == "retry":
            self.panel_orb.set_state(UIState.RECOVERING)

        # Handle human intervention events
        if event_type == "human_intervention":
            self.panel_orb.set_state(UIState.PAUSED)
            parts = message.split(":", 1)
            reason_text = parts[1].strip() if len(parts) > 1 else ""
            clean_reason = clean_emoji_prefixes(reason_text)
            self._intervention_issue.setText(f"Issue: {clean_reason}")
            self._intervention_desc.setText("Please resolve the verification on the page before resuming.")
            self._intervention_card.show()
            if not self.isVisible():
                self.show_at_default()
            return

        # Handle reasoning events
        if event_type == "planning" and ("💭" in message or "planning" in event_type):
            clean = clean_emoji_prefixes(message)
            if "[conf=" in clean:
                parts = clean.rsplit("[conf=", 1)
                reasoning_text = parts[0].strip()
                conf_str = parts[1].replace("]", "").strip()
                try:
                    conf = float(conf_str)
                    self._set_confidence(conf)
                except ValueError:
                    pass
                self._reasoning_label.setText(reasoning_text)
            else:
                self._reasoning_label.setText(clean)

        elif event_type == "plan_update" and ("ROADMAP:" in message or "Roadmap" in message):
            try:
                # E.g. "ROADMAP:33% | Details"
                header_part, roadmap_content = message.split("|", 1)
                pct_str = header_part.replace("ROADMAP:", "").replace("%", "").strip()
                base_goal = self._goal_label.text().split(" (")[0]
                self._goal_label.setText(f"{base_goal} ({pct_str}% Done)")
                message = f"Roadmap Progress: {pct_str}%\n{clean_emoji_prefixes(roadmap_content)}"
            except Exception:
                pass

        elif event_type == "action" and ("Executing:" in message or "⚡" in message):
            cmd = clean_emoji_prefixes(message)
            self._action_label.setText(cmd)

        elif event_type == "info" and "New goal" in message:
            goal_text = message.split(":", 1)[-1].strip()
            self._goal_label.setText(clean_emoji_prefixes(goal_text))

        elif event_type == "info" and "Iteration" in message:
            iteration = message.replace("── Iteration", "").replace("──", "").replace("Iteration:", "").strip()
            self._iter_label.setText(f"Iteration: {clean_emoji_prefixes(iteration)}")

        # Add to feed
        item = QListWidgetItem(self.event_list)
        widget = DebugEventItem(timestamp, event_type, message)
        item.setSizeHint(widget.sizeHint())
        self.event_list.addItem(item)
        self.event_list.setItemWidget(item, widget)
        self.event_list.scrollToBottom()

        # Auto-show on important events
        if event_type in ("error", "planning") and not self.isVisible():
            self.show_at_default()

    def show_at_default(self):
        screen = self.screen().availableGeometry()
        self.move(screen.width() - self.width() - 20, 80)
        self.show()

    def _set_confidence(self, value: float):
        pct = int(max(0.0, min(1.0, value)) * 100)
        self._conf_bar.setValue(pct)
        self._conf_pct.setText(f"{pct}%")
        
        # Color the bar progress based on value
        if pct < 40:
            colour = Colors.RED
        elif pct < 70:
            colour = Colors.AMBER
        else:
            colour = Colors.GREEN
            
        self._conf_bar.setStyleSheet(f"""
            QProgressBar {{
                background: rgba(255, 255, 255, 0.05);
                border-radius: 3px;
                border: none;
            }}
            QProgressBar::chunk {{
                background: {colour};
                border-radius: 3px;
            }}
        """)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start = event.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self._drag_start:
            self.move(event.globalPos() - self._drag_start)
