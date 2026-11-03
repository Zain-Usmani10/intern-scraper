"""BambooHR: reads every job from the public careers list API."""

from methods.common import job, listing, normalize_url, request_json, require


def fetch(params, settings):
    require(params, "company")
    site = f"https://{params['company']}.bamboohr.com/careers"
    data = request_json(f"{site}/list", settings)
    jobs = {}
    for posting in data["result"]:
        place = posting.get("location") or {}
        ats = posting.get("atsLocation") or {}
        location = ", ".join(
            part for part in (place.get("city"), place.get("state"),
                              ats.get("province"), ats.get("country")) if part
        )
        jobs[normalize_url(f"{site}/{posting['id']}")] = job(posting["jobOpeningName"], [location])
    return listing(jobs, (data.get("meta") or {}).get("totalCount"))
