import pytest
from unittest.mock import patch, MagicMock

# We use the temp_memory_db fixture from conftest.py which gives an empty isolated sqlite database
def test_semantic_similarity(temp_memory_db):
    with patch('agent.semantic_memory.SemanticMemoryEngine.encode') as mock_encode:
        # Mock embeddings to be normalized vectors as standard python lists
        mock_encode.side_effect = lambda text: [1.0, 0.0] if "music" in text or "song" in text else [0.0, 1.0]
        
        # Save "play music"
        plan = {"action": "browser", "steps": [{"command": "open_url", "argument": "https://music.youtube.com"}]}
        temp_memory_db.save_workflow("play music", plan, success=True)
        
        # Test exact match still works
        exact_hit = temp_memory_db.get_cached_plan("play music")
        assert exact_hit is not None
        
        # Test semantic match works (cosine similarity = 1.0 based on our mock)
        semantic_hit = temp_memory_db.get_cached_plan("start some songs")
        assert semantic_hit is not None
        assert semantic_hit["steps"][0]["argument"] == "https://music.youtube.com"
        
        # Test miss
        miss = temp_memory_db.get_cached_plan("open calculator")
        assert miss is None
