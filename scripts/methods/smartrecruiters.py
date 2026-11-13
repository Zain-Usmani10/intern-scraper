"""SmartRecruiters: pages through the public postings API."""

from methods.common import Collector, job, normalize_url, pause, request_json, require

PAGE_SIZE = 100  # The API's maximum.


def fetch(params, settings):
    require(params, "company")
    found = Collector()
    total = None

    def read_posting(posting):
        url = normalize_url(f"https://jobs.smartrecruiters.com/{params['company']}/{posting['id']}")
        return url, job(posting["name"], [(posting.get("location") or {}).get("fullLocation")])
    for _ in range(settings["scraping"]["max_api_pages"]):
        data = request_json(
            f"https://api.smartrecruiters.com/v1/companies/{params['company']}/postings"
            f"?limit={PAGE_SIZE}&offset={len(found)}", settings,
        )
        total = data["totalFound"]
        before = len(found)
        for posting in data.get("content") or []:
            found.add(posting, read_posting)
        if len(found) >= total:
            return found.listing(total)
        if len(found) == before:
            raise RuntimeError(f"SmartRecruiters stopped after {len(found)} of {total} jobs")
        pause(settings)
    raise RuntimeError("SmartRecruiters returned more pages than max_api_pages allows")
