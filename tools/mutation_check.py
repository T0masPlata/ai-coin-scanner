#!/usr/bin/env python3
"""Mutation proof for the record_score / upload rules.

For each rule: copy the repo to a temp dir, break the rule in the source, run the
offline tests, and require that the named test goes RED. A rule whose test stays
green after the rule is removed is not actually tested.  Run: python3 tools/mutation_check.py
"""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MUTATIONS = [
    ("score range", "vostuk_scanner/rubric.py", "if not 0 <= score <= 10:", "if False:",
     "test_score_11_rejected"),
    ("integer score", "vostuk_scanner/rubric.py",
     "raise ScoreRejected(f\"score must be an integer 0-10 (got {score!r})\")", "pass",
     "test_non_integer_score_rejected"),
    ("verdict enum", "vostuk_scanner/rubric.py", 'if verdict not in ("WATCH", "SKIP"):', "if False:",
     "test_verdict_enum"),
    ("verdict band", "vostuk_scanner/rubric.py", "if verdict != expected:", "if False:",
     "test_watch_requires_7"),
    ("rugcheck row required", "vostuk_scanner/core.py", "    if not rc:\n        raise ScoreRejected",
     "    if not rc:\n        rc = {'data': '{}'}\n    if False:\n        raise ScoreRejected",
     "test_refuses_mint_without_rugcheck_row"),
    ("mint must be in scan", "vostuk_scanner/core.py", "    if not coin:\n", "    if False:\n",
     "test_refuses_mint_not_in_scan"),
    ("rubric version", "vostuk_scanner/rubric.py", "if rubric_version != RUBRIC_VERSION:", "if False:",
     "test_rubric_version_mismatch"),
    ("reason cites key", "vostuk_scanner/rubric.py", "if not any(k in r for k in CITABLE_KEYS):",
     "if False:", "test_reason_must_cite_metric_key"),
    ("reason length", "vostuk_scanner/rubric.py", "if len(r) > MAX_REASON_CHARS:", "if False:",
     "test_reason_count_and_length"),
    ("freeze cap", "vostuk_scanner/rubric.py", 'if rc.get("freeze_authority") and score > FREEZE_CAP:',
     "if False:", "test_freeze_authority_caps_score_at_2"),
    ("divergent flag", "vostuk_scanner/core.py", 'flag = "divergent" if', 'flag = None if',
     "test_divergent_flag"),
    ("payload from rows only", "vostuk_scanner/upload.py", '"flag": r["flag"],',
     '"flag": r["flag"], "env": dict(os.environ),', "test_payload_comes_from_rows_only"),
    ("idempotency key", "vostuk_scanner/upload.py", "poster(url, token, payload, scan_id)",
     "poster(url, token, payload, 'x')", "test_idempotency_key_is_scan_id_and_bearer_header"),
    ("token file perms", "vostuk_scanner/upload.py", "mode & (stat.S_IRWXG | stat.S_IRWXO)", "False",
     "test_token_file_must_be_0600"),
    ("no plain http", "vostuk_scanner/upload.py", 'if u.scheme != "https" and not', "if False and not",
     "test_no_plain_http_to_remote_dashboard"),
    ("no trading code", "vostuk_scanner/core.py", "DEX_BATCH = 30", "DEX_BATCH = 30\nsendTransaction = None",
     "test_no_wallet_or_signing_code"),
]


# These need the mcp SDK (run this script with the venv python) and drive the real stdio server.
STDIO_MUTATIONS = [
    ("rejection text reaches model", "vostuk_scanner/server.py",
     'raise ToolError(f"record_score rejected: {e}") from None',
     'raise ValueError(f"record_score rejected: {e}") from None',
     "test_rejection_message_reaches_the_model"),
    ("conn per call (threads)", "vostuk_scanner/server.py",
     "    conn = db.connect()\n    try:", "    global _C\n    conn = _C = globals().get('_C') or db.connect()\n    try:",
     "test_parallel_record_score_all_land"),
]
try:
    import mcp  # noqa: F401
except ImportError:
    print("mcp SDK not importable: skipping the stdio mutations (use .venv/bin/python)")
    STDIO_MUTATIONS = []
STDIO = {m[0] for m in STDIO_MUTATIONS}
MUTATIONS += STDIO_MUTATIONS


def run(tmp, module="tests.test_mcp"):
    return subprocess.run([sys.executable, "-W", "ignore", "-m", "unittest", module, "-v"], cwd=tmp,
                          capture_output=True, text=True)


def main():
    base = tempfile.mkdtemp()
    clean = os.path.join(base, "clean")
    shutil.copytree(ROOT, clean, ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__"))
    r = run(clean)
    if r.returncode == 0 and STDIO:
        r = run(clean, "tests.test_mcp_stdio")
    if r.returncode != 0:
        print("UNMUTATED TESTS ARE RED, fix them first\n" + r.stderr[-2000:])
        return 1
    print("control: unmutated suite GREEN")
    bad = 0
    for i, (label, rel, old, new, test) in enumerate(MUTATIONS):
        tmp = os.path.join(base, f"m{i}")
        shutil.copytree(clean, tmp)
        path = os.path.join(tmp, rel)
        with open(path) as f:
            src = f.read()
        if old not in src:
            print(f"STALE   {label}: pattern not found in {rel}")
            bad += 1
            continue
        with open(path, "w") as f:
            f.write(src.replace(old, new, 1))
        r = run(tmp, "tests.test_mcp_stdio" if label in STDIO else "tests.test_mcp")
        red = r.returncode != 0 and any(test in ln and ("FAIL" in ln or "ERROR" in ln)
                                        for ln in r.stderr.splitlines())
        print(f"{'RED ok ' if red else 'SURVIVED'} {label:<24} -> {test}")
        bad += not red
    shutil.rmtree(base, ignore_errors=True)
    print(f"{len(MUTATIONS) - bad}/{len(MUTATIONS)} mutations killed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
