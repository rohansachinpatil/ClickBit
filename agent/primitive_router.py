"""
agent/primitive_router.py
-------------------------
Deterministic router mapping high-level semantic intents from ActionDecider/Mistral
directly into primitive action workflows, avoiding conversational click loops.
"""

from playwright.sync_api import Page
from utils.logger import get_logger
from automation.primitive_actions import PrimitiveActions

logger = get_logger(__name__)

class PrimitiveRouter:
    """Validates and executes structured high-level user intents synchronously and deterministically."""
    
    @staticmethod
    def is_primitive(intent: str) -> bool:
        """Checks if the intent is recognized as a deterministic primitive action."""
        if not intent:
            return False
        return intent.strip().lower() in (
            "youtube_search",
            "google_search",
            "play_video",
            "play_first_video",
            "dismiss_overlay",
            "close_modal"
        )

    @staticmethod
    def execute(page: Page, intent: str, argument: str = "") -> dict:
        """Synchronously routes and invokes the respective primitive, returning structured telemetry."""
        logger.info(f"[PrimitiveRouter] Routing semantic intent '{intent}' with argument '{argument}'")
        
        intent_clean = intent.strip().lower()
        if intent_clean == "youtube_search":
            return PrimitiveActions.youtube_search(page, argument)
        elif intent_clean == "google_search":
            return PrimitiveActions.google_search(page, argument)
        elif intent_clean in ("play_video", "play_first_video"):
            return PrimitiveActions.play_first_video(page, argument)
        elif intent_clean in ("dismiss_overlay", "close_modal"):
            return PrimitiveActions.dismiss_overlay(page, argument)
        else:
            raise ValueError(f"Unknown primitive intent: {intent}")
