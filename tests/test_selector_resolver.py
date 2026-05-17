import pytest
import os
import shutil
from unittest.mock import MagicMock, patch
from automation.selector_resolver import SelectorResolver, CandidateElement

@pytest.fixture
def temp_db():
    db_path = "tmp/test_selector_memory.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    resolver = SelectorResolver(db_path=db_path)
    yield resolver
    # Cleanup after test
    if os.path.exists("tmp"):
        try:
            shutil.rmtree("tmp/test_selector_memory.db", ignore_errors=True)
            if os.path.exists(db_path):
                os.remove(db_path)
        except:
            pass

def test_semantic_similarity_scoring():
    resolver = SelectorResolver(db_path="tmp/test_similarity.db")
    
    # Exact match
    score1 = resolver._calculate_similarity("Login", "Login")
    assert score1 == 1.0

    # Substring match
    score2 = resolver._calculate_similarity("Login", "Submit Login Form")
    assert score2 == 0.85

    # Case insensitive exact match
    score3 = resolver._calculate_similarity("login", "LOGIN")
    assert score3 == 1.0

    # Fuzzy match
    score4 = resolver._calculate_similarity("Login", "Logon")
    assert score4 > 0.5 and score4 < 1.0

    # No match
    score5 = resolver._calculate_similarity("Login", "Cancel")
    assert score5 < 0.2

def test_visibility_ranking():
    resolver = SelectorResolver(db_path="tmp/test_visibility.db")
    
    mock_page = MagicMock()
    mock_page.url = "http://google.com"
    
    # Mock gather_candidates return values
    candidates = [
        CandidateElement(
            index=0, tag_name="button", element_type="submit", text="Search",
            placeholder="", aria_label="", name="", element_id="", class_name="",
            role="button", is_visible=False, rect={"x": 0, "y": 0, "width": 0, "height": 0},
            css_selector="button#invisible"
        ),
        CandidateElement(
            index=1, tag_name="button", element_type="submit", text="Search",
            placeholder="", aria_label="", name="", element_id="", class_name="",
            role="button", is_visible=True, rect={"x": 100, "y": 100, "width": 80, "height": 30},
            css_selector="button#visible"
        )
    ]
    
    with patch.object(resolver, "gather_candidates", return_value=candidates):
        cand, conf, reason = resolver.resolve_best_candidate(mock_page, "Search", "click")
        assert cand is not None
        assert cand.css_selector == "button#visible"
        assert cand.confidence > 0.7

def test_fuzzy_button_matching():
    resolver = SelectorResolver(db_path="tmp/test_fuzzy.db")
    mock_page = MagicMock()
    mock_page.url = "http://google.com"

    candidates = [
        CandidateElement(
            index=0, tag_name="button", element_type="button", text="Send Query",
            placeholder="", aria_label="", name="", element_id="", class_name="",
            role="button", is_visible=True, rect={"x": 50, "y": 50, "width": 100, "height": 40},
            css_selector="button#send"
        ),
        CandidateElement(
            index=1, tag_name="button", element_type="button", text="Cancel",
            placeholder="", aria_label="", name="", element_id="", class_name="",
            role="button", is_visible=True, rect={"x": 200, "y": 50, "width": 100, "height": 40},
            css_selector="button#cancel"
        )
    ]

    with patch.object(resolver, "gather_candidates", return_value=candidates):
        cand, conf, reason = resolver.resolve_best_candidate(mock_page, "submit", "click")
        assert cand is not None
        assert cand.css_selector == "button#send" # "submit" is semantically closer to "Send Query" than "Cancel"

def test_sqlite_memory_caching_and_decay(temp_db):
    resolver = temp_db
    domain = "example.com"
    query = "search_box"
    selector = "input#search"
    
    # Verify initially no memory boosts exist
    boosts = resolver._get_memory_boosts(domain, query)
    assert selector not in boosts
    
    # Store success in memory
    resolver.remember_success(domain, query, selector, "css", 0.8)
    
    # Verify memory contains stored selector with confidence boost
    boosts2 = resolver._get_memory_boosts(domain, query)
    assert selector in boosts2
    assert boosts2[selector] > 0.15
    
    # Decay selector
    resolver.decay_selector(domain, query, selector)
    boosts3 = resolver._get_memory_boosts(domain, query)
    # Since confidence decremented by 0.15 but count is 1 (new count = 0),
    # count == 0 and conf <= 0.1 is false (confidence was 0.8 -> 0.65).
    # So it stays but with lower boost
    assert selector in boosts3
    
    # Decay again to trigger purge
    resolver.decay_selector(domain, query, selector)
    resolver.decay_selector(domain, query, selector)
    resolver.decay_selector(domain, query, selector)
    resolver.decay_selector(domain, query, selector)
    resolver.decay_selector(domain, query, selector)
    boosts4 = resolver._get_memory_boosts(domain, query)
    assert selector not in boosts4 # Decayed to zero and purged!

def test_selector_fallback_recovery():
    resolver = SelectorResolver(db_path="tmp/test_fallback.db")
    mock_page = MagicMock()
    mock_page.url = "http://google.com"

    # Primary candidate
    primary = CandidateElement(
        index=0, tag_name="button", element_type="button", text="Search",
        placeholder="", aria_label="", name="", element_id="", class_name="",
        role="button", is_visible=True, rect={"x": 50, "y": 50, "width": 100, "height": 40},
        css_selector="button#broken"
    )

    # 1. Simulating failure on primary, then fallback succeeds on Playwright native text search
    with patch.object(resolver, "_perform_action") as mock_perform:
        # First call (primary selector button#broken) raises error
        mock_perform.side_effect = Exception("Element not clickable")
        
        # Playwright native text locator succeeds
        mock_locator = MagicMock()
        mock_first = MagicMock()
        mock_first.count.return_value = 1
        mock_first.is_visible.return_value = True
        mock_locator.first = mock_first
        mock_page.get_by_text.return_value = mock_locator
        
        success, sel, msg = resolver.execute_fallback_chain(mock_page, primary, "Search", "click")
        
        assert success
        assert sel == "get_by_text(Search)"
        assert mock_perform.called
        assert mock_page.get_by_text.called

def test_execute_fallback_chain_missing_action_type():
    resolver = SelectorResolver(db_path="tmp/test_fallback_error.db")
    mock_page = MagicMock()
    mock_page.url = "http://google.com"
    primary = CandidateElement(
        index=0, tag_name="button", element_type="button", text="Search",
        placeholder="", aria_label="", name="", element_id="", class_name="",
        role="button", is_visible=True, rect={"x": 50, "y": 50, "width": 100, "height": 40},
        css_selector="button#broken"
    )
    from automation.selector_resolver import ResolverExecutionError
    with pytest.raises(ResolverExecutionError) as exc_info:
        resolver.execute_fallback_chain(mock_page, primary, "Search")
    assert "action_type is missing or empty" in str(exc_info.value)
