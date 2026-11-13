"""UKG Pro (UltiPro) Recruiting: pages through the job board's search API."""

from methods.common import Collector, job, normalize_url, pause, request_json, require

PAGE_SIZE = 50


def fetch(params, settings):
    require(params, "host", "tenant", "board_id")
    board = f"https://{params['host']}/{params['tenant']}/JobBoard/{params['board_id']}"
    found = Collector()
    total = None

    def read_posting(posting):
        places = []
        for place in posting.get("Locations") or []:
            address = place.get("Address") or {}
            parts = [address.get("City"), (address.get("State") or {}).get("Name"),
                     (address.get("Country") or {}).get("Name")]
            places.append(", ".join(part for part in parts if part) or place.get("LocalizedDescription"))
        url = normalize_url(f"{board}/OpportunityDetail?opportunityId={posting['Id']}")
        return url, job(posting["Title"], places)
    for _ in range(settings["scraping"]["max_api_pages"]):
        data = request_json(f"{board}/JobBoardView/LoadSearchResults", settings, body={
            "opportunitySearch": {"Top": PAGE_SIZE, "Skip": len(found), "QueryString": "",
                                  "OrderBy": [], "Filters": []},
            "matchCriteria": {"PreferredJobs": [], "Educations": [], "LicenseAndCertifications": [],
                              "Skills": [], "hasNoLicenses": False, "SkippedSkills": []},
        })
        total = data["totalCount"]
        before = len(found)
        for posting in data.get("opportunities") or []:
            found.add(posting, read_posting)
        if len(found) >= total:
            return found.listing(total)
        if len(found) == before:
            raise RuntimeError(f"UKG Pro stopped after {len(found)} of {total} jobs")
        pause(settings)
    raise RuntimeError("UKG Pro returned more pages than max_api_pages allows")
