# src/tools/fetch.py
import requests
from bs4 import BeautifulSoup

def fetch_one(url: str, timeout: int = 8) -> dict:
    """
    Fetches and strips a single URL to plain text.
    Returns {'url': ..., 'text': ..., 'success': bool, 'error': str|None}
    Deliberately catches errors HERE (not raised) since fetch failures
    for individual sources are expected/partial — the reliability layer
    will decide whether partial results are acceptable later.
    """
    try:
        headers = {"User-Agent": "Mozilla/5.0 (agent-ops research bot)"}
        response = requests.get(url, timeout=timeout, headers=headers)
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "")
        if "text/html" not in content_type:
            return {"url": url, "text": None, "success": False,
                     "error": f"non-HTML content-type: {content_type}"}

        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        text = " ".join(soup.get_text(separator=" ").split())
        if len(text) < 100:
            return {"url": url, "text": None, "success": False,
                     "error": "extracted text too short, likely blocked/empty"}

        return {"url": url, "text": text[:5000], "success": True, "error": None}

    except requests.Timeout:
        return {"url": url, "text": None, "success": False, "error": "timeout"}
    except requests.HTTPError as e:
        return {"url": url, "text": None, "success": False, "error": f"http error: {e}"}
    except requests.RequestException as e:
        return {"url": url, "text": None, "success": False, "error": f"request failed: {e}"}


def run(urls: list[str]) -> dict:
    """Fetches multiple URLs, returns successes and failures separately."""
    results = [fetch_one(url) for url in urls]
    texts = [r["text"] for r in results if r["success"]]
    failed = [{"url": r["url"], "error": r["error"]} for r in results if not r["success"]]
    return {"texts": texts, "failed_urls": failed}


if __name__ == "__main__":
    # standalone test — use 2 real URLs + 1 deliberately bad one
    test_urls = [
        "https://en.wikipedia.org/wiki/Multi-agent_system",
        "https://en.wikipedia.org/wiki/Circuit_breaker_design_pattern",
        "https://this-domain-does-not-exist-xyz123.com",
    ]
    result = run(test_urls)
    print(f"Fetched {len(result['texts'])} successfully, {len(result['failed_urls'])} failed\n")
    for text in result["texts"]:
        print(text[:150], "...\n")
    for f in result["failed_urls"]:
        print(f"FAILED: {f['url']} — {f['error']}")