"""
agent/memory.py
----------------
Simple in-memory conversation history for the Mistral planner.
Keeps the last N messages so the model has short-term context.
"""

from utils.logger import get_logger

logger = get_logger(__name__)

# Maximum number of messages stored in memory
MAX_HISTORY = 10


class Memory:
    """
    Maintains a rolling window of conversation messages.
    Each message is a dict: {"role": "user"|"assistant", "content": str}
    """

    def __init__(self, max_size: int = MAX_HISTORY):
        self._history: list[dict] = []
        self._max_size = max_size
        logger.debug(f"Memory initialised (max={max_size})")

    def add(self, role: str, content: str) -> None:
        """Append a message and trim to max_size."""
        self._history.append({"role": role, "content": content})
        if len(self._history) > self._max_size:
            # Drop oldest message when limit is exceeded
            self._history.pop(0)
        logger.debug(f"Memory add [{role}]: {content[:60]}…")

    def get_history(self) -> list[dict]:
        """Return a copy of the current message history."""
        return list(self._history)

    def clear(self) -> None:
        """Wipe conversation history."""
        self._history.clear()
        logger.info("Memory cleared")

    def __len__(self) -> int:
        return len(self._history)
