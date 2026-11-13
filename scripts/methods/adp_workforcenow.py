"""ADP Workforce Now: reads a public career center's job list API."""

from methods.common import Collector, job, normalize_url, pause, request_json, require

PAGE_SIZE = 50
API = "https://workforcenow.adp.com/mascsr/default/careercenter/public/events/staffing/v1/job-requisitions"
JOB_PAGE = "https://workforcenow.adp.com/mascsr/default/mdf/recruitment/recruitment.html"


def external_id(posting):
    for field in (posting.get("customFieldGroup") or {}).get("stringFields") or []:
        if (field.get("nameCode") or {}).get("codeValue") == "ExternalJobID" and field.get("stringValue"):
            return field["stringValue"]
    return posting["itemID"]


def fetch(params, settings):
    require(params, "cid", "cc_id")
    site = f"cid={params['cid']}&ccId={params['cc_id']}&lang=en_CA"
    found = Collector()
    total = None

    def read_posting(posting):
        url = normalize_url(f"{JOB_PAGE}?{site}&jobId={external_id(posting)}")
        places = [(place.get("nameCode") or {}).get("shortName")
                  for place in posting.get("requisitionLocations") or []]
        return url, job(posting["requisitionTitle"], places)
    for _ in range(settings["scraping"]["max_api_pages"]):
        data = request_json(f"{API}?{site}&locale=en_CA&$top={PAGE_SIZE}&$skip={len(found)}", settings)
        total = data["meta"]["totalNumber"]
        postings = data.get("jobRequisitions") or []
        for posting in postings:
            found.add(posting, read_posting)
        if not postings or len(found) >= total:
            return found.listing(total)
        pause(settings)
    raise RuntimeError("ADP returned more pages than max_api_pages allows")
