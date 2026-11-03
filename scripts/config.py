"""Paths to every data file, plus helpers to read and write JSON."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
TMP = DATA / "tmp"

SETTINGS_FILE = DATA / "settings.json"
METHODS_FILE = DATA / "methods.json"
PROMPTS_FILE = DATA / "prompts.json"
COMPANIES_FILE = DATA / "companies.json"
ENTERED_FILE = DATA / "companies_entered.json"
STATE_FILE = DATA / "seen_jobs.json"

RECOMMENDATIONS_FILE = TMP / "recommendations.json"
EVIDENCE_FILE = TMP / "evidence.json"
VALIDATION_FILE = TMP / "validation.json"
CLAUDE_LOG_FILE = TMP / "claude_calls.json"
SCRATCH_DIR = TMP / "scratch"


def read_json(path, default=None):
    path = Path(path)
    if not path.exists():
        if default is not None:
            return default
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, data):
    """Write JSON atomically, so a crash never leaves a half-written file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_file = path.with_suffix(path.suffix + ".tmp")
    temp_file.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    temp_file.replace(path)


def load_settings():
    return read_json(SETTINGS_FILE)


def load_methods():
    return read_json(METHODS_FILE)


def load_prompts():
    return read_json(PROMPTS_FILE)


def load_companies():
    return read_json(COMPANIES_FILE, default=[])
