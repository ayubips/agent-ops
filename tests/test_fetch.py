from unittest.mock import patch, MagicMock
import requests
from src.tools import fetch


def test_fetch_one_success():
    mock_response = MagicMock()
    mock_response.headers = {"Content-Type": "text/html"}
    mock_response.text = "<html><body>" + ("word " * 50) + "</body></html>"
    mock_response.raise_for_status = MagicMock()

    with patch("src.tools.fetch.requests.get", return_value=mock_response):
        result = fetch.fetch_one("https://example.com")

    assert result["success"] is True
    assert result["text"] is not None
    assert "word" in result["text"]


def test_fetch_one_handles_timeout():
    with patch("src.tools.fetch.requests.get", side_effect=requests.Timeout()):
        result = fetch.fetch_one("https://example.com")

    assert result["success"] is False
    assert result["error"] == "timeout"


def test_fetch_one_handles_non_html():
    mock_response = MagicMock()
    mock_response.headers = {"Content-Type": "application/pdf"}
    mock_response.raise_for_status = MagicMock()

    with patch("src.tools.fetch.requests.get", return_value=mock_response):
        result = fetch.fetch_one("https://example.com/doc.pdf")

    assert result["success"] is False
    assert "non-HTML" in result["error"]


def test_fetch_one_handles_short_content():
    mock_response = MagicMock()
    mock_response.headers = {"Content-Type": "text/html"}
    mock_response.text = "<html><body>too short</body></html>"
    mock_response.raise_for_status = MagicMock()

    with patch("src.tools.fetch.requests.get", return_value=mock_response):
        result = fetch.fetch_one("https://example.com")

    assert result["success"] is False
    assert "too short" in result["error"]


def test_run_separates_successes_and_failures():
    def fake_fetch_one(url, timeout=8):
        if "good" in url:
            return {"url": url, "text": "a" * 300, "success": True, "error": None}
        return {"url": url, "text": None, "success": False, "error": "simulated failure"}

    with patch("src.tools.fetch.fetch_one", side_effect=fake_fetch_one):
        result = fetch.run(["https://good.com", "https://bad.com"])

    assert len(result["texts"]) == 1
    assert len(result["failed_urls"]) == 1