"""Rippling: pages through the public job board API at ats.rippling.com."""

from methods.common import job, listing, normalize_url, pause, request_json, require

PAGE_SIZE = 50


def fetch(params, settings):
    require(params, "board")
    jobs = {}
    read = 0
    for page in range(settings["scraping"]["max_api_pages"]):
        data = request_json(
            f"https://ats.rippling.com/api/v2/board/{params['board']}/jobs"
            f"?page={page}&pageSize={PAGE_SIZE}", settings,
        )
        total = data["totalItems"]
        for posting in data.get("items") or []:
            places = [
                ", ".join(part for part in (place.get("city"), place.get("state"), place.get("country")) if part)
                or place.get("name")
                for place in posting.get("locations") or []
            ]
            # A job in two locations is listed twice, once per location.
            url = normalize_url(posting["url"])
            if url in jobs:
                jobs[url]["locations"] += job(posting["name"], places)["locations"]
            else:
                jobs[url] = job(posting["name"], places)
        read += len(data.get("items") or [])
        if page + 1 >= data.get("totalPages", 0):
            if read < total:
                raise RuntimeError(f"Rippling stopped after {read} of {total} listings")
            # Every listing was read, so the unique jobs are complete.
            return listing(jobs, len(jobs))
        pause(settings)
    raise RuntimeError("Rippling returned more pages than max_api_pages allows")
