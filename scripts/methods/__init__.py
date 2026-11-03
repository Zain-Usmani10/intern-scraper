"""One module per scraping method. data/methods.json documents each one."""

from methods import (
    amazon,
    ashby,
    browser_page,
    browser_paginated,
    eightfold,
    greenhouse,
    icims_jibe,
    lever,
    workday,
)

METHODS = {
    "greenhouse": greenhouse,
    "ashby": ashby,
    "lever": lever,
    "workday": workday,
    "eightfold": eightfold,
    "amazon": amazon,
    "icims_jibe": icims_jibe,
    "browser_paginated": browser_paginated,
    "browser_page": browser_page,
}


def fetch(method, params, settings):
    if method not in METHODS:
        raise ValueError(f"unknown method: {method}")
    return METHODS[method].fetch(params, settings)
