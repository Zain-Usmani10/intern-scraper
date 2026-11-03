"""Amazon Jobs: pages through amazon.jobs search results, 100 at a time."""

import urllib.parse

from methods.common import job, listing, normalize_url, pause, request_json, require

PAGE_SIZE = 100


def fetch(params, settings):
    require(params, "query")
    jobs = {}
    hits = None
    offset = 0

    for _ in range(settings["scraping"]["max_api_pages"]):
        query = urllib.parse.urlencode({
            "base_query": params["query"],
            "sort": "recent",
            "result_limit": PAGE_SIZE,
            "offset": offset,
            **(params.get("extra_query") or {}),
        })
        data = request_json(f"https://www.amazon.jobs/en/search.json?{query}", settings)
        hits = data["hits"]
        postings = data.get("jobs") or []
        for posting in postings:
            url = normalize_url(f"https://www.amazon.jobs{posting['job_path']}")
            jobs[url] = job(
                posting["title"],
                [posting.get("normalized_location") or posting.get("location"),
                 posting.get("country_code")],
            )

        offset += len(postings)
        if not postings or offset >= hits:
            return listing(jobs, hits)
        pause(settings)

    raise RuntimeError("Amazon returned more pages than max_api_pages allows")
