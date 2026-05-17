import pytest
from unittest.mock import MagicMock
from automation.ui_state_engine import UIStateEngine, UIState

def test_uistate_to_dict():
    state = UIState(
        overlay_open=True,
        modal_visible=True,
        active_element_type="INPUT",
        pointer_blocked=True,
        visible_inputs=["Search"],
        clickable_regions=["Click me"],
        blocker_selector=".modal"
    )
    d = state.to_dict()
    assert d["overlay_open"] is True
    assert d["modal_visible"] is True
    assert d["active_element_type"] == "INPUT"
    assert d["pointer_blocked"] is True
    assert d["visible_inputs"] == ["Search"]
    assert d["clickable_regions"] == ["Click me"]
    assert d["blocker_selector"] == ".modal"

def test_inspect_page_success():
    mock_page = MagicMock()
    mock_page.evaluate.return_value = {
        "overlay_open": True,
        "modal_visible": True,
        "pointer_blocked": True,
        "active_element_type": "INPUT",
        "visible_inputs": ["Query"],
        "clickable_regions": ["Search"],
        "blocker_selector": ".popup-overlay"
    }
    
    state = UIStateEngine.inspect_page(mock_page)
    assert state.overlay_open is True
    assert state.modal_visible is True
    assert state.pointer_blocked is True
    assert state.active_element_type == "INPUT"
    assert state.visible_inputs == ["Query"]
    assert state.clickable_regions == ["Search"]
    assert state.blocker_selector == ".popup-overlay"
    mock_page.evaluate.assert_called_once()

def test_inspect_page_failure_fallback():
    mock_page = MagicMock()
    mock_page.evaluate.side_effect = Exception("Browser not responding")
    
    state = UIStateEngine.inspect_page(mock_page)
    assert state.overlay_open is False
    assert state.modal_visible is False
    assert state.pointer_blocked is False
    assert state.active_element_type == "UNKNOWN"
    assert state.visible_inputs == []
    assert state.clickable_regions == []

def test_detect_overlay():
    mock_page = MagicMock()
    mock_page.evaluate.return_value = {
        "overlay_open": True,
        "modal_visible": False,
        "pointer_blocked": False,
        "active_element_type": "BODY",
        "visible_inputs": [],
        "clickable_regions": [],
        "blocker_selector": ""
    }
    assert UIStateEngine.detect_overlay(mock_page) is True

def test_dismiss_overlay_escape_key():
    mock_page = MagicMock()
    # First inspect: returns overlay open
    # Second inspect (after Escape key): returns overlay closed
    mock_page.evaluate.side_effect = [
        # First call inside dismiss_overlay (detect_overlay)
        {
            "overlay_open": True,
            "modal_visible": True,
            "pointer_blocked": True,
            "active_element_type": "BODY",
            "visible_inputs": [],
            "clickable_regions": [],
            "blocker_selector": ".scrim"
        },
        # Second call inside dismiss_overlay (detect_overlay post-escape)
        {
            "overlay_open": False,
            "modal_visible": False,
            "pointer_blocked": False,
            "active_element_type": "BODY",
            "visible_inputs": [],
            "clickable_regions": [],
            "blocker_selector": ""
        }
    ]
    
    res = UIStateEngine.dismiss_overlay(mock_page)
    assert res is True
    mock_page.keyboard.press.assert_called_once_with("Escape")

def test_validate_interaction_safe():
    mock_page = MagicMock()
    mock_locator = MagicMock()
    mock_page.locator.return_value.first = mock_locator
    
    # Element visible and enabled
    mock_locator.is_visible.return_value = True
    mock_locator.is_enabled.return_value = True
    
    # Page has no pointer blockages
    mock_page.evaluate.return_value = {
        "overlay_open": False,
        "modal_visible": False,
        "pointer_blocked": False,
        "active_element_type": "BODY",
        "visible_inputs": [],
        "clickable_regions": [],
        "blocker_selector": ""
    }
    
    assert UIStateEngine.validate_interaction_safe(mock_page, "#my-button") is True
