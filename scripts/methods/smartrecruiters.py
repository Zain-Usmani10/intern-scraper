"""SmartRecruiters: pages through the public postings API."""

from methods.common import job, listing, normalize_url, pause, request_json, require

PAGE_SIZE = 100  # The API's maximum.


def fetch(params, settings):
    require(params, "company")
    jobs = {}
    total = None
    for _ in range(settings["scraping"]["max_api_pages"]):
        data = request_json(
            f"https://api.smartrecruiters.com/v1/companies/{params['company']}/postings"
            f"?limit={PAGE_SIZE}&offset={len(jobs)}", settings,
        )
        total = data["totalFound"]
        before = len(jobs)
        for posting in data.get("content") or []:
            jobs[normalize_url(f"https://jobs.smartrecruiters.com/{params['company']}/{posting['id']}")] = job(
                posting["name"], [(posting.get("location") or {}).get("fullLocation")]
            )
        if len(jobs) >= total:
            return listing(jobs, total)
        if len(jobs) == before:
            raise RuntimeError(f"SmartRecruiters stopped after {len(jobs)} of {total} jobs")
        pause(settings)
    raise RuntimeError("SmartRecruiters returned more pages than max_api_pages allows")
