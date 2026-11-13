"""Gem: reads every job from the public job board API at api.gem.com."""

from methods.common import Collector, job, normalize_url, request_json, require


def read_posting(posting):
    places = [(office.get("location") or {}).get("name") for office in posting.get("offices") or []]
    return normalize_url(posting["absolute_url"]), job(
        posting["title"], places or [(posting.get("location") or {}).get("name")]
    )


def fetch(params, settings):
    require(params, "board")
    postings = request_json(
        f"https://api.gem.com/job_board/v0/{params['board']}/job_posts/", settings
    )
    found = Collector()
    for posting in postings:
        found.add(posting, read_posting)
    # The API has no total, but returns the whole board in one response.
    return found.listing()
