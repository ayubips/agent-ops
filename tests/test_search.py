from unittest.mock import patch, MagicMock
from src.tools import search


def test_search_run_parses_results():
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "results": [
            {"url": "https://a.com", "content": "snippet a"},
            {"url": "https://b.com", "content": "snippet b"},
        ]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("src.tools.search.requests.post", return_value=mock_response):
        result = search.run("test query")

    assert result["urls"] == ["https://a.com", "https://b.com"]
    assert result["snippets"] == ["snippet a", "snippet b"]


def test_search_run_handles_empty_results():
    mock_response = MagicMock()
    mock_response.json.return_value = {"results": []}
    mock_response.raise_for_status = MagicMock()

    with patch("src.tools.search.requests.post", return_value=mock_response):
        result = search.run("nonsense query")

    assert result["urls"] == []
    assert result["snippets"] == []