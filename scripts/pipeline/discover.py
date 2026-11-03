"""Step 1: Claude turns your text into company names and careers URLs."""

import urllib.parse

from pipeline import claude, handoff


def discover(text, settings):
    """Return [{"name", "careers_url", "notes"}] from data/tmp/discovery.json."""
    handoff.reset("discover_companies", input_text=text)
    timeout = settings["claude"]["discovery_timeout_minutes"] * 60
    claude.run("discover_companies", {"input_text": text}, timeout, settings)

    companies = []
    for entry in handoff.read("discover_companies").get("companies", []):
        name = (entry.get("name") or "").strip()
        url = (entry.get("careers_url") or "").strip()
        if not name:
            continue
        if urllib.parse.urlsplit(url).scheme not in ("http", "https"):
            url = ""
        companies.append({"name": name, "careers_url": url, "notes": entry.get("notes", "")})
    return companies
