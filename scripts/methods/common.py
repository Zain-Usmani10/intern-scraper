"""Helpers shared by the scraping methods.

Every method has a fetch(params, settings) function that returns:
    {"jobs": {url: {"title": str, "locations": [str]}}, "reported_total": int or None}

"jobs" holds every job the method read, before any filtering.
"reported_total" is the count the site itself reports, when it has one.
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

TRACKING_PARAMS = {
    "ref", "referer", "referrer", "source", "src", "gh_src", "lever-source",
    "lever-origin", "fbclid", "gclid", "mc_cid", "mc_eid", "trk", "_ga",
}


def require(params, *names):
    missing = [name for name in names if not params.get(name)]
    if missing:
        raise ValueError(f"missing params: {', '.join(missing)}")


def request_json(url, settings, body=None, headers=None):
    """GET, or POST when body is given. Waits and retries on HTTP 429."""
    scraping = settings["scraping"]
    all_headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        all_headers["Content-Type"] = "application/json"
    all_headers.update(headers or {})
    request = urllib.request.Request(url, data=data, headers=all_headers)

    for wait_seconds in (*scraping["rate_limit_waits_seconds"], None):
        try:
            with urllib.request.urlopen(
                request, timeout=scraping["request_timeout_seconds"]
            ) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code != 429 or wait_seconds is None:
                raise
            time.sleep(wait_seconds)


def pause(settings):
    time.sleep(settings["scraping"]["api_page_delay_seconds"])


def normalize_url(url):
    """Remove the parts of a URL that can change while the job stays the same."""
    parts = urllib.parse.urlsplit(url.strip())
    query = sorted(
        (key, value)
        for key, value in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in TRACKING_PARAMS and not key.lower().startswith("utm_")
    )
    return urllib.parse.urlunsplit((
        parts.scheme.lower(),
        parts.netloc.lower(),
        parts.path.rstrip("/"),
        urllib.parse.urlencode(query),
        "",
    ))


def clean_title(text):
    lines = [" ".join(line.split()) for line in (text or "").splitlines()]
    return next((line for line in lines if line), "")


def job(title, locations=()):
    return {
        "title": clean_title(title) or "New posting",
        "locations": [clean_title(location) for location in locations if location],
    }


def listing(jobs, reported_total=None):
    return {"jobs": jobs, "reported_total": reported_total}
