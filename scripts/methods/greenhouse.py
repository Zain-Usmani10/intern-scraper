"""Greenhouse: reads every job from the public board API."""

from methods.common import job, listing, normalize_url, request_json, require


def fetch(params, settings):
    require(params, "board")
    data = request_json(
        f"https://boards-api.greenhouse.io/v1/boards/{params['board']}/jobs", settings
    )
    jobs = {
        normalize_url(posting["absolute_url"]): job(
            posting["title"], [(posting.get("location") or {}).get("name")]
        )
        for posting in data["jobs"]
    }
    return listing(jobs, data.get("meta", {}).get("total"))
