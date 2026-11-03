"""Radancy (TalentBrew): pages through the SITE/search-jobs/results JSON."""

import html
import re
import urllib.parse

from methods.common import job, listing, normalize_url, pause, request_json, require

PAGE_SIZE = 100
TOTAL = re.compile(r'data-total-results="(\d+)"')
JOB = re.compile(r'<a[^>]+href="([^"]*/job/[^"]+)"[^>]*>(.*?)</a>', re.S)
TITLE = re.compile(r"<h[23][^>]*>(.*?)</h[23]>", re.S)
LOCATION = re.compile(r'class="[^"]*job-location[^"]*"[^>]*>([^<]+)<')
COUNTRY = re.compile(r'data-facet-type="2"[^>]*data-id="(\d+)"[^>]*data-display="([^"]+)"')


def search(params, settings, page=1, country_id=None):
    query = [
        ("CurrentPage", page), ("RecordsPerPage", PAGE_SIZE),
        ("Keywords", params.get("keywords", "")), ("SearchType", 5),
        ("SearchResultsModuleName", "Search Results"), ("SearchFiltersModuleName", "Search Filters"),
    ]
    if country_id:
        query += [
            ("ActiveFacetID", country_id), ("FacetFilters[0].ID", country_id),
            ("FacetFilters[0].FacetType", 2), ("FacetFilters[0].IsApplied", "true"),
        ]
    url = f"{params['site'].rstrip('/')}/search-jobs/results?{urllib.parse.urlencode(query)}"
    return request_json(url, settings, headers={"X-Requested-With": "XMLHttpRequest"})


def country_ids(params, settings, countries):
    """Look up the site's country filter ID for each country name."""
    wanted = {country.casefold() for country in countries}
    filters = search(params, settings).get("filters") or ""
    return [facet_id for facet_id, name in COUNTRY.findall(filters)
            if html.unescape(name).casefold() in wanted]


def fetch(params, settings):
    require(params, "site")
    origin = "{0.scheme}://{0.netloc}".format(urllib.parse.urlsplit(params["site"]))
    jobs = {}
    for country_id in params.get("country_ids") or [None]:
        read, total = 0, None
        for page in range(1, settings["scraping"]["max_api_pages"] + 1):
            results = search(params, settings, page, country_id).get("results") or ""
            if total is None:
                match = TOTAL.search(results)
                if not match:
                    raise RuntimeError("Radancy results have no total")
                total = int(match.group(1))
            found = JOB.findall(results)
            for href, body in found:
                title = TITLE.search(body)
                location = LOCATION.search(body)
                jobs[normalize_url(urllib.parse.urljoin(origin, html.unescape(href)))] = job(
                    html.unescape(re.sub(r"<[^>]+>", "", title.group(1) if title else body)),
                    [html.unescape(location.group(1))] if location else [],
                )
            read += len(found)
            if not found or read >= total:
                break
            pause(settings)
        if read < total:
            raise RuntimeError(f"Radancy stopped after {read} of {total} jobs")
    # Every country's total was read in full, so the unique count is complete.
    return listing(jobs, len(jobs))
