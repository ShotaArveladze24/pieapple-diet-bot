"""Fetches a web page and extracts its plain text content, for recipe URL imports."""

import requests
from bs4 import BeautifulSoup

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; PieappleDietBot/1.0)"}
_MAX_CHARS = 15000


def fetch_url_text(url: str) -> str:
    response = requests.get(url, headers=_HEADERS, timeout=15)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    text = soup.get_text(separator="\n", strip=True)
    return text[:_MAX_CHARS]
