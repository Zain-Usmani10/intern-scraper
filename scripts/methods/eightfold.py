"""Eightfold: pages through a career site's search API, using the page URL's filters."""

import urllib.parse

import pycountry

from methods.common import job, listing, normalize_url, pause, request_json, require


def site_origin(url):
    parts = urllib.parse.urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def default_domain(url):
    return ".".join(urllib.parse.urlsplit(url).hostname.split(".")[-2:])


def places(position):
    """Use Eightfold's standard locations, like "Kulim, 02, MY", with the
    country code spelled out, since many raw locations name only a city."""
    found = []
    for place in position.get("standardizedLocations") or []:
        parts = [part.strip() for part in place.split(",")]
        country = pycountry.countries.get(alpha_2=parts[-1]) if len(parts[-1]) == 2 else None
        if country:
            found.append(", ".join([*parts[:-1], country.name]))
    return found or position.get("locations") or []


def search_url(params, start):
    page = urllib.parse.urlsplit(params["url"])
    filters = [
        (key, value)
        for key, value in urllib.parse.parse_qsl(page.query, keep_blank_values=True)
        if key not in ("pid", "start", "domain")
    ]
    domain = params.get("domain") or default_domain(params["url"])
    query = urllib.parse.urlencode([*filters, ("domain", domain), ("start", start)])
    return f"{site_origin(params['url'])}/api/pcsx/search?{query}"


def fetch(params, settings):
    require(params, "url")
    origin = site_origin(params["url"])
    jobs = {}
    reported = None

    for _ in range(settings["scraping"]["max_api_pages"]):
        data = request_json(search_url(params, len(jobs)), settings)["data"]
        reported = data["count"]
        before = len(jobs)
        for position in data["positions"]:
            url = normalize_url(urllib.parse.urljoin(origin, position["positionUrl"]))
            jobs[url] = job(position["name"], places(position))

        if len(jobs) >= reported:
            return listing(jobs, reported)
        if len(jobs) == before:
            # The API stopped returning jobs early. Treat it as a failed read.
            raise RuntimeError(f"Eightfold stopped after {len(jobs)} of {reported} jobs")
        pause(settings)

    raise RuntimeError("Eightfold returned more pages than max_api_pages allows")
