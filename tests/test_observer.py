import pytest
from unittest.mock import MagicMock, patch
from automation.observer import Observer, BrowserObservation

@pytest.fixture
def mock_page():
    page = MagicMock()
    page.evaluate.return_value = {
        "title": "Mock Title",
        "buttons": ["Click Me", "Submit"],
        "inputs": ["Username", "Password"],
        "links": ["Home", "About"],
        "text_blocks": ["Welcome to the mock page."]
    }
    return page

def test_dom_observation(mock_page):
    observer = Observer()
    obs = observer.get_page_state(mock_page)
    
    assert isinstance(obs, BrowserObservation)
    assert obs.title == "Mock Title"
    assert "Click Me" in obs.buttons
    assert "Username" in obs.inputs
    
    # Check schema conversion
    obs_dict = obs.to_dict()
    assert "title" in obs_dict
    assert "visible_text" in obs_dict
    assert obs_dict["title"] == "Mock Title"

def test_dom_observation_failure():
    observer = Observer()
    page = MagicMock()
    page.evaluate.side_effect = Exception("Browser crashed")
    
    obs = observer.get_page_state(page)
    
    # Should safely fallback
    assert obs.title == "Unknown"
    assert obs.buttons == []
    assert obs.inputs == []

def test_screenshot_pipeline(mock_page):
    observer = Observer()
    
    # Mock screenshot so we don't actually write to disk during testing if we don't want to
    # Or we can just let it try since tmp/ is ignored
    mock_page.screenshot.return_value = None
    
    path = observer.capture_screen(mock_page)
    
    assert "tmp" in path
    assert "last_state.png" in path
    mock_page.screenshot.assert_called_once()

@patch('automation.observer.os.path.exists')
@patch('PIL.Image.open')
@patch('pytesseract.image_to_string')
def test_ocr_fallback(mock_image_to_string, mock_image_open, mock_exists):
    observer = Observer()
    
    mock_exists.return_value = True
    mock_image_to_string.return_value = "Extracted OCR text"
    
    text = observer.ocr_fallback("fake/path.png")
    
    assert text == "Extracted OCR text"
    mock_image_to_string.assert_called_once()

def test_ocr_fallback_missing_file():
    observer = Observer()
    text = observer.ocr_fallback("non_existent.png")
    assert text == ""
