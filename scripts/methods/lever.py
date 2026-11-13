"""Lever: reads every job from the public postings API."""

from methods.common import Collector, job, normalize_url, request_json, require


def read_posting(posting):
    categories = posting.get("categories") or {}
    places = categories.get("allLocations") or [categories.get("location")]
    return normalize_url(posting["hostedUrl"]), job(posting["text"], [*places, posting.get("country")])


def fetch(params, settings):
    require(params, "site")
    host = "api.eu.lever.co" if params.get("region") == "eu" else "api.lever.co"
    postings = request_json(f"https://{host}/v0/postings/{params['site']}?mode=json", settings)
    found = Collector()
    for posting in postings:
        found.add(posting, read_posting)
    # The API returns the whole board at once, so there's no separate total.
    return found.listing()
