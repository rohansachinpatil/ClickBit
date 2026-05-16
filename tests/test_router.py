import pytest
from unittest.mock import MagicMock
from agent.router import Router

def test_local_routing_simple(mock_ollama):
    router = Router()
    
    # Should route simple commands locally
    decision = router.get_routing_decision("open calculator")
    assert decision == "local"
    
    # Try fetching a local plan
    plan = router.get_local_plan("open calculator", "system prompt")
    
    # Mock returns "browser|open_url:https://google.com"
    assert plan is not None
    assert plan["action"] == "browser"
    assert len(plan["steps"]) == 1
    assert plan["steps"][0]["command"] == "open_url"

def test_cloud_fallback(mock_ollama):
    router = Router()
    
    # Simulate timeout / connection error from Ollama
    mock_ollama.side_effect = Exception("Connection Timeout")
    
    plan = router.get_local_plan("open youtube", "system prompt")
    
    # Should gracefully fail and return None, prompting the executor to use Cloud Mistral
    assert plan is None

def test_cloud_routing_complex():
    router = Router()
    
    # Complex/vague queries with complexity markers should route to Mistral
    decision = router.get_routing_decision("analyze the top 5 AI models and decide which is best")
    assert decision == "cloud"
