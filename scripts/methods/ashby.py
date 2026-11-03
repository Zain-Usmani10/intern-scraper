"""Ashby: reads every listed job from the public job board API."""

from methods.common import job, listing, normalize_url, request_json, require


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
    jobs = {
        normalize_url(posting["jobUrl"]): job(posting["title"], locations(posting))
        for posting in data["jobs"]
        if posting.get("isListed", True)
    }
    # The API returns the whole board at once, so there's no separate total.
    return listing(jobs)
