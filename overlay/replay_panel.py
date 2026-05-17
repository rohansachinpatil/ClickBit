"""
overlay/replay_panel.py
-----------------------
Visual Observability Engine and Deterministic Replay Inspector.
Linear/Raycast inspired telemetry scrubbing interface.
"""

import os
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QSlider, QScrollArea, QFrame, QSplitter)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap, QImage, QPainter
from ui.theme import Colors, Typography, Spacing, get_svg_pixmap
from ui.components import GlassCard
from automation.execution_recorder import ExecutionRecorder

class ReplayPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._session_id = None
        self._timeline = []
        self._session_dir = None
        self._current_frame_idx = 0
        
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.MD)
        
        # ── 1. Top Controls (Scrubber) ──────────────────────────────────
        control_card = GlassCard(self, rounded_radius=10)
        control_layout = QVBoxLayout(control_card)
        control_layout.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
        control_layout.setSpacing(Spacing.SM)
        
        header_row = QHBoxLayout()
        self._frame_lbl = QLabel("Frame 0 / 0")
        self._frame_lbl.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-family: {Typography.FAMILY}; font-weight: 600; font-size: 12px;")
        
        self._time_lbl = QLabel("--:--:--")
        self._time_lbl.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-family: Consolas, monospace; font-size: 11px;")
        
        header_row.addWidget(self._frame_lbl)
        header_row.addStretch()
        header_row.addWidget(self._time_lbl)
        control_layout.addLayout(header_row)
        
        self._slider = QSlider(Qt.Horizontal)
        self._slider.setEnabled(False)
        self._slider.setRange(0, 0)
        self._slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                border: none;
                height: 4px;
                background: rgba(0, 0, 0, 0.1);
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {Colors.INDIGO};
                width: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }}
        """)
        self._slider.valueChanged.connect(self._on_slider_scrub)
        control_layout.addWidget(self._slider)
        layout.addWidget(control_card)
        
        # ── 2. Splitter for Media vs Telemetry ──────────────────────────
        self._splitter = QSplitter(Qt.Vertical)
        self._splitter.setStyleSheet("QSplitter::handle { background: transparent; }")
        
        # MEDIA AREA (Before / After / Diff)
        media_widget = QWidget()
        media_layout = QVBoxLayout(media_widget)
        media_layout.setContentsMargins(0, 0, 0, 0)
        media_layout.setSpacing(Spacing.SM)
        
        # Side by Side view
        sbs_layout = QHBoxLayout()
        sbs_layout.setSpacing(Spacing.SM)
        
        self._before_img = QLabel()
        self._before_img.setAlignment(Qt.AlignCenter)
        self._before_img.setStyleSheet(f"background: #fff; border-radius: 6px; border: 1px solid {Colors.BORDER_LIGHT};")
        self._before_img.setMinimumHeight(150)
        
        self._after_img = QLabel()
        self._after_img.setAlignment(Qt.AlignCenter)
        self._after_img.setStyleSheet(f"background: #fff; border-radius: 6px; border: 1px solid {Colors.BORDER_LIGHT};")
        self._after_img.setMinimumHeight(150)
        
        sbs_layout.addWidget(self._before_img, 1)
        sbs_layout.addWidget(self._after_img, 1)
        media_layout.addLayout(sbs_layout)
        
        # Diff View
        self._diff_img = QLabel()
        self._diff_img.setAlignment(Qt.AlignCenter)
        self._diff_img.setStyleSheet(f"background: #f9fafb; border-radius: 6px; border: 1px dashed {Colors.BORDER_LIGHT};")
        self._diff_img.setMinimumHeight(150)
        media_layout.addWidget(self._diff_img, 1)
        
        self._splitter.addWidget(media_widget)
        
        # TELEMETRY AREA
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        
        telemetry_widget = QWidget()
        self._telemetry_layout = QVBoxLayout(telemetry_widget)
        self._telemetry_layout.setContentsMargins(0, Spacing.SM, 0, 0)
        self._telemetry_layout.setSpacing(Spacing.SM)
        
        # Telemetry Cards
        self._action_lbl = self._create_telem_card("play", Colors.INDIGO, "Action", "--")
        self._reason_lbl = self._create_telem_card("brain", Colors.BLUE, "Reasoning", "--")
        self._val_lbl = self._create_telem_card("activity", Colors.GREEN, "Validation", "--")
        self._latency_lbl = self._create_telem_card("clock", Colors.AMBER, "Latencies", "--")
        
        self._telemetry_layout.addStretch()
        scroll.setWidget(telemetry_widget)
        
        self._splitter.addWidget(scroll)
        self._splitter.setSizes([350, 150])
        
        layout.addWidget(self._splitter, 1)
        
    def _create_telem_card(self, icon_name, color, title, initial_val):
        card = GlassCard(self, rounded_radius=8, border_color=Colors.BORDER_LIGHT)
        h_layout = QHBoxLayout(card)
        h_layout.setContentsMargins(Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM)
        h_layout.setSpacing(Spacing.SM)
        
        icon = QLabel()
        icon.setPixmap(get_svg_pixmap(icon_name, color, 14))
        icon.setFixedSize(14, 14)
        h_layout.addWidget(icon, 0, Qt.AlignTop)
        
        v_layout = QVBoxLayout()
        v_layout.setSpacing(2)
        
        t_lbl = QLabel(title)
        t_lbl.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px; font-weight: 600; font-family: {Typography.FAMILY};")
        v_layout.addWidget(t_lbl)
        
        val_lbl = QLabel(initial_val)
        val_lbl.setWordWrap(True)
        val_lbl.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 11px; font-family: {Typography.FAMILY};")
        v_layout.addWidget(val_lbl)
        
        h_layout.addLayout(v_layout, 1)
        self._telemetry_layout.addWidget(card)
        return val_lbl

    def load_session(self, session_id: str):
        """Loads session data via ExecutionRecorder."""
        try:
            data = ExecutionRecorder.load_session(session_id)
            self._session_id = data["session_id"]
            self._session_dir = data["session_dir"]
            self._timeline = data["timeline"]
            
            total = len(self._timeline)
            if total > 0:
                self._slider.setEnabled(True)
                self._slider.setRange(0, total - 1)
                self._slider.setValue(0)
                self._render_frame(0)
            else:
                self._slider.setEnabled(False)
                
        except Exception as e:
            self._frame_lbl.setText(f"Error loading session: {e}")

    def _on_slider_scrub(self, idx: int):
        self._render_frame(idx)
        
    def _render_frame(self, idx: int):
        if not self._timeline or idx < 0 or idx >= len(self._timeline):
            return
            
        frame = self._timeline[idx]
        self._current_frame_idx = idx
        
        # Update Controls
        self._frame_lbl.setText(f"Frame {idx + 1} / {len(self._timeline)}")
        self._time_lbl.setText(frame.get("timestamp", "--:--:--").split("T")[-1])
        
        # Update Media (Lazy Loading)
        self._load_image_safely(frame.get("before_screenshot_path", ""), self._before_img, "screenshots")
        self._load_image_safely(frame.get("after_screenshot_path", ""), self._after_img, "screenshots")
        self._load_image_safely(frame.get("diff_screenshot_path", ""), self._diff_img, "diffs")
        
        # Update Telemetry
        cmd = frame.get("command", "")
        arg = frame.get("argument", "")
        self._action_lbl.setText(f"{cmd}({arg})")
        
        reason = frame.get("reasoning", "")
        conf = frame.get("confidence", 0.0)
        self._reason_lbl.setText(f"{reason}\n(Conf: {conf:.2f})")
        
        score = frame.get("transition_score", 0.0)
        t_type = frame.get("transition_type", "no_change")
        success = frame.get("action_success", False)
        self._val_lbl.setText(f"Score: {score:.2f} | Type: {t_type} | Success: {success}")
        
        obs_l = frame.get("observe_latency_ms", 0)
        rsn_l = frame.get("reasoning_latency_ms", 0)
        exe_l = frame.get("execution_latency_ms", 0)
        val_l = frame.get("validation_latency_ms", 0)
        self._latency_lbl.setText(f"Obs: {obs_l}ms | Think: {rsn_l}ms\nAct: {exe_l}ms | Val: {val_l}ms")
        
    def _load_image_safely(self, filename: str, label: QLabel, subfolder: str):
        if not filename or not self._session_dir:
            label.setText("No Image")
            label.setPixmap(QPixmap())
            return
            
        full_path = os.path.join(self._session_dir, subfolder, filename)
        if os.path.exists(full_path):
            pixmap = QPixmap(full_path)
            # Scale to fit while preserving aspect
            scaled = pixmap.scaled(label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            label.setPixmap(scaled)
        else:
            label.setText("Image Missing")
            label.setPixmap(QPixmap())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Re-render to scale images correctly to new sizes
        if self._timeline:
            self._render_frame(self._current_frame_idx)
