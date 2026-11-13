"""Ashby: reads every listed job from the public job board API."""

from methods.common import Collector, job, normalize_url, request_json, require


def locations(posting):
    found = [posting.get("location")]
    for extra in posting.get("secondaryLocations") or []:
        found.append(extra.get("location") if isinstance(extra, dict) else extra)
    address = (posting.get("address") or {}).get("postalAddress") or {}
    found.append(address.get("addressCountry"))
    return found


def fetch(params, settings):
    require(params, "board")
    data = request_json(
        f"https://api.ashbyhq.com/posting-api/job-board/{params['board']}", settings
    )
    found = Collector()
    for posting in data["jobs"]:
        if posting.get("isListed", True):
            found.add(posting, lambda p: (normalize_url(p["jobUrl"]), job(p["title"], locations(p))))
    # The API returns the whole board at once, so there's no separate total.
    return found.listing()
