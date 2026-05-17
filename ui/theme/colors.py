"""
ui/theme/colors.py
------------------
Centralized colors and UI State system for ClickBit.
Implements a premium, Apple-style frosted light minimalist design system.
"""

class UIState:
    IDLE = "idle"
    THINKING = "thinking"
    EXECUTING = "executing"
    WARNING = "warning"
    RECOVERING = "recovering"
    PAUSED = "paused"
    SUCCESS = "success"
    ERROR = "error"

class Colors:
    # ── Layered Backgrounds ──────────────────────────────────────────────────
    # Main outer translucent glass background (Frosted Light Glass)
    NAVY_GLASS = "rgba(255, 255, 255, 0.85)"
    
    # Layered card/inner background (Frosted Sub-Surface Card)
    CARD_BG = "rgba(248, 250, 252, 0.92)"
    
    # Ultra-translucent background for chips and overlays (Soft dark-translucent highlight)
    TRANSLUCENT_WHITE = "rgba(0, 0, 0, 0.05)"
    
    # ── Borders ──────────────────────────────────────────────────────────────
    # Soft translucent borders simulating glass reflections
    BORDER_GLASS = "rgba(0, 0, 0, 0.08)"
    BORDER_LIGHT = "rgba(0, 0, 0, 0.04)"
    
    # ── Typography ───────────────────────────────────────────────────────────
    TEXT_PRIMARY = "#111827"      # Crisp near-black charcoal
    TEXT_SECONDARY = "#6b7280"    # Muted cool gray
    TEXT_PLACEHOLDER = "#9ca3af"  # Placeholder gray
    
    # ── Semantic & State Accents (Muted for Light Theme clarity) ─────────────
    BLUE = "#2563eb"       # Thinking/Planning
    INDIGO = "#4f46e5"     # Executing/Browser
    GREEN = "#16a34a"      # Success/Completed
    AMBER = "#d97706"      # Warning/Repaired
    ORANGE = "#ea580c"     # Recovering/Rebuilding
    PURPLE = "#7c3aed"     # Paused/Intervention
    RED = "#dc2626"        # Error/Failed
    
    @staticmethod
    def get_state_color(state: str) -> str:
        """Returns the primary hex/rgba color associated with a UIState."""
        mapping = {
            UIState.IDLE: "#6b7280",
            UIState.THINKING: Colors.BLUE,
            UIState.EXECUTING: Colors.INDIGO,
            UIState.WARNING: Colors.AMBER,
            UIState.RECOVERING: Colors.ORANGE,
            UIState.PAUSED: Colors.PURPLE,
            UIState.SUCCESS: Colors.GREEN,
            UIState.ERROR: Colors.RED,
        }
        return mapping.get(state, "#6b7280")
