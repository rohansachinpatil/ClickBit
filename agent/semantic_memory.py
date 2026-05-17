import os
import json
import math
import struct
from typing import List
from utils.logger import get_logger

logger = get_logger(__name__)

class SemanticMemoryEngine:
    """
    Computes vector embeddings using Mistral API to avoid heavy local dependencies
    and prevent PyTorch DLL crashes on Windows.
    Uses pure-Python math/struct for zero external library footprint.
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SemanticMemoryEngine, cls).__new__(cls)
        return cls._instance

    def encode(self, text: str) -> List[float]:
        """Converts a prompt into a high-dimensional vector using Mistral Embeddings."""
        api_key = os.getenv("MISTRAL_API_KEY")
        if not api_key:
            logger.error("MISTRAL_API_KEY not set. Semantic memory disabled.")
            return [0.0] * 1024
            
        try:
            import httpx
            # Mistral embeddings API
            url = "https://api.mistral.ai/v1/embeddings"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            data = {
                "model": "mistral-embed",
                "input": [text.strip().lower()]
            }
            
            response = httpx.post(url, headers=headers, json=data, timeout=10.0)
            response.raise_for_status()
            
            embedding = response.json()["data"][0]["embedding"]
            
            # Normalize vector for cosine similarity
            sq_sum = sum(x * x for x in embedding)
            norm = math.sqrt(sq_sum)
            if norm > 0:
                embedding = [x / norm for x in embedding]
                
            return embedding
        except Exception as e:
            logger.error(f"Failed to generate embedding from Mistral: {e}")
            return [0.0] * 1024
        
    def calculate_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculates cosine similarity between two normalized vectors."""
        # Graceful fallback: check if either is the zero vector
        if not vec1 or not vec2 or all(x == 0.0 for x in vec1) or all(x == 0.0 for x in vec2):
            return 0.0
            
        # Cosine similarity of normalized vectors is their dot product
        try:
            return float(sum(a * b for a, b in zip(vec1, vec2)))
        except Exception as e:
            logger.error(f"Failed to calculate similarity: {e}")
            return 0.0
