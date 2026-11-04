"""Internship and location filters, built from data/settings.json."""

import re
from functools import lru_cache

import pycountry

# Common names that pycountry doesn't list.
EXTRA_COUNTRY_NAMES = {
    "US": ["USA", "U.S.", "U.S.A.", "United States of America", "America"],
    "GB": ["UK", "U.K.", "England", "Scotland", "Wales", "Great Britain", "Britain"],
    "KR": ["South Korea", "Korea"],
    "CN": ["PRC", "Mainland China"],
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


def hint_verdict(hint, settings, countries=None):
    """Judge free text, such as a title or job card. True, False, or None if unknown."""
    chosen = tuple(countries or settings["locations"]["allowed_countries"])
    allowed, _ = location_patterns(chosen)
    if allowed and allowed.search(hint):
        return True
    blocked = blocked_names_pattern(chosen)
    if blocked and blocked.search(hint):
        return False
    return None


def hint_allowed(hint, settings, countries=None):
    verdict = hint_verdict(hint, settings, countries)
    return settings["locations"]["include_unknown_locations"] if verdict is None else verdict


def location_verdict(locations, settings, countries=None):
    """True if any location is allowed, False if they only name other
    countries, None if no country can be identified."""
    text = " ; ".join(location for location in locations if location)
    if not text.strip():
        return None
    allowed, blocked = location_patterns(tuple(countries or settings["locations"]["allowed_countries"]))
    if allowed and allowed.search(text):
        return True
    if blocked and blocked.search(text):
        return False
    return None


def location_allowed(locations, settings, countries=None):
    verdict = location_verdict(locations, settings, countries)
    return settings["locations"]["include_unknown_locations"] if verdict is None else verdict


@lru_cache(maxsize=None)
def country_terms(countries):
    """Map each place name or code to (allowed country, weight).

    A code that is both a country code and another allowed country's state
    code, like CA (Canada, or California), leans to the state, weakly.
    """
    names, codes, state_codes = {}, {}, {}
    for name in countries:
        country = pycountry.countries.lookup(name)
        country_names, country_codes = country_names_and_codes(country)
        for term in country_names:
            names[term.casefold()] = (name, 2)
        for region in pycountry.subdivisions.get(country_code=country.alpha_2) or []:
            names.setdefault(region.name.casefold(), (name, 1))
            state_codes[region.code.split("-")[1]] = name
        for code in country_codes:
            codes[code] = (name, 1)
    for code, name in state_codes.items():
        codes[code] = (name, 0.5) if code in codes and codes[code][0] != name else (name, 1)
    return names, codes, terms_regex(set(names), set(codes))


def job_country(text, countries):
    """Return the allowed country a location or title points to, or ""."""
    names, codes, pattern = country_terms(tuple(countries))
    scores = {}
    for term in pattern.findall(text or "") if pattern else []:
        country, weight = names.get(term.casefold()) or codes.get(term) or (None, 0)
        if country:
            scores[country] = scores.get(country, 0) + weight
    return max(scores, key=lambda country: (scores[country], -countries.index(country)), default="")


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
        # The location field decides. When it names no country, the title
        # and card text decide, as in "Internship Germany (Nürnberg)".
        verdict = location_verdict(job["locations"], settings, countries)
        if verdict is None:
            verdict = hint_verdict(f"{job['title']} {job.get('location_hint', '')}", settings, countries)
        if verdict is None:
            verdict = settings["locations"]["include_unknown_locations"]
        if not verdict:
            continue
        chosen = list(countries or settings["locations"]["allowed_countries"])
        country = (job_country(" ; ".join(job["locations"]), chosen)
                   or job_country(f"{job['title']} {job.get('location_hint', '')}", chosen))
        kept[url] = {"title": job["title"], "location": "; ".join(job["locations"][:3]),
                     "country": country}
    return kept
