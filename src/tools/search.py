# src/tools/search.py
import os
import requests
from dotenv import load_dotenv

load_dotenv()

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
TAVILY_URL = "https://api.tavily.com/search"

def run(query: str, max_results: int = 4) -> dict:
    """
    Runs a web search via Tavily.
    Returns {'urls': [...], 'snippets': [...]}
    Raises requests.RequestException on network/API failure — let the
    caller (reliability layer) handle retries, don't swallow errors here.
    """
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "max_results": max_results,
        "search_depth": "basic",
    }
    response = requests.post(TAVILY_URL, json=payload, timeout=10)
    response.raise_for_status()
    data = response.json()

    results = data.get("results", [])
    return {
        "urls": [r["url"] for r in results],
        "snippets": [r.get("content", "") for r in results],
    }


if __name__ == "__main__":
    # standalone test
    result = run("latest developments in AI agent orchestration")
    print(f"Found {len(result['urls'])} results:\n")
    for url, snippet in zip(result["urls"], result["snippets"]):
        print(f"- {url}")
        print(f"  {snippet[:120]}...\n")