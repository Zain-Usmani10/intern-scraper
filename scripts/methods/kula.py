"""Kula: pages through the job board API behind careers.kula.ai/ACCOUNT."""

import re

from methods.common import Collector, job, normalize_url, pause, request_json, require

PAGE_SIZE = 99


def fetch(params, settings):
    require(params, "account")
    found = Collector()

    def read_posting(posting):
        slug = re.sub(r"[^a-z0-9]+", "-", posting["title"].lower()).strip("-")
        places = [office.get("location") for office in (posting.get("ats_job") or {}).get("offices") or []]
        url = normalize_url(f"https://careers.kula.ai/{params['account']}/{posting['id']}-{slug}")
        return url, job(posting["title"], places)

    for page in range(1, settings["scraping"]["max_api_pages"] + 1):
        data = request_json(
            "https://careers.kula.ai/api/internal/ats_job_posts"
            f"?accountName={params['account']}&page={page}&type=ats_job_post.index&items={PAGE_SIZE}",
            settings,
        )
        for posting in data.get("data") or []:
            found.add(posting, read_posting)
        meta = data["meta"]
        if page >= meta.get("pages", 0):
            return found.listing(meta["count"])
        pause(settings)
    raise RuntimeError("Kula returned more pages than max_api_pages allows")
