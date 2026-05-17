import pytest
from unittest.mock import MagicMock
from agent.transition_validator import TransitionValidator, TransitionSnapshot

def test_transition_snapshot_init():
    snap = TransitionSnapshot(
        url="https://example.com/page1",
        title="Page 1",
        active_element="INPUT#search",
        text_hash="abc",
        elements_hash="def",
        modal_state=False
    )
    assert snap.url == "https://example.com/page1"
    assert snap.title == "Page 1"
    assert snap.active_element == "INPUT#search"
    assert snap.text_hash == "abc"
    assert snap.elements_hash == "def"
    assert snap.modal_state is False

def test_take_snapshot_success():
    mock_page = MagicMock()
    mock_page.evaluate.return_value = {
        "url": "https://example.com/dashboard",
        "title": "Dashboard",
        "active_element": "BUTTON#submit",
        "visible_text": "Welcome User|Your Profile",
        "clickable_labels": "Logout|Settings",
        "modal_state": True
    }
    
    snap = TransitionValidator.take_snapshot(mock_page)
    assert snap.url == "https://example.com/dashboard"
    assert snap.title == "Dashboard"
    assert snap.active_element == "BUTTON#submit"
    assert len(snap.text_hash) == 32 # MD5 hash is 32 chars
    assert len(snap.elements_hash) == 32
    assert snap.modal_state is True

def test_take_snapshot_failure_fallback():
    mock_page = MagicMock()
    mock_page.evaluate.side_effect = Exception("Browser context lost")
    
    snap = TransitionValidator.take_snapshot(mock_page)
    assert snap.url == ""
    assert snap.title == ""
    assert snap.active_element == ""
    assert snap.text_hash == ""
    assert snap.elements_hash == ""
    assert snap.modal_state is False

def test_compute_transition_score_no_change():
    snap_before = TransitionSnapshot("https://example.com", "Title", "INPUT", "hash1", "hash2", False)
    snap_after = TransitionSnapshot("https://example.com", "Title", "INPUT", "hash1", "hash2", False)
    
    score, _ = TransitionValidator.compute_transition_score(snap_before, snap_after)
    assert score == 0.0

def test_compute_transition_score_url_change():
    snap_before = TransitionSnapshot("https://example.com", "Title", "INPUT", "hash1", "hash2", False)
    snap_after = TransitionSnapshot("https://example.com/new", "Title", "INPUT", "hash1", "hash2", False)
    
    score, _ = TransitionValidator.compute_transition_score(snap_before, snap_after)
    assert score == 0.8

def test_compute_transition_score_title_change():
    snap_before = TransitionSnapshot("https://example.com", "Title 1", "INPUT", "hash1", "hash2", False)
    snap_after = TransitionSnapshot("https://example.com", "Title 2", "INPUT", "hash1", "hash2", False)
    
    score, _ = TransitionValidator.compute_transition_score(snap_before, snap_after)
    assert score == 0.4

def test_compute_transition_score_text_change():
    snap_before = TransitionSnapshot("https://example.com", "Title", "INPUT", "hash1", "hash2", False)
    snap_after = TransitionSnapshot("https://example.com", "Title", "INPUT", "hash3", "hash2", False)
    
    score, _ = TransitionValidator.compute_transition_score(snap_before, snap_after)
    assert score == 0.3

def test_compute_transition_score_elements_change():
    snap_before = TransitionSnapshot("https://example.com", "Title", "INPUT", "hash1", "hash2", False)
    snap_after = TransitionSnapshot("https://example.com", "Title", "INPUT", "hash1", "hash4", False)
    
    score, _ = TransitionValidator.compute_transition_score(snap_before, snap_after)
    assert score == 0.3

def test_compute_transition_score_modal_change():
    snap_before = TransitionSnapshot("https://example.com", "Title", "INPUT", "hash1", "hash2", False)
    snap_after = TransitionSnapshot("https://example.com", "Title", "INPUT", "hash1", "hash2", True)
    
    score, _ = TransitionValidator.compute_transition_score(snap_before, snap_after)
    assert score == 0.4

def test_compute_transition_score_multiple_changes_capped():
    # URL change (0.8) + Title change (0.4) + text change (0.3) = 1.5, should be capped at 1.0
    snap_before = TransitionSnapshot("https://example.com", "Title 1", "INPUT", "hash1", "hash2", False)
    snap_after = TransitionSnapshot("https://example.com/new", "Title 2", "INPUT", "hash3", "hash2", False)
    
    score, _ = TransitionValidator.compute_transition_score(snap_before, snap_after)
    assert score == 1.0
