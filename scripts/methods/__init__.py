"""One module per scraping method. data/methods.json documents each one."""

from methods import (
    adp_workforcenow,
    amazon,
    ashby,
    bamboohr,
    browser_page,
    browser_paginated,
    eightfold,
    greenhouse,
    icims_jibe,
    jazzhr,
    lever,
    oracle_hcm,
    radancy,
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
    "oracle_hcm": oracle_hcm,
    "radancy": radancy,
    "bamboohr": bamboohr,
    "adp_workforcenow": adp_workforcenow,
    "jazzhr": jazzhr,
    "browser_paginated": browser_paginated,
    "browser_page": browser_page,
}


def fetch(method, params, settings):
    if method not in METHODS:
        raise ValueError(f"unknown method: {method}")
    return METHODS[method].fetch(params, settings)
