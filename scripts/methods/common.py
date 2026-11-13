"""Helpers shared by the scraping methods.

Every method has a fetch(params, settings) function that returns:
    {"jobs": {url: {"title": str, "locations": [str]}}, "reported_total": int or None}

"jobs" holds every job the method read, before any filtering.
"reported_total" is the count the site itself reports, when it has one.

API methods also return "broken": one entry per posting that came back without
its title or link (a glitch on the site's side, e.g. while a job is being
edited or closed). Each entry is the posting's ID when it has one, else None.
Skipping these keeps one bad posting from failing the whole company.
"""

import json
import re
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


def request_text(url, settings, body=None, headers=None):
    """GET, or POST when body is given. Waits and retries on HTTP 429."""
    scraping = settings["scraping"]
    all_headers = {"User-Agent": USER_AGENT}
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
                return response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as error:
            if error.code != 429 or wait_seconds is None:
                raise
            time.sleep(wait_seconds)


def request_json(url, settings, body=None, headers=None):
    return json.loads(request_text(
        url, settings, body, {"Accept": "application/json", **(headers or {})}
    ))


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


def listing(jobs, reported_total=None, broken=None):
    return {"jobs": jobs, "reported_total": reported_total, "broken": broken or []}


# Field names job boards use for a posting's ID.
ID_KEYS = ("id", "Id", "jobId", "job_id", "req_id", "reqId", "requisitionId",
           "itemID", "positionId", "jobReqId")
# What a posting with a missing or empty field raises while being read.
BROKEN_ERRORS = (KeyError, TypeError, AttributeError, ValueError, IndexError)


def posting_id(posting):
    """The ID of a raw posting, or None if it has none we recognise."""
    if not isinstance(posting, dict):
        return None
    for part in (posting, posting.get("data"), posting.get("response")):
        if isinstance(part, dict):
            for key in ID_KEYS:
                value = part.get(key)
                if isinstance(value, (str, int)) and len(str(value)) >= 3:
                    return str(value)
    bullets = posting.get("bulletFields")  # Workday puts the requisition ID here.
    if isinstance(bullets, list) and bullets and isinstance(bullets[0], str) and len(bullets[0]) >= 3:
        return bullets[0]
    return None


def id_in_url(posting_id, url):
    """True if the ID appears in the URL as a whole token (R0343079 in ..._R0343079)."""
    return re.search(rf"(?<![A-Za-z0-9]){re.escape(posting_id)}(?![A-Za-z0-9])", url, re.IGNORECASE) is not None


class Collector:
    """Gathers jobs one posting at a time, setting broken postings aside."""

    def __init__(self):
        self.jobs = {}
        self.broken = []

    def add(self, posting, build, merge_locations=False):
        """build(posting) returns (url, job). A posting it can't read goes to .broken.

        merge_locations: a job listed once per location keeps every location.
        """
        try:
            url, item = build(posting)
        except BROKEN_ERRORS:
            self.broken.append(posting_id(posting))
            return
        if merge_locations and url in self.jobs:
            self.jobs[url]["locations"] += item["locations"]
        else:
            self.jobs[url] = item

    def __len__(self):
        """Postings read so far, broken ones included. Used for paging and totals."""
        return len(self.jobs) + len(self.broken)

    def listing(self, reported_total=None):
        return listing(self.jobs, reported_total, self.broken)
