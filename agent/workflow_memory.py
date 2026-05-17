"""
agent/workflow_memory.py
-------------------------
Persistent SQLite-based storage for successful automation plans.
Allows instant recall of repeated tasks.
"""

import sqlite3
import json
import os
import struct
from datetime import datetime
from utils.logger import get_logger
from agent.semantic_memory import SemanticMemoryEngine

logger = get_logger(__name__)
SIMILARITY_THRESHOLD = float(os.getenv("SEMANTIC_SIMILARITY_THRESHOLD", "0.82"))

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
            # Add embedding column if upgrading from older version
            try:
                cursor.execute("ALTER TABLE workflows ADD COLUMN embedding BLOB")
                conn.commit()
            except sqlite3.OperationalError:
                pass # Column already exists
                
            conn.close()
            
            # Initialize semantic engine lazily
            self.semantic_engine = SemanticMemoryEngine()
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
                logger.info(f"Exact Memory HIT: Found cached plan for '{clean_prompt}'")
                return json.loads(row[0])
        except Exception as e:
            logger.error(f"Error reading from exact memory: {e}")
        
        logger.debug(f"Exact Memory MISS: No exact plan for '{clean_prompt}'")
        
        # --- Fallback: Semantic Search ---
        try:
            # Encode the search prompt
            query_vec = self.semantic_engine.encode(clean_prompt)
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT prompt, plan, embedding FROM workflows WHERE success = 1 AND embedding IS NOT NULL")
            rows = cursor.fetchall()
            conn.close()
            
            best_match = None
            highest_score = -1.0
            
            for db_prompt, db_plan, db_embedding_blob in rows:
                if not db_embedding_blob:
                    continue
                try:
                    num_floats = len(db_embedding_blob) // 4
                    db_vec = list(struct.unpack(f"{num_floats}f", db_embedding_blob))
                    score = self.semantic_engine.calculate_similarity(query_vec, db_vec)
                    
                    if score > highest_score:
                        highest_score = score
                        best_match = (db_prompt, db_plan)
                except Exception as ex:
                    logger.warning(f"Failed to unpack embedding for prompt '{db_prompt}': {ex}")
            
            if highest_score >= SIMILARITY_THRESHOLD and best_match:
                logger.info(f"Semantic Memory HIT: '{clean_prompt}' matches '{best_match[0]}' (Score: {highest_score:.2f})")
                return json.loads(best_match[1])
            else:
                if highest_score > 0:
                    logger.debug(f"Semantic Memory MISS: Best match was '{best_match[0]}' with score {highest_score:.2f} (Threshold: {SIMILARITY_THRESHOLD})")
                
        except Exception as e:
            logger.error(f"Error reading from semantic memory: {e}")

    def save_workflow(self, prompt: str, plan: dict, success: bool = True):
        """Saves a successful workflow to the database."""
        if not success:
            return

        clean_prompt = prompt.strip().lower()
        plan_json = json.dumps(plan)
        
        try:
            embedding = self.semantic_engine.encode(clean_prompt)
            # Pack list of floats to binary bytes (each 'f' is 4 bytes float)
            embedding_blob = struct.pack(f"{len(embedding)}f", *embedding)
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Using parameter substitution to safely insert
            cursor.execute("""
                INSERT OR REPLACE INTO workflows (prompt, plan, success, timestamp, embedding)
                VALUES (?, ?, ?, ?, ?)
            """, (clean_prompt, plan_json, 1 if success else 0, datetime.now(), embedding_blob))
            
            conn.commit()
            conn.close()
            logger.info(f"Memory SAVED: Workflow for '{clean_prompt}' cached and embedded successfully.")
        except Exception as e:
            logger.error(f"Failed to save workflow to memory: {e}")
