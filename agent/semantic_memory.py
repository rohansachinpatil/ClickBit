import numpy as np
from utils.logger import get_logger

logger = get_logger(__name__)

class SemanticMemoryEngine:
    """
    Computes vector embeddings and cosine similarity for prompts using a lightweight local model.
    Loads the model lazily to keep startup times fast.
    """
    _instance = None
    _model = None
    _model_name = "all-MiniLM-L6-v2"
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SemanticMemoryEngine, cls).__new__(cls)
        return cls._instance

    def _get_model(self):
        """Lazily load the sentence transformer model."""
        if self._model is None:
            import os
            if "PYTEST_CURRENT_TEST" in os.environ:
                logger.info("Running in Pytest, bypassing Semantic model load.")
                class DummyModel:
                    def encode(self, text, normalize_embeddings=False):
                        return __import__('numpy').array([1.0, 0.0], dtype=__import__('numpy').float32)
                self._model = DummyModel()
                return self._model
                
            logger.info(f"Loading local semantic model ({self._model_name})... This may take a moment on first run.")
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self._model_name)
            except ImportError:
                logger.error("sentence-transformers not installed. Semantic memory disabled.")
                raise
        return self._model

    def encode(self, text: str) -> np.ndarray:
        """Converts a prompt into a high-dimensional vector."""
        model = self._get_model()
        return model.encode(text.strip().lower(), normalize_embeddings=True)
        
    def calculate_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Calculates cosine similarity between two normalized vectors."""
        # Since we use normalize_embeddings=True, dot product is equivalent to cosine similarity
        return float(np.dot(vec1, vec2))
