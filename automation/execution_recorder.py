"""
automation/execution_recorder.py
--------------------------------
Deterministic Execution Replay System & Visual Observability Engine.
Records lightweight, async event frames of ClickBit's execution trajectory without blocking the main loop.
"""

import os
import json
import time
import hashlib
import queue
import threading
import uuid
import tempfile
import zipfile
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any, List
from io import BytesIO

from utils.logger import get_logger

try:
    from PIL import Image, ImageChops, ImageDraw
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

logger = get_logger(__name__)

# Base storage directory
SESSIONS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sessions")


@dataclass
class ExecutionFrame:
    """Represents a single deterministic execution cycle step."""
    frame_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    iteration: int = 0
    session_id: str = ""
    
    # States
    before_state: Dict[str, Any] = field(default_factory=dict)
    after_state: Dict[str, Any] = field(default_factory=dict)
    
    # Action Specs
    command: str = ""
    argument: str = ""
    primitive_used: bool = False
    primitive_name: str = ""
    execution_mode: str = "llm"  # "llm", "deterministic_primitive", "skill_replay"
    confidence: float = 0.0
    reasoning: str = ""
    
    # Validation Specs
    transition_score: float = 0.0
    transition_type: str = "no_change"
    action_success: bool = False
    recovery_triggered: bool = False
    blacklisted: bool = False
    
    # Media Paths (relative to session dir)
    before_screenshot_path: str = ""
    after_screenshot_path: str = ""
    diff_screenshot_path: str = ""
    
    # Performance Latency Metrics
    observe_latency_ms: int = 0
    reasoning_latency_ms: int = 0
    execution_latency_ms: int = 0
    validation_latency_ms: int = 0


class ExecutionRecorder:
    """
    Decoupled subsystem that buffers and serializes execution telemetry
    asynchronously using JSONL, ensuring zero UI/runtime lag.
    """
    
    def __init__(self):
        os.makedirs(SESSIONS_DIR, exist_ok=True)
        self._index_path = os.path.join(SESSIONS_DIR, "index.json")
        self._ensure_index()
        
        self.session_id: Optional[str] = None
        self.session_dir: Optional[str] = None
        self.screenshots_dir: Optional[str] = None
        self.diffs_dir: Optional[str] = None
        self.timeline_path: Optional[str] = None
        self.metadata_path: Optional[str] = None
        
        # Async writing mechanisms
        self._write_queue = queue.Queue()
        self._worker_thread = None
        self._stop_event = threading.Event()
        
        # In-memory analytics accumulation
        self._metadata = {
            "session_id": "",
            "goal": "",
            "started_at": "",
            "completed": False,
            "total_frames": 0,
            "recoveries": 0,
            "primitive_success_rate": {"total": 0, "success": 0},
            "blacklisted_actions": 0,
            "avg_observe_latency_ms": 0,
            "avg_reasoning_latency_ms": 0,
            "avg_execution_latency_ms": 0,
            "avg_transition_score": 0.0
        }

    def _ensure_index(self):
        """Creates the session registry index if missing."""
        if not os.path.exists(self._index_path):
            with open(self._index_path, "w", encoding="utf-8") as f:
                json.dump({"sessions": []}, f, indent=2)

    def _update_index(self):
        """Updates the global session registry."""
        if not self.session_id:
            return
            
        try:
            with open(self._index_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {"sessions": []}
            
        # Update or append
        existing = next((s for s in data["sessions"] if s["session_id"] == self.session_id), None)
        if existing:
            existing.update({
                "completed": self._metadata["completed"],
                "total_frames": self._metadata["total_frames"],
                "duration_seconds": int(time.time()) - self._session_start_time
            })
        else:
            data["sessions"].append({
                "session_id": self.session_id,
                "goal": self._metadata["goal"],
                "timestamp": self._metadata["started_at"],
                "completed": self._metadata["completed"],
                "total_frames": self._metadata["total_frames"],
                "duration_seconds": 0
            })
            
        with open(self._index_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def start_session(self, goal: str) -> str:
        """Initializes a new recording session and starts the background worker."""
        self.session_id = str(uuid.uuid4())
        self._session_start_time = int(time.time())
        
        self.session_dir = os.path.join(SESSIONS_DIR, self.session_id)
        self.screenshots_dir = os.path.join(self.session_dir, "screenshots")
        self.diffs_dir = os.path.join(self.session_dir, "diffs")
        self.timeline_path = os.path.join(self.session_dir, "timeline.jsonl")
        self.metadata_path = os.path.join(self.session_dir, "metadata.json")
        
        os.makedirs(self.screenshots_dir, exist_ok=True)
        os.makedirs(self.diffs_dir, exist_ok=True)
        
        # Initialize timeline file
        open(self.timeline_path, "w", encoding="utf-8").close()
        
        self._metadata.update({
            "session_id": self.session_id,
            "goal": goal,
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")
        })
        self._flush_metadata()
        self._update_index()
        
        # Start async worker
        self._stop_event.clear()
        self._worker_thread = threading.Thread(target=self._async_flush_worker, daemon=True)
        self._worker_thread.start()
        
        logger.info(f"[ExecutionRecorder] Started session {self.session_id}")
        return self.session_id

    def stop_session(self, completed: bool = False):
        """Signals the background worker to stop and flushes final metadata."""
        if not self.session_id: return
        
        self._metadata["completed"] = completed
        self._stop_event.set()
        
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=5.0)
            
        self._flush_metadata()
        self._update_index()
        logger.info(f"[ExecutionRecorder] Stopped session {self.session_id}")

    def record_frame(self, frame: ExecutionFrame):
        """Enqueues a frame for async disk writing."""
        if not self.session_id: return
        frame.session_id = self.session_id
        
        # Update running analytics
        n = self._metadata["total_frames"]
        self._metadata["avg_observe_latency_ms"] = (self._metadata["avg_observe_latency_ms"] * n + frame.observe_latency_ms) / (n + 1)
        self._metadata["avg_reasoning_latency_ms"] = (self._metadata["avg_reasoning_latency_ms"] * n + frame.reasoning_latency_ms) / (n + 1)
        self._metadata["avg_execution_latency_ms"] = (self._metadata["avg_execution_latency_ms"] * n + frame.execution_latency_ms) / (n + 1)
        self._metadata["avg_transition_score"] = (self._metadata["avg_transition_score"] * n + frame.transition_score) / (n + 1)
        
        if frame.primitive_used:
            self._metadata["primitive_success_rate"]["total"] += 1
            if frame.action_success:
                self._metadata["primitive_success_rate"]["success"] += 1
                
        if frame.recovery_triggered:
            self._metadata["recoveries"] += 1
        if frame.blacklisted:
            self._metadata["blacklisted_actions"] += 1
            
        self._metadata["total_frames"] += 1
        
        self._write_queue.put({"type": "frame", "data": asdict(frame)})
        self._write_queue.put({"type": "metadata", "data": self._metadata.copy()})

    def _async_flush_worker(self):
        """Background thread processing queue writes to ensure zero UI lag."""
        while not self._stop_event.is_set() or not self._write_queue.empty():
            try:
                task = self._write_queue.get(timeout=0.1)
                
                if task["type"] == "frame":
                    with open(self.timeline_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps(task["data"]) + "\n")
                elif task["type"] == "metadata":
                    with open(self.metadata_path, "w", encoding="utf-8") as f:
                        json.dump(task["data"], f, indent=2)
                        
                self._write_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"[ExecutionRecorder] Async write failure: {e}", exc_info=True)

    def _flush_metadata(self):
        """Synchronously forces a metadata write."""
        if self.metadata_path:
            with open(self.metadata_path, "w", encoding="utf-8") as f:
                json.dump(self._metadata, f, indent=2)

    # ── Media Processors ────────────────────────────────────────────────────────

    @staticmethod
    def capture_and_compress_screenshot(page, target_path: str) -> bool:
        """
        Captures a Playwright page screenshot and applies 2-stage optimization:
        A: Resizes to max width 1280 (preserving aspect).
        B: Adaptive JPEG quality compression (72-78) ensuring file < 120KB.
        """
        if not PIL_AVAILABLE or not page: return False
        
        try:
            # Capture raw byte stream in memory
            raw_png = page.screenshot(type="png", full_page=False)
            img = Image.open(BytesIO(raw_png))
            
            # Stage A: Resize
            MAX_WIDTH = 1280
            if img.width > MAX_WIDTH:
                ratio = MAX_WIDTH / float(img.width)
                new_height = int(float(img.height) * float(ratio))
                img = img.resize((MAX_WIDTH, new_height), Image.Resampling.LANCZOS)
                
            img = img.convert("RGB")
            
            # Stage B: Adaptive Quality
            # Start at 78, drop if byte size too large
            quality = 78
            while quality >= 60:
                out = BytesIO()
                img.save(out, format="JPEG", quality=quality)
                size_kb = len(out.getvalue()) / 1024
                if size_kb <= 120:
                    break
                quality -= 4
                
            with open(target_path, "wb") as f:
                f.write(out.getvalue())
            return True
            
        except Exception as e:
            logger.error(f"[ExecutionRecorder] Screenshot compression failed: {e}")
            return False

    @staticmethod
    def compute_visual_diff(before_path: str, after_path: str, diff_path: str) -> float:
        """
        Computes lightweight perceptual difference.
        1. Fast md5 hash skip filter.
        2. Bounding-box translucent red highlighting over original image.
        Returns percentage of changed pixels.
        """
        if not PIL_AVAILABLE: return 0.0
        
        try:
            # 1. Fast Hash Skip Optimization
            with open(before_path, "rb") as f1, open(after_path, "rb") as f2:
                h1 = hashlib.md5(f1.read()).hexdigest()
                h2 = hashlib.md5(f2.read()).hexdigest()
                if h1 == h2:
                    return 0.0

            # 2. Pixel Diffing
            with Image.open(before_path) as img_b, Image.open(after_path) as img_a:
                img_b = img_b.convert("RGB")
                img_a = img_a.convert("RGB")
                
                if img_b.size != img_a.size:
                    img_a = img_a.resize(img_b.size)
                    
                diff = ImageChops.difference(img_b, img_a).convert("L")
                
                # Threshold noise
                binary = diff.point(lambda p: 255 if p > 15 else 0)
                if not binary.getbbox():
                    return 0.0 # No meaningful visual change
                    
                pixels = binary.getdata()
                changed = sum(1 for p in pixels if p > 0)
                percent_changed = (changed / len(pixels)) * 100.0
                
                # Render heatmap overlay on top of "after" image
                base = img_a.convert("RGBA")
                overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
                draw = ImageDraw.Draw(overlay)
                
                # Draw grid blocks (32x32 for speed)
                block_size = 32
                w, h = binary.size
                for y in range(0, h, block_size):
                    for x in range(0, w, block_size):
                        box = (x, y, min(x+block_size, w), min(y+block_size, h))
                        cropped = binary.crop(box)
                        if cropped.getbbox():
                            draw.rectangle(box, fill=(239, 68, 68, 45), outline=(239, 68, 68, 120))
                            
                blended = Image.alpha_composite(base, overlay).convert("RGB")
                blended.save(diff_path, "JPEG", quality=75)
                
                return percent_changed
        except Exception as e:
            logger.error(f"[ExecutionRecorder] Visual diff failure: {e}")
            return 0.0

    # ── Loaders & Exporters ─────────────────────────────────────────────────────

    @staticmethod
    def load_session(session_id: str) -> Dict[str, Any]:
        """Loads a full session into memory for replay rendering."""
        session_dir = os.path.join(SESSIONS_DIR, session_id)
        if not os.path.exists(session_dir):
            raise FileNotFoundError(f"Session {session_id} not found.")
            
        timeline = []
        timeline_path = os.path.join(session_dir, "timeline.jsonl")
        if os.path.exists(timeline_path):
            with open(timeline_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        timeline.append(json.loads(line))
                        
        metadata = {}
        metadata_path = os.path.join(session_dir, "metadata.json")
        if os.path.exists(metadata_path):
            with open(metadata_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
                
        return {
            "session_id": session_id,
            "metadata": metadata,
            "timeline": timeline,
            "session_dir": session_dir
        }

    @staticmethod
    def export_session_zip(session_id: str, output_path: str):
        """Archives a complete session directory for sharing/analysis."""
        session_dir = os.path.join(SESSIONS_DIR, session_id)
        if not os.path.exists(session_dir):
            raise FileNotFoundError(f"Session {session_id} not found.")
            
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(session_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, session_dir)
                    zf.write(file_path, arcname)
