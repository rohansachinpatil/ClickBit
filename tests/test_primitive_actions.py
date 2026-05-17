import pytest
from unittest.mock import MagicMock, patch
from automation.primitive_actions import PrimitiveActions
from agent.primitive_router import PrimitiveRouter

def test_primitive_router_is_primitive():
    assert PrimitiveRouter.is_primitive("youtube_search") is True
    assert PrimitiveRouter.is_primitive("google_search") is True
    assert PrimitiveRouter.is_primitive("play_first_video") is True
    assert PrimitiveRouter.is_primitive("dismiss_overlay") is True
    assert PrimitiveRouter.is_primitive("close_modal") is True
    assert PrimitiveRouter.is_primitive("other_action") is False
    assert PrimitiveRouter.is_primitive("") is False
    assert PrimitiveRouter.is_primitive(None) is False

@patch('automation.primitive_actions.TransitionValidator.take_snapshot')
@patch('automation.primitive_actions.TransitionValidator.compute_transition_score')
def test_youtube_search_success(mock_compute_score, mock_take_snapshot):
    mock_page = MagicMock()
    mock_page.url = "https://youtube.com/results?search_query=cat"
    
    mock_locator = MagicMock()
    mock_locator.count.return_value = 1
    mock_locator.is_visible.return_value = True
    mock_page.locator.return_value.first = mock_locator
    
    mock_take_snapshot.return_value = MagicMock()
    mock_compute_score.return_value = 0.5
    
    res = PrimitiveActions.youtube_search(mock_page, "cats")
    
    assert res["success"] is True
    assert res["primitive"] == "youtube_search"
    assert res["transition_score"] == 0.5
    mock_page.goto.assert_not_called() # because url has 'youtube.com' in it
    mock_locator.type.assert_called_once_with("cats")
    mock_locator.press.assert_called_once_with("Enter")

@patch('automation.primitive_actions.TransitionValidator.take_snapshot')
@patch('automation.primitive_actions.TransitionValidator.compute_transition_score')
def test_youtube_search_goto_trigger(mock_compute_score, mock_take_snapshot):
    mock_page = MagicMock()
    mock_page.url = "https://google.com"
    
    mock_locator = MagicMock()
    mock_locator.count.return_value = 1
    mock_locator.is_visible.return_value = True
    mock_page.locator.return_value.first = mock_locator
    
    mock_take_snapshot.return_value = MagicMock()
    mock_compute_score.return_value = 0.6
    
    res = PrimitiveActions.youtube_search(mock_page, "music")
    
    assert res["success"] is True
    mock_page.goto.assert_called_once_with("https://youtube.com", timeout=12000, wait_until="load")

@patch('automation.primitive_actions.TransitionValidator.take_snapshot')
@patch('automation.primitive_actions.TransitionValidator.compute_transition_score')
def test_play_first_video_success(mock_compute_score, mock_take_snapshot):
    mock_page = MagicMock()
    mock_page.url = "https://youtube.com/watch?v=123"
    
    mock_locator = MagicMock()
    mock_locator.count.return_value = 1
    mock_locator.is_visible.return_value = True
    mock_page.locator.return_value.first = mock_locator
    
    mock_take_snapshot.return_value = MagicMock()
    mock_compute_score.return_value = 0.8
    
    res = PrimitiveActions.play_first_video(mock_page)
    
    assert res["success"] is True
    assert res["primitive"] == "play_first_video"
    mock_locator.click.assert_called_once_with(timeout=5000)

@patch('automation.primitive_actions.TransitionValidator.take_snapshot')
@patch('automation.primitive_actions.TransitionValidator.compute_transition_score')
def test_google_search_success(mock_compute_score, mock_take_snapshot):
    mock_page = MagicMock()
    mock_page.url = "https://google.com/search?q=weather"
    
    mock_locator = MagicMock()
    mock_locator.count.return_value = 1
    mock_locator.is_visible.return_value = True
    mock_page.locator.return_value.first = mock_locator
    
    mock_take_snapshot.return_value = MagicMock()
    mock_compute_score.return_value = 0.5
    
    res = PrimitiveActions.google_search(mock_page, "weather")
    
    assert res["success"] is True
    assert res["primitive"] == "google_search"
    mock_locator.type.assert_called_once_with("weather")
    mock_locator.press.assert_called_once_with("Enter")

@patch('automation.primitive_actions.UIStateEngine.dismiss_overlay')
@patch('automation.primitive_actions.TransitionValidator.take_snapshot')
@patch('automation.primitive_actions.TransitionValidator.compute_transition_score')
def test_dismiss_overlay_success(mock_compute_score, mock_take_snapshot, mock_dismiss):
    mock_page = MagicMock()
    mock_dismiss.return_value = True
    mock_take_snapshot.return_value = MagicMock()
    mock_compute_score.return_value = 0.4
    
    res = PrimitiveActions.dismiss_overlay(mock_page)
    
    assert res["success"] is True
    assert res["primitive"] == "dismiss_overlay"
    assert res["transition_score"] == 0.4
    mock_dismiss.assert_called_once_with(mock_page)

@patch('agent.primitive_router.PrimitiveActions.youtube_search')
def test_primitive_router_execute(mock_youtube_search):
    mock_page = MagicMock()
    mock_youtube_search.return_value = {"success": True, "message": "Done"}
    
    res = PrimitiveRouter.execute(mock_page, "youtube_search", "cats")
    assert res["success"] is True
    mock_youtube_search.assert_called_once_with(mock_page, "cats")
