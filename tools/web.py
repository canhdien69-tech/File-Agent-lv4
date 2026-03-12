# ==============================================================================
#  SUNNY AI v5.0 — tools/web.py
#  Web search + URL fetch.
# ==============================================================================
from core.sandbox import Sandbox

try:
    from ddgs import DDGS
    HAS_DDGS = True
except ImportError:
    HAS_DDGS = False

try:
    import requests
    from bs4 import BeautifulSoup
    HAS_WEB = True
except ImportError:
    HAS_WEB = False


def web_search(query: str) -> str:
    if not HAS_DDGS:
        return "[Missing]: duckduckgo-search not installed. Run: pip install duckduckgo-search"
    ok, reason = Sandbox.check_url("https://dummy")
    if not ok:
        return f"[Blocked]: {reason}"
    try:
        results = DDGS(timeout=5).text(query, max_results=3)
        if not results:
            return "[WEB]: No results found."
        out = "[WEB SEARCH]:\n"
        for i, x in enumerate(results, 1):
            out += f"{i}. {x['title']}\n   {x['body']}\n   {x['href']}\n"
        return out
    except Exception as e:
        return f"[WEB ERROR]: {e}"


def visit_url(url: str) -> str:
    ok, reason = Sandbox.check_url(url)
    if not ok:
        return f"[Blocked]: {reason}"
    if not HAS_WEB:
        return "[Missing]: requests/beautifulsoup4 not installed."
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        s = BeautifulSoup(r.text, "html.parser")
        for tag in s(["script", "style", "nav", "footer"]):
            tag.extract()
        return f"[URL: {url}]:\n{s.get_text()[:5000]}"
    except Exception as e:
        return f"[URL ERROR]: {e}"
