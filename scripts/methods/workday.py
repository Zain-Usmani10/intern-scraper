"""Workday: pages through a career site's search API, 20 jobs at a time."""

from methods.common import job, listing, normalize_url, pause, request_json, require

PAGE_SIZE = 20  # Workday's maximum.


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
            jobs[url] = job(posting["title"], [posting.get("locationsText")])

        offset += len(postings)
        if not postings or (total is not None and offset >= total):
            return listing(jobs, total)
        pause(settings)

    raise RuntimeError("Workday returned more pages than max_api_pages allows")
