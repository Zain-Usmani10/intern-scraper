"""Lever: reads every job from the public postings API."""

from methods.common import job, listing, normalize_url, request_json, require


def fetch(params, settings):
    require(params, "site")
    host = "api.eu.lever.co" if params.get("region") == "eu" else "api.lever.co"
    postings = request_json(f"https://{host}/v0/postings/{params['site']}?mode=json", settings)
    jobs = {}
    for posting in postings:
        categories = posting.get("categories") or {}
        places = categories.get("allLocations") or [categories.get("location")]
        jobs[normalize_url(posting["hostedUrl"])] = job(
            posting["text"], [*places, posting.get("country")]
        )
    # The API returns the whole board at once, so there's no separate total.
    return listing(jobs)
