"""Runs a prompt from data/prompts.json with `claude -p` and waits for it.

Claude can only use the tools the prompt lists, and can only write the
files its allowed_tools name. Python passes the prompt through stdin and
captures the reply, so nothing prints to your terminal.
"""

import json
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

import config


class ClaudeUnavailable(Exception):
    pass


def claude_executable():
    """Find claude.exe directly, so Windows .cmd quoting can't break arguments."""
    wrapper = shutil.which("claude")
    if not wrapper:
        raise ClaudeUnavailable("Claude Code isn't installed or isn't on PATH.")
    wrapper = Path(wrapper)
    native = wrapper.parent / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
    return str(native if native.exists() else wrapper)


def build_prompt(prompt_key, values):
    text = "\n".join(config.load_prompts()[prompt_key]["prompt"])
    for key, value in values.items():
        text = text.replace("{" + key + "}", str(value))
    return text


def log_call(entry):
    log = config.read_json(config.CLAUDE_LOG_FILE, default=[])
    log.append(entry)
    config.write_json(config.CLAUDE_LOG_FILE, log)


def run(prompt_key, values, timeout_seconds, settings):
    """Run one prompt. Return Claude's one-line reply. Raises on failure."""
    prompt = config.load_prompts()[prompt_key]
    # "Edit(data/tmp/x.json)" makes the Edit tool available, limited to that file.
    tools = dict.fromkeys(rule.split("(")[0] for rule in prompt["allowed_tools"])
    command = [
        claude_executable(), "-p",
        "--tools", ",".join(tools),
        "--allowedTools", *prompt["allowed_tools"],
        "--permission-mode", "dontAsk",
        "--output-format", "json",
        "--no-session-persistence",
    ]
    if settings["claude"].get("model"):
        command += ["--model", settings["claude"]["model"]]

    started = time.time()
    entry = {
        "prompt": prompt_key,
        "values": values,
        "started": datetime.now().isoformat(timespec="seconds"),
    }
    process = subprocess.Popen(
        command, cwd=config.ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
    )
    try:
        stdout, stderr = process.communicate(build_prompt(prompt_key, values), timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        # Kill Claude and anything it started.
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True)
        process.communicate()
        entry.update(seconds=round(time.time() - started), error="timed out")
        log_call(entry)
        raise TimeoutError(f"Claude took longer than {timeout_seconds} seconds")

    entry["seconds"] = round(time.time() - started)
    try:
        result = json.loads(stdout)
    except json.JSONDecodeError:
        entry["error"] = (stderr or stdout).strip()[:500]
        log_call(entry)
        raise RuntimeError(f"Claude failed: {entry['error'] or 'no output'}")

    entry.update(
        reply=result.get("result", "")[:500],
        turns=result.get("num_turns"),
        denied_tools=[
            f"{denial['tool_name']}: {json.dumps(denial.get('tool_input', {}))[:200]}"
            for denial in result.get("permission_denials", [])
        ],
        is_error=result.get("is_error"),
    )
    log_call(entry)
    if result.get("is_error"):
        raise RuntimeError(f"Claude returned an error: {entry['reply']}")
    return entry["reply"]
