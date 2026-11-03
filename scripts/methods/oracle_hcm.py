"""Oracle Recruiting Cloud: pages through the Candidate Experience search API."""

import urllib.parse

from methods.common import job, listing, normalize_url, pause, request_json, require

PAGE_SIZE = 25  # Oracle's maximum.


def search(params, settings, offset=0, location_id=None, extra=()):
    parts = [f"siteNumber={params['site']}", f"limit={PAGE_SIZE}", f"offset={offset}",
             "sortBy=POSTING_DATES_DESC", *extra]
    if params.get("keyword"):
        parts.append(f"keyword={params['keyword']}")
    if location_id:
        parts.append(f"selectedLocationsFacet={location_id}")
    finder = urllib.parse.quote("findReqs;" + ",".join(parts), safe="=;,")
    url = (f"https://{params['host']}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
           f"?onlyData=true&expand=requisitionList.secondaryLocations,locationsFacet&finder={finder}")
    return request_json(url, settings)["items"][0]


def country_ids(params, settings, countries):
    """Look up the site's location filter ID for each country name."""
    ids = []
    for country in countries:
        data = search(params, settings, extra=(
            "facetsList=LOCATIONS", "userTargetFacetName=LOCATIONS",
            f"userTargetFacetInputTerm={country}",
        ))
        ids += [str(facet["Id"]) for facet in data.get("locationsFacet") or []
                if facet["Name"].casefold() == country.casefold()]
    return ids


def fetch(params, settings):
    require(params, "host", "site")
    jobs = {}
    for location_id in params.get("location_ids") or [None]:
        read, offset, total = 0, 0, None
        for _ in range(settings["scraping"]["max_api_pages"]):
            data = search(params, settings, offset, location_id)
            total = data["TotalJobsCount"]
            postings = data.get("requisitionList") or []
            for posting in postings:
                url = normalize_url(
                    f"https://{params['host']}/hcmUI/CandidateExperience/en/sites/"
                    f"{params['site']}/job/{posting['Id']}"
                )
                places = [posting.get("PrimaryLocation")]
                places += [extra.get("Name") for extra in posting.get("secondaryLocations") or []]
                jobs[url] = job(posting["Title"], places)
            read += len(postings)
            offset += PAGE_SIZE
            if not postings or offset >= total:
                break
            pause(settings)
        if read < total:
            raise RuntimeError(f"Oracle stopped after {read} of {total} jobs")
    # Every location's total was read in full, so the unique count is complete.
    return listing(jobs, len(jobs))
