"""
agent/router.py
----------------
Smart routing logic to decide between Local (Ollama) and Cloud (Mistral).
"""

import os
import time
import httpx
import json
from utils.logger import get_logger

logger = get_logger(__name__)

class Router:
    """
    Decides whether a prompt is simple enough for local inference (Ollama)
    or requires cloud reasoning (Mistral).
    """

    def __init__(self):
        self.ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.local_model = os.getenv("LOCAL_MODEL_NAME", "qwen2.5:1.5b")
        self.enable_local = os.getenv("ENABLE_LOCAL_ROUTING", "True").lower() == "true"
        self.threshold = int(os.getenv("ROUTING_COMPLEXITY_THRESHOLD", "3"))

    def get_routing_decision(self, prompt: str) -> str:
        """
        Classifies prompt into 'local' or 'cloud'.
        Logic: 
        - Simple tasks (open, search, type) go to local.
        - Multi-step or ambiguous tasks go to cloud.
        """
        if not self.enable_local:
            return "cloud"

        # Simple classification heuristics
        p = prompt.lower()
        
        # Indicators of complexity (routing to Cloud)
        complexity_markers = ["best", "decide", "choose", "analyze", "if", "then", "according to"]
        word_count = len(p.split())
        
        # If too many words or contains complexity markers -> Cloud
        if word_count > 10 or any(m in p for m in complexity_markers):
            logger.info(f"Routing to CLOUD: Complexity detected (words={word_count})")
            return "cloud"
            
        # Common simple commands -> Local
        simple_keywords = ["open", "search", "go to", "type", "hello", "launch", "youtube", "google"]
        if any(kw in p for kw in simple_keywords):
            logger.info(f"Routing to LOCAL: Simple command recognized")
            return "local"

        # Default fallback for ambiguous tasks
        logger.info("Routing to CLOUD: Defaulting for ambiguity")
        return "cloud"

    def get_local_plan(self, prompt: str, system_prompt: str) -> dict:
        """
        Calls Ollama to generate a plan locally.
        """
        logger.info(f"Inference via LOCAL MODEL ({self.local_model})...")
        start_time = time.time()
        
        try:
            payload = {
                "model": self.local_model,
                "prompt": f"{system_prompt}\n\nUser Task: {prompt}",
                "stream": False,
                "format": "json"
            }
            
            response = httpx.post(
                f"{self.ollama_url}/api/generate",
                json=payload,
                timeout=10.0
            )
            response.raise_for_status()
            
            latency = time.time() - start_time
            result = response.json().get("response", "{}")
            logger.info(f"Local inference complete (latency: {latency:.2f}s)")
            
            return json.loads(result)
            
        except Exception as e:
            logger.warning(f"Local inference failed: {e}. Falling back to cloud...")
            return None # Trigger cloud fallback
