"""Internship and location filters, built from data/settings.json."""

import re
from functools import lru_cache

import pycountry

# Common names that pycountry doesn't list.
EXTRA_COUNTRY_NAMES = {
    "US": ["USA", "U.S.", "U.S.A.", "United States of America", "America"],
    "GB": ["UK", "U.K.", "England", "Scotland", "Wales", "Great Britain", "Britain"],
    "KR": ["South Korea", "Korea"],
    "TW": ["Taiwan"],
    "RU": ["Russia"],
    "VN": ["Vietnam"],
    "AE": ["UAE"],
    "CZ": ["Czech Republic"],
    "NL": ["Holland"],
    "TR": ["Turkey"],
}

# Job sites often name only a state or province, like "Austin, TX" or
# "Toronto, ON". When one of these countries isn't allowed, its states block
# a job. That also makes "CA" mean California, not Canada.
STATE_COUNTRIES = ("US", "CA")


def keyword_pattern(keywords):
    """Match whole words only, so "intern" doesn't match "internal"."""
    parts = []
    for keyword in sorted(keywords, key=len, reverse=True):
        words = re.split(r"[\s-]+", keyword.strip())
        parts.append(r"[\s-]?".join(re.escape(word) for word in words if word))
    return re.compile(rf"\b({'|'.join(parts)})\b", re.IGNORECASE)


@lru_cache(maxsize=None)
def intern_pattern(keywords):
    return keyword_pattern(keywords)


def is_internship(title, url, settings):
    keywords = tuple(settings["internship_filter"]["keywords"])
    return bool(intern_pattern(keywords).search(f"{title} {url}"))


def country_names_and_codes(country):
    names = {country.name}
    for attribute in ("official_name", "common_name"):
        if getattr(country, attribute, None):
            names.add(getattr(country, attribute))
    names.update(EXTRA_COUNTRY_NAMES.get(country.alpha_2, []))
    return names, {country.alpha_2, country.alpha_3}


def terms_regex(names, codes):
    """Names match in any case. Short codes must be uppercase, like CA or NY."""
    patterns = []
    if names:
        joined = "|".join(re.escape(name) for name in sorted(names, key=len, reverse=True))
        patterns.append(rf"(?i:(?<![A-Za-z])(?:{joined})(?![A-Za-z]))")
    if codes:
        joined = "|".join(re.escape(code) for code in sorted(codes, key=len, reverse=True))
        patterns.append(rf"(?<![A-Za-z])(?:{joined})(?![A-Za-z])")
    return re.compile("|".join(patterns)) if patterns else None


@lru_cache(maxsize=None)
def location_patterns(allowed_countries):
    """Build regexes for allowed places and for every other country."""
    allowed = [pycountry.countries.lookup(name) for name in allowed_countries]
    allowed_codes = {country.alpha_2 for country in allowed}

    allowed_names, allowed_short_codes = set(), set()
    for country in allowed:
        names, codes = country_names_and_codes(country)
        allowed_names |= names
        allowed_short_codes |= codes
        for region in pycountry.subdivisions.get(country_code=country.alpha_2) or []:
            allowed_names.add(region.name)
            allowed_short_codes.add(region.code.split("-")[1])

    blocked_names, blocked_codes = set(), set()
    for country in pycountry.countries:
        if country.alpha_2 not in allowed_codes:
            names, codes = country_names_and_codes(country)
            blocked_names |= names - allowed_names
            blocked_codes |= codes - allowed_short_codes

    state_names, state_codes = blocked_states(allowed_codes)
    allowed_short_codes -= state_codes
    blocked_names |= state_names - allowed_names
    blocked_codes |= state_codes

    return terms_regex(allowed_names, allowed_short_codes), terms_regex(blocked_names, blocked_codes)


def blocked_states(allowed_codes):
    """State names and codes of STATE_COUNTRIES that aren't allowed."""
    names, codes = set(), set()
    for country_code in STATE_COUNTRIES:
        if country_code not in allowed_codes:
            for region in pycountry.subdivisions.get(country_code=country_code):
                names.add(region.name)
                codes.add(region.code.split("-")[1])
    return names, codes


@lru_cache(maxsize=None)
def blocked_names_pattern(allowed_countries):
    """Other countries' names only. Used on free text, where short uppercase
    words like AI or IT would be mistaken for country codes."""
    allowed_names = set()
    allowed_codes = set()
    for name in allowed_countries:
        country = pycountry.countries.lookup(name)
        allowed_codes.add(country.alpha_2)
        allowed_names |= country_names_and_codes(country)[0]
        for region in pycountry.subdivisions.get(country_code=country.alpha_2) or []:
            allowed_names.add(region.name)
    blocked = blocked_states(allowed_codes)[0] - allowed_names
    for country in pycountry.countries:
        if country.alpha_2 not in allowed_codes:
            blocked |= country_names_and_codes(country)[0] - allowed_names
    return terms_regex(blocked, set())


def hint_allowed(hint, settings, countries=None):
    """Judge free text, such as a job card, when there's no location field."""
    rules = settings["locations"]
    chosen = tuple(countries or rules["allowed_countries"])
    allowed, _ = location_patterns(chosen)
    if allowed and allowed.search(hint):
        return True
    blocked = blocked_names_pattern(chosen)
    if blocked and blocked.search(hint):
        return False
    return rules["include_unknown_locations"]


def location_allowed(locations, settings, countries=None):
    """Keep a job if any location is allowed or no country can be identified.

    A job is dropped only when its locations name another country and none
    of them names an allowed one.
    """
    rules = settings["locations"]
    text = " ; ".join(location for location in locations if location)
    if not text.strip():
        return rules["include_unknown_locations"]

    allowed, blocked = location_patterns(tuple(countries or rules["allowed_countries"]))
    if allowed and allowed.search(text):
        return True
    if blocked and blocked.search(text):
        return False
    return rules["include_unknown_locations"]


def apply_filters(jobs, company, settings):
    """Filter {url: {title, locations}} with the company's or default rules."""
    filters = company.get("filters", {})
    use_intern_filter = filters.get(
        "intern_titles", settings["internship_filter"]["enabled_by_default"]
    )
    countries = filters.get("countries")

    kept = {}
    for url, job in jobs.items():
        if use_intern_filter and not is_internship(job["title"], url, settings):
            continue
        if job["locations"]:
            if not location_allowed(job["locations"], settings, countries):
                continue
        elif job.get("location_hint"):
            if not hint_allowed(f"{job['title']} {job['location_hint']}", settings, countries):
                continue
        kept[url] = {"title": job["title"], "location": "; ".join(job["locations"][:3])}
    return kept
