import pytest
from unittest.mock import MagicMock
from automation.js_bridge import safe_evaluate

def test_safe_evaluate_success():
    mock_page = MagicMock()
    mock_page.evaluate.return_value = "hello_world"
    
    script = "() => 'hello_world'"
    payload = {"a": 1, "b": "test"}
    
    result = safe_evaluate(mock_page, script, payload)
    
    assert result == "hello_world"
    mock_page.evaluate.assert_called_once_with(script, payload)

def test_safe_evaluate_no_payload():
    mock_page = MagicMock()
    mock_page.evaluate.return_value = 42
    
    script = "() => 42"
    result = safe_evaluate(mock_page, script)
    
    assert result == 42
    mock_page.evaluate.assert_called_once_with(script, {})

def test_safe_evaluate_serialization_error():
    mock_page = MagicMock()
    
    # Passing an object that cannot be serialized to JSON (like a class instance or set)
    bad_payload = {"unserializable": {1, 2, 3}}
    
    with pytest.raises(ValueError) as excinfo:
        safe_evaluate(mock_page, "() => {}", bad_payload)
        
    assert "Payload not JSON serializable" in str(excinfo.value)
    mock_page.evaluate.assert_not_called()

def test_safe_evaluate_transport_failure():
    mock_page = MagicMock()
    mock_page.evaluate.side_effect = RuntimeError("Playwright transport channel closed")
    
    with pytest.raises(RuntimeError) as excinfo:
        safe_evaluate(mock_page, "() => {}", {"a": 1})
        
    assert "Playwright transport channel closed" in str(excinfo.value)
