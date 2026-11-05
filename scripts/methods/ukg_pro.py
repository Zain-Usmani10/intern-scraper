"""UKG Pro (UltiPro) Recruiting: pages through the job board's search API."""

from methods.common import job, listing, normalize_url, pause, request_json, require

PAGE_SIZE = 50


def fetch(params, settings):
    require(params, "host", "tenant", "board_id")
    board = f"https://{params['host']}/{params['tenant']}/JobBoard/{params['board_id']}"
    jobs = {}
    total = None
    for _ in range(settings["scraping"]["max_api_pages"]):
        data = request_json(f"{board}/JobBoardView/LoadSearchResults", settings, body={
            "opportunitySearch": {"Top": PAGE_SIZE, "Skip": len(jobs), "QueryString": "",
                                  "OrderBy": [], "Filters": []},
            "matchCriteria": {"PreferredJobs": [], "Educations": [], "LicenseAndCertifications": [],
                              "Skills": [], "hasNoLicenses": False, "SkippedSkills": []},
        })
        total = data["totalCount"]
        before = len(jobs)
        for posting in data.get("opportunities") or []:
            places = []
            for place in posting.get("Locations") or []:
                address = place.get("Address") or {}
                parts = [address.get("City"), (address.get("State") or {}).get("Name"),
                         (address.get("Country") or {}).get("Name")]
                places.append(", ".join(part for part in parts if part) or place.get("LocalizedDescription"))
            jobs[normalize_url(f"{board}/OpportunityDetail?opportunityId={posting['Id']}")] = job(
                posting["Title"], places
            )
        if len(jobs) >= total:
            return listing(jobs, total)
        if len(jobs) == before:
            raise RuntimeError(f"UKG Pro stopped after {len(jobs)} of {total} jobs")
        pause(settings)
    raise RuntimeError("UKG Pro returned more pages than max_api_pages allows")
