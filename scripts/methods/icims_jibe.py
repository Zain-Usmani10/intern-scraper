"""iCIMS Jibe: pages through SITE/api/jobs, 100 jobs at a time."""

import urllib.parse

from methods.common import Collector, job, normalize_url, pause, request_json, require

PAGE_SIZE = 100


def fetch(params, settings):
    require(params, "site", "jobs_path")
    site = params["site"].rstrip("/")
    jobs_path = "/" + params["jobs_path"].strip("/")
    found = Collector()
    total = None

    def read_posting(posting):
        details = posting["data"]
        slug = details.get("slug") or details["req_id"]
        url = normalize_url(details.get("canonical_url") or f"{site}{jobs_path}/{slug}")
        return url, job(details["title"], [details.get("location_name"), details.get("country")])

    for page in range(1, settings["scraping"]["max_api_pages"] + 1):
        query = urllib.parse.urlencode({
            "keywords": params.get("keywords", ""),
            "page": page,
            "limit": PAGE_SIZE,
            **(params.get("extra_query") or {}),
        })
        data = request_json(f"{site}/api/jobs?{query}", settings)
        total = data["totalCount"]
        postings = data.get("jobs") or []
        for posting in postings:
            found.add(posting, read_posting)

        if not postings or len(found) >= total:
            return found.listing(total)
        pause(settings)

    raise RuntimeError("iCIMS Jibe returned more pages than max_api_pages allows")
