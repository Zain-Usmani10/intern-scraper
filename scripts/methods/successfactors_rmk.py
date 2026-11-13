"""SAP SuccessFactors Recruiting Marketing: pages through the jobs-search API."""

import re

from methods.common import Collector, job, normalize_url, pause, request_json, require


def fetch(params, settings):
    require(params, "site")
    site = params["site"].rstrip("/")
    found = Collector()
    total = None

    def read_result(result):
        posting = result["response"]
        places = [re.sub(r"<[^>]+>", "", place) for place in posting.get("jobLocationShort") or []]
        url = normalize_url(f"{site}/job/{posting['urlTitle']}/{posting['id']}-en_US")
        return url, job(posting["unifiedStandardTitle"], places)
    for page in range(settings["scraping"]["max_api_pages"]):
        data = request_json(f"{site}/services/recruiting/v1/jobs", settings, body={
            # Sorted by date, since relevance order shifts between pages.
            "locale": "en_US", "pageNumber": page, "sortBy": "date", "keywords": params.get("keywords", ""),
            "location": params.get("location", ""), "facetFilters": params.get("facet_filters") or {},
            "brand": "", "skills": [], "categoryId": 0, "alertId": "", "rcmCandidateId": "",
        })
        total = data["totalJobs"]
        results = data.get("jobSearchResult") or []
        for result in results:
            found.add(result, read_result)
        if len(found) >= total:
            return found.listing(total)
        if not results:
            raise RuntimeError(f"SuccessFactors stopped after {len(found)} of {total} jobs")
        pause(settings)
    raise RuntimeError("SuccessFactors returned more pages than max_api_pages allows")
