"""Greenhouse: reads every job from the public board API."""

from methods.common import Collector, job, normalize_url, request_json, require


def fetch(params, settings):
    require(params, "board")
    data = request_json(
        f"https://boards-api.greenhouse.io/v1/boards/{params['board']}/jobs", settings
    )
    found = Collector()
    for posting in data["jobs"]:
        found.add(posting, lambda p: (
            normalize_url(p["absolute_url"]),
            job(p["title"], [(p.get("location") or {}).get("name")]),
        ))
    return found.listing(data.get("meta", {}).get("total"))
