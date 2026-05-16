"""
agent/workflow_memory.py
-------------------------
Persistent SQLite-based storage for successful automation plans.
Allows instant recall of repeated tasks.
"""

import sqlite3
import json
import os
from datetime import datetime
from utils.logger import get_logger

logger = get_logger(__name__)

class WorkflowMemory:
    """
    Manages the workflows.db database.
    Stores and retrieves successful plans based on prompt similarity.
    """

    def __init__(self, db_path: str = "workflows.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Creates the workflows table if it doesn't exist."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS workflows (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    prompt TEXT UNIQUE,
                    plan TEXT,
                    success INTEGER,
                    timestamp DATETIME
                )
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to initialize WorkflowMemory: {e}")

    def get_cached_plan(self, prompt: str) -> dict:
        """
        Retrieves a cached plan if an exact or highly similar prompt exists.
        Currently uses simple lowercase normalization.
        """
        clean_prompt = prompt.strip().lower()
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT plan FROM workflows WHERE prompt = ? AND success = 1", (clean_prompt,))
            row = cursor.fetchone()
            conn.close()
            
            if row:
                logger.info(f"Memory HIT: Found cached plan for '{clean_prompt}'")
                return json.loads(row[0])
        except Exception as e:
            logger.error(f"Error reading from memory: {e}")
        
        logger.debug(f"Memory MISS: No cached plan for '{clean_prompt}'")
        return None

    def save_workflow(self, prompt: str, plan: dict, success: bool = True):
        """Saves a successful workflow to the database."""
        if not success:
            return

        clean_prompt = prompt.strip().lower()
        plan_json = json.dumps(plan)
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO workflows (prompt, plan, success, timestamp)
                VALUES (?, ?, ?, ?)
            """, (clean_prompt, plan_json, 1 if success else 0, datetime.now()))
            conn.commit()
            conn.close()
            logger.info(f"Memory SAVED: Workflow for '{clean_prompt}' cached successfully.")
        except Exception as e:
            logger.error(f"Failed to save workflow to memory: {e}")
