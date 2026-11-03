"""The JSON files in data/tmp/ that Python and Claude use to pass data.

Python resets a file to its template from data/prompts.json before each
Claude call. The files stay after the run, so you can open them anytime.
recommendations.json is never reset.
"""

from datetime import datetime

import config


def prepare_tmp():
    """Create data/tmp/ and any missing files, without touching existing ones."""
    config.SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    for prompt in config.load_prompts().values():
        path = config.ROOT / prompt["output_file"]
        if not path.exists():
            config.write_json(path, prompt["output_template"])
    for path, empty in (
        (config.RECOMMENDATIONS_FILE, []),
        (config.EVIDENCE_FILE, {}),
        (config.VALIDATION_FILE, {}),
        (config.CLAUDE_LOG_FILE, []),
    ):
        if not path.exists():
            config.write_json(path, empty)


def output_path(prompt_key):
    return config.ROOT / config.load_prompts()[prompt_key]["output_file"]


def reset(prompt_key, **values):
    """Write the prompt's template to its file, with some fields filled in."""
    template = dict(config.load_prompts()[prompt_key]["output_template"])
    template.update(values)
    config.write_json(output_path(prompt_key), template)


def read(prompt_key):
    return config.read_json(output_path(prompt_key))


def add_recommendation(company, careers_url, recommendation):
    recommendations = config.read_json(config.RECOMMENDATIONS_FILE, default=[])
    recommendations.append({
        "date": datetime.now().isoformat(timespec="seconds"),
        "company": company,
        "careers_url": careers_url,
        **recommendation,
    })
    config.write_json(config.RECOMMENDATIONS_FILE, recommendations)
