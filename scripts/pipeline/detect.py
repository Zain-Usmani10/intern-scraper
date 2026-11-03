"""Step 2b: turn page evidence into ordered method candidates, with no AI.

Each candidate is {"method", "params", "source"}. The validator tests them
in order, and the first that passes wins.
"""

import re
import urllib.parse

import filters
from methods import oracle_hcm, radancy, workday

GREENHOUSE = [
    re.compile(r"greenhouse\.io/v1/boards/([\w-]+)", re.I),
    re.compile(r"greenhouse\.io/embed/job_board(?:/js)?\?for=([\w-]+)", re.I),
    re.compile(r"(?:job-boards|boards)(?:\.eu)?\.greenhouse\.io/(?!embed\b)([\w-]+)", re.I),
]
ASHBY = [
    re.compile(r"api\.ashbyhq\.com/posting-api/job-board/([\w.-]+)", re.I),
    re.compile(r"jobs\.ashbyhq\.com/([\w.-]+)", re.I),
]
LEVER = [
    re.compile(r"api\.(eu\.)?lever\.co/v0/postings/([\w.-]+)", re.I),
    re.compile(r"jobs\.(eu\.)?lever\.co/([\w.-]+)", re.I),
]
WORKDAY_API = re.compile(r"https://([\w.-]+\.myworkdayjobs\.com)/wday/cxs/([\w-]+)/([\w-]+)/jobs", re.I)
WORKDAY_PAGE = re.compile(
    r"https://(([\w-]+)\.wd\d+\.myworkdayjobs\.com)/(?:[a-z]{2}-[A-Z]{2}/)?([\w-]+)", re.I
)
ORACLE = re.compile(
    r"https://([\w.-]+\.oraclecloud\.com)/hcmUI/CandidateExperience/(?:[a-z]{2}(?:-[A-Z]{2})?/)?sites/(\w+)", re.I
)
ADP = re.compile(r"https://workforcenow\.adp\.com/[^\s\"'<>]*recruitment\.html\?[^\s\"'<>]+", re.I)
BAMBOOHR = [re.compile(r"https?://([\w-]+)\.bamboohr\.com", re.I)]
JAZZHR = [re.compile(r"https?://([\w-]+)\.applytojob\.com", re.I)]
NOT_BOARD_NAMES = {"embed", "v1", "jobs", "api", "static", "assets", "www", "app"}


def evidence_text(evidence):
    parts = [evidence.get("careers_url", ""), evidence.get("final_url", "")]
    parts += evidence.get("links", [])
    parts += evidence.get("frames", [])
    parts += evidence.get("system_references", [])
    parts += [request["url"] for request in evidence.get("api_requests", [])]
    return " ".join(parts)


def first_names(patterns, text, group=1):
    found = []
    for pattern in patterns:
        for match in pattern.finditer(text):
            name = match.group(group)
            if name.lower() not in NOT_BOARD_NAMES and name not in found:
                found.append(name)
    return found


def all_facets(facets):
    """Workday nests some filters, like countries, inside a group."""
    for facet in facets:
        yield facet
        yield from (value for value in facet.get("values") or [] if value.get("facetParameter"))


def country_facet(facets, settings):
    """Return {facetParameter: [ids]} for the allowed countries, if Workday has that filter."""
    wanted = {name.casefold() for name in settings["locations"]["allowed_countries"]}
    for facet in all_facets(facets):
        ids = [
            value["id"] for value in facet.get("values") or []
            if value.get("id") and (value.get("descriptor") or "").casefold() in wanted
        ]
        if ids:
            return {facet["facetParameter"]: ids}
    return {}


def workday_candidates(host, tenant, site, settings):
    """Prefer Workday's intern and country filters. Fall back to searching "intern"."""
    base = {"host": host, "tenant": tenant, "site": site}
    candidates = []
    try:
        facets = workday.search({**base, "search_text": ""}, settings, 0).get("facets") or []
    except Exception:
        facets = []
    countries = country_facet(facets, settings)

    best = None
    for facet in facets:
        values = [
            value for value in facet.get("values") or []
            if value.get("id") and filters.is_internship(value.get("descriptor", ""), "", settings)
        ]
        count = sum(value.get("count", 0) for value in values)
        if values and (best is None or count > best[2]):
            best = (facet["facetParameter"], [value["id"] for value in values], count)

    if best and countries:
        candidates.append({
            "method": "workday",
            "params": {**base, "search_text": "",
                       "applied_facets": {best[0]: best[1], **countries}},
            "source": f"Workday filters {best[0]} and {next(iter(countries))}",
        })
    if best:
        candidates.append({
            "method": "workday",
            "params": {**base, "search_text": "", "applied_facets": {best[0]: best[1]}},
            "source": f"Workday filter {best[0]}",
        })
    candidates.append({
        "method": "workday",
        "params": {**base, "search_text": "intern"},
        "source": "Workday search for intern",
    })
    return candidates


def pagination_candidate(evidence):
    """Build browser_paginated settings from a next-page link, if it has one."""
    control = evidence.get("more_results_control") or {}
    href = control.get("href")
    if not href:
        return None
    current = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(evidence["final_url"]).query))
    following = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(href).query))
    for param, value in following.items():
        if not value.isdigit() or current.get(param) == value:
            continue
        next_value = int(value)
        if param in current and current[param].isdigit():
            first = int(current[param])
        else:
            first = 1 if next_value == 2 else 0
        step = next_value - first
        if step > 0:
            return {
                "method": "browser_paginated",
                "params": {
                    "url": evidence["final_url"], "page_param": param,
                    "first_page": first, "page_step": step,
                },
                "source": "next-page link on the careers page",
            }
    return None


def slug_guesses(name):
    words = re.findall(r"[a-z0-9]+", name.lower())
    guesses = ["".join(words), "-".join(words), words[0] if words else ""]
    return [guess for index, guess in enumerate(guesses) if guess and guess not in guesses[:index]]


def candidates(name, evidence, settings):
    """Return method candidates in the order they should be tested."""
    text = evidence_text(evidence)
    found = []

    def add(method, params, source):
        if not any(c["method"] == method and c["params"] == params for c in found):
            found.append({"method": method, "params": params, "source": source})

    for board in first_names(GREENHOUSE, text):
        add("greenhouse", {"board": board}, "Greenhouse link on the careers page")
    for board in first_names(ASHBY, text):
        add("ashby", {"board": board}, "Ashby link on the careers page")
    for pattern in LEVER:
        for match in pattern.finditer(text):
            params = {"site": match.group(2)}
            if match.group(1):
                params["region"] = "eu"
            if params["site"].lower() not in NOT_BOARD_NAMES:
                add("lever", params, "Lever link on the careers page")

    workday_sites = {(m.group(1), m.group(2), m.group(3)) for m in WORKDAY_API.finditer(text)}
    if not workday_sites:
        workday_sites = {(m.group(1), m.group(2), m.group(3)) for m in WORKDAY_PAGE.finditer(text)}
    for host, tenant, site in sorted(workday_sites):
        for candidate in workday_candidates(host, tenant, site, settings):
            add(candidate["method"], candidate["params"], candidate["source"])

    for request in evidence.get("api_requests", []):
        parts = urllib.parse.urlsplit(request["url"])
        origin = f"{parts.scheme}://{parts.netloc}"
        if parts.path.endswith("/api/pcsx/search"):
            params = {"url": evidence["final_url"]}
            domain = dict(urllib.parse.parse_qsl(parts.query)).get("domain")
            if domain:
                params["domain"] = domain
            add("eightfold", params, "Eightfold search request")
        if parts.path == "/api/jobs" and "json" in request["type"]:
            page_path = urllib.parse.urlsplit(evidence["final_url"]).path
            jobs_path = page_path[: page_path.find("/jobs") + 5] if "/jobs" in page_path else "/jobs"
            keywords = dict(urllib.parse.parse_qsl(parts.query)).get("keywords", "intern")
            add("icims_jibe", {"site": origin, "jobs_path": jobs_path, "keywords": keywords},
                "iCIMS Jibe /api/jobs request")

    countries = settings["locations"]["allowed_countries"]
    for host, site in dict.fromkeys(ORACLE.findall(text)):
        base = {"host": host, "site": site}
        try:
            ids = oracle_hcm.country_ids(base, settings, countries)
        except Exception:
            ids = []
        if ids:
            add("oracle_hcm", {**base, "location_ids": ids}, "Oracle site, filtered to your countries")
        add("oracle_hcm", base, "Oracle site")

    for link in dict.fromkeys(ADP.findall(text)):
        query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(link).query))
        if query.get("cid") and query.get("ccId"):
            add("adp_workforcenow", {"cid": query["cid"], "cc_id": query["ccId"]}, "ADP career center link")
    for company in first_names(BAMBOOHR, text):
        add("bamboohr", {"company": company}, "BambooHR link")
    for company in first_names(JAZZHR, text):
        add("jazzhr", {"company": company}, "JazzHR link")

    final = urllib.parse.urlsplit(evidence.get("final_url") or "")
    if "/search-jobs" in final.path:
        base = {"site": f"{final.scheme}://{final.netloc}{final.path.split('/search-jobs')[0]}"}
        try:
            ids = radancy.country_ids(base, settings, countries)
        except Exception:
            ids = None  # Not a Radancy site.
        if ids:
            add("radancy", {**base, "country_ids": ids}, "Radancy site, filtered to your countries")
        if ids is not None:
            add("radancy", {**base, "keywords": "intern"}, "Radancy site, searching intern")

    if (final.hostname or "").endswith("amazon.jobs"):
        query = dict(urllib.parse.parse_qsl(final.query)).get("base_query") or "intern"
        add("amazon", {"query": query}, "amazon.jobs site")

    if not found:
        for guess in slug_guesses(name):
            add("greenhouse", {"board": guess}, "guessed from the company name")
            add("ashby", {"board": guess}, "guessed from the company name")
            add("lever", {"site": guess}, "guessed from the company name")

    paginated = pagination_candidate(evidence)
    if paginated:
        add(paginated["method"], paginated["params"], paginated["source"])
    elif (
        evidence.get("job_like_links")
        and not evidence.get("more_results_control")
        and not evidence.get("loads_more_on_scroll")
    ):
        add("browser_page", {"url": evidence["final_url"]}, "job links on a single page")

    return found


def same_source(company, method, params):
    """True when an existing company already reads from this exact source."""
    if company.get("method") != method:
        return False
    keys = {
        "greenhouse": ("board",), "ashby": ("board",), "lever": ("site",),
        "workday": ("host", "site"), "eightfold": ("url",), "amazon": ("query",),
        "icims_jibe": ("site", "keywords"), "oracle_hcm": ("host", "site"), "radancy": ("site",),
        "bamboohr": ("company",), "adp_workforcenow": ("cc_id",), "jazzhr": ("company",),
        "browser_paginated": ("url",), "browser_page": ("url",),
    }.get(method, ())
    return bool(keys) and all(company["params"].get(key) == params.get(key) for key in keys)
