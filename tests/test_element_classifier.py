import pytest
from unittest.mock import MagicMock
from automation.element_classifier import ElementClassifier, ElementType

def test_classify_searchbox():
    mock_locator = MagicMock()
    # Case 1: role="searchbox"
    mock_locator.evaluate.return_value = {
        "tagName": "INPUT",
        "type": "",
        "role": "SEARCHBOX",
        "contentEditable": False,
        "placeholder": ""
    }
    assert ElementClassifier.classify(mock_locator) == ElementType.SEARCHBOX
    assert ElementClassifier.is_input(mock_locator) is True
    assert ElementClassifier.supports_typing(mock_locator) is True

    # Case 2: type="search"
    mock_locator.evaluate.return_value = {
        "tagName": "INPUT",
        "type": "SEARCH",
        "role": "",
        "contentEditable": False,
        "placeholder": ""
    }
    assert ElementClassifier.classify(mock_locator) == ElementType.SEARCHBOX

    # Case 3: placeholder has "search"
    mock_locator.evaluate.return_value = {
        "tagName": "INPUT",
        "type": "TEXT",
        "role": "",
        "contentEditable": False,
        "placeholder": "Search site..."
    }
    assert ElementClassifier.classify(mock_locator) == ElementType.SEARCHBOX

def test_classify_input():
    mock_locator = MagicMock()
    # Case 1: tag=TEXTAREA
    mock_locator.evaluate.return_value = {
        "tagName": "TEXTAREA",
        "type": "",
        "role": "",
        "contentEditable": False,
        "placeholder": ""
    }
    assert ElementClassifier.classify(mock_locator) == ElementType.INPUT
    assert ElementClassifier.supports_typing(mock_locator) is True

    # Case 2: contentEditable=True
    mock_locator.evaluate.return_value = {
        "tagName": "DIV",
        "type": "",
        "role": "",
        "contentEditable": True,
        "placeholder": ""
    }
    assert ElementClassifier.classify(mock_locator) == ElementType.INPUT

def test_classify_button():
    mock_locator = MagicMock()
    # Case 1: tag=BUTTON
    mock_locator.evaluate.return_value = {
        "tagName": "BUTTON",
        "type": "",
        "role": "",
        "contentEditable": False,
        "placeholder": ""
    }
    assert ElementClassifier.classify(mock_locator) == ElementType.BUTTON
    assert ElementClassifier.is_clickable(mock_locator) is True

    # Case 2: role=BUTTON
    mock_locator.evaluate.return_value = {
        "tagName": "DIV",
        "type": "",
        "role": "BUTTON",
        "contentEditable": False,
        "placeholder": ""
    }
    assert ElementClassifier.classify(mock_locator) == ElementType.BUTTON

def test_classify_link():
    mock_locator = MagicMock()
    mock_locator.evaluate.return_value = {
        "tagName": "A",
        "type": "",
        "role": "",
        "contentEditable": False,
        "placeholder": ""
    }
    assert ElementClassifier.classify(mock_locator) == ElementType.LINK
    assert ElementClassifier.is_clickable(mock_locator) is True

def test_classify_menu():
    mock_locator = MagicMock()
    mock_locator.evaluate.return_value = {
        "tagName": "SELECT",
        "type": "",
        "role": "LISTBOX",
        "contentEditable": False,
        "placeholder": ""
    }
    assert ElementClassifier.classify(mock_locator) == ElementType.MENU
    assert ElementClassifier.is_clickable(mock_locator) is True

def test_classify_exception_fallback():
    mock_locator = MagicMock()
    mock_locator.evaluate.side_effect = Exception("Evaluation failed")
    assert ElementClassifier.classify(mock_locator) == ElementType.UNKNOWN
