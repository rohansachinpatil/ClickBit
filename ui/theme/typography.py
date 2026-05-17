"""
ui/theme/typography.py
-----------------------
Typography scale and system-native font hierarchy for ClickBit.
Supports Segoe UI Variable, Inter, and Apple SF Pro.
"""

class Typography:
    # ── Native Font Family Hierarchy ──────────────────────────────────────────
    FAMILY = "Segoe UI Variable Text, Inter, -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', Roboto, sans-serif"
    
    # ── Text Constants ───────────────────────────────────────────────────────
    FONT_HEADING_SIZE = 14
    FONT_INPUT_SIZE = 22
    FONT_BODY_SIZE = 12
    FONT_METADATA_SIZE = 10
    
    FONT_HEADING_WEIGHT = "600" # Semibold
    FONT_INPUT_WEIGHT = "300"   # Light
    FONT_BODY_WEIGHT = "500"    # Medium
    FONT_METADATA_WEIGHT = "400"# Regular
