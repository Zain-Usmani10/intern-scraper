"""Workday: pages through a career site's search API, 20 jobs at a time."""

import re

import filters
from methods.common import job, listing, normalize_url, pause, request_json, require

PAGE_SIZE = 20  # Workday's maximum.
SEVERAL_PLACES = re.compile(r"^\d+ Locations?$")


def search_url(params):
    return f"https://{params['host']}/wday/cxs/{params['tenant']}/{params['site']}/jobs"


def search(params, settings, offset):
    body = {
        "appliedFacets": params.get("applied_facets") or {},
        "limit": PAGE_SIZE,
        "offset": offset,
        "searchText": params.get("search_text", ""),
    }
    return request_json(search_url(params), settings, body=body)


def real_locations(params, settings, posting):
    """A job listed as "5 Locations" names its places only on its own page."""
    try:
        info = request_json(
            f"https://{params['host']}/wday/cxs/{params['tenant']}/{params['site']}{posting['externalPath']}",
            settings,
        )["jobPostingInfo"]
    except Exception:
        return [posting.get("locationsText")]  # Keep the job. Unknown places pass the filter.
    country = (info.get("country") or {}).get("descriptor")
    return [info.get("location"), *(info.get("additionalLocations") or []), country]


def fetch(params, settings):
    require(params, "host", "tenant", "site")
    jobs = {}
    total = None
    offset = 0

    for _ in range(settings["scraping"]["max_api_pages"]):
        data = search(params, settings, offset)
        if total is None:
            total = data.get("total")  # Only the first page reports it.
        postings = data.get("jobPostings") or []
        for posting in postings:
            url = normalize_url(
                f"https://{params['host']}/{params['site']}{posting['externalPath']}"
            )
            places = [posting.get("locationsText")]
            # Only internships are looked up, to keep the extra requests few.
            if SEVERAL_PLACES.match(places[0] or "") and filters.is_internship(posting["title"], url, settings):
                places = real_locations(params, settings, posting)
            jobs[url] = job(posting["title"], places)

        offset += len(postings)
        if not postings or (total is not None and offset >= total):
            return listing(jobs, total)
        pause(settings)

    raise RuntimeError("Workday returned more pages than max_api_pages allows")
