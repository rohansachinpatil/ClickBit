"""
tests/test_ui_theme.py
----------------------
Unit tests for the new ClickBit Design Tokens System, Icon System, and State Engine.
"""

import sys
import unittest
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QIcon, QPixmap
from ui.theme import Colors, UIState, Typography, Spacing, get_svg_icon, get_svg_pixmap
from ui.components import GlassCard, StatusOrb, IconButton, AnimatedChip

# Instantiate QApplication once for GUI test cases
app = QApplication.instance() or QApplication(sys.argv)

class TestUITheme(unittest.TestCase):
    def test_colors_presence(self):
        """Verify new premium theme colors exist and are not legacy light green."""
        self.assertEqual(Colors.NAVY_GLASS, "rgba(255, 255, 255, 0.85)")
        self.assertEqual(Colors.TEXT_PRIMARY, "#111827")
        self.assertEqual(Colors.GREEN, "#16a34a")
        self.assertEqual(Colors.RED, "#dc2626")
        self.assertEqual(Colors.AMBER, "#d97706")

    def test_state_color_mapping(self):
        """Verify UIState colors match semantic definitions."""
        self.assertEqual(Colors.get_state_color(UIState.IDLE), "#6b7280")
        self.assertEqual(Colors.get_state_color(UIState.THINKING), Colors.BLUE)
        self.assertEqual(Colors.get_state_color(UIState.EXECUTING), Colors.INDIGO)
        self.assertEqual(Colors.get_state_color(UIState.SUCCESS), Colors.GREEN)
        self.assertEqual(Colors.get_state_color(UIState.ERROR), Colors.RED)

    def test_typography_constants(self):
        """Verify native font stacks and sizes are correctly declared."""
        self.assertTrue("Segoe UI" in Typography.FAMILY)
        self.assertEqual(Typography.FONT_INPUT_SIZE, 22)
        self.assertEqual(Typography.FONT_BODY_SIZE, 12)

    def test_spacing_constants(self):
        """Verify spacing scale matches standard design increments."""
        self.assertEqual(Spacing.XS, 4)
        self.assertEqual(Spacing.SM, 8)
        self.assertEqual(Spacing.MD, 12)
        self.assertEqual(Spacing.LG, 20)
        self.assertEqual(Spacing.XL, 32)

    def test_vector_icon_rendering(self):
        """Verify that Lucide monochrome SVG renderer loads templates and scales them."""
        # Test valid icon
        icon = get_svg_icon("search", Colors.BLUE, size=16)
        self.assertIsInstance(icon, QIcon)
        self.assertFalse(icon.isNull())
        
        pixmap = get_svg_pixmap("brain", Colors.INDIGO, size=24)
        self.assertIsInstance(pixmap, QPixmap)
        self.assertFalse(pixmap.isNull())
        self.assertEqual(pixmap.width(), 24)

        # Test invalid icon fallback
        invalid_icon = get_svg_icon("non_existent_icon")
        self.assertIsInstance(invalid_icon, QIcon)
        self.assertTrue(invalid_icon.isNull())

    def test_components_instantiation(self):
        """Verify premium custom components initialize without crashes."""
        card = GlassCard()
        self.assertIsNotNone(card)
        
        orb = StatusOrb()
        self.assertIsNotNone(orb)
        self.assertEqual(orb._state, UIState.IDLE)
        
        btn = IconButton("play")
        self.assertIsNotNone(btn)
        
        chip = AnimatedChip("Executing", state=UIState.EXECUTING)
        self.assertIsNotNone(chip)

if __name__ == "__main__":
    unittest.main()
