"""Push one scan to the user's dashboard. Push-only: the dashboard never calls back.

The payload is built from SQLite rows and nothing else, so prompts, chat text, file
paths, environment variables and keys have no way into it.
"""
import json
import os
import re
import stat
import urllib.error
import urllib.parse
import urllib.request

from . import __version__, rubric
from .core import UA, now_iso

DEFAULT_URL = "https://dashboard.vostuk.com"
TOKEN_RE = re.compile(r"^vsk_[A-Za-z0-9_-]{40,}$")
SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")
MAX_COINS = 200


class UploadError(RuntimeError):
    pass


def token_file_path():
    return os.environ.get("VOSTUK_UPLOAD_TOKEN_FILE") or os.path.join(
        os.path.expanduser("~"), ".config", "vostuk", "credentials.toml")


def load_token():
    """VOSTUK_UPLOAD_TOKEN, else upload_token = "vsk_..." from a 0600 credentials file."""
    tok = os.environ.get("VOSTUK_UPLOAD_TOKEN", "").strip()
    if not tok:
        path = token_file_path()
        if not os.path.exists(path):
            raise UploadError("no upload token: set VOSTUK_UPLOAD_TOKEN or create "
                              f"{path} (chmod 600) with upload_token = \"vsk_...\"")
        mode = os.stat(path).st_mode
        if os.name == "posix" and mode & (stat.S_IRWXG | stat.S_IRWXO):
            raise UploadError(f"{path} is readable by other users; run: chmod 600 {path}")
        with open(path) as f:
            for line in f:
                m = re.match(r'\s*upload_token\s*=\s*"([^"]+)"', line)
                if m:
                    tok = m.group(1).strip()
                    break
    if not TOKEN_RE.match(tok):
        raise UploadError("upload token is malformed (expected vsk_ followed by 40+ characters)")
    return tok


def endpoint():
    base = (os.environ.get("VOSTUK_DASHBOARD_URL") or DEFAULT_URL).rstrip("/")
    u = urllib.parse.urlparse(base)
    if u.scheme != "https" and not (u.scheme == "http" and u.hostname in ("127.0.0.1", "localhost", "::1")):
        raise UploadError("VOSTUK_DASHBOARD_URL must be https:// (http only to this computer)")
    return base, base + "/api/v1/scans"


def build_payload(conn, scan_id, repo_url=None, commit_sha=None):
    scan = conn.execute("SELECT scan_id, ts FROM scans WHERE scan_id=?", (scan_id,)).fetchone()
    if not scan:
        raise UploadError(f"unknown scan_id {scan_id!r}")
    rows = conn.execute(
        "SELECT c.mint, c.symbol, c.pair, c.metrics, r.data AS rc, s.score, s.verdict, s.reasons, "
        "s.rubric_version, s.model_name, s.flag FROM scores s "
        "JOIN coins c ON c.scan_id=s.scan_id AND c.mint=s.mint "
        "JOIN rugchecks r ON r.scan_id=s.scan_id AND r.mint=s.mint "
        "WHERE s.scan_id=? ORDER BY s.score DESC, c.mint LIMIT ?", (scan_id, MAX_COINS)).fetchall()
    if not rows:
        raise UploadError("this scan has no recorded scores yet; record_score first")
    coins, models = [], set()
    for r in rows:
        rc = json.loads(r["rc"])
        models.add(r["model_name"])
        coins.append({
            "mint": r["mint"], "symbol": r["symbol"], "pair": r["pair"],
            "metrics": {k: json.loads(r["metrics"]).get(k) for k in rubric.METRIC_KEYS},
            "rugcheck": {k: rc.get(k) for k in rubric.RUGCHECK_KEYS},
            "score": r["score"], "verdict": r["verdict"], "reasons": json.loads(r["reasons"]),
            "flag": r["flag"],
        })
    payload = {"scan_id": scan["scan_id"], "ts": scan["ts"], "scanner_version": __version__,
               "rubric_version": rows[0]["rubric_version"],
               "model_name": " / ".join(sorted(models))[:80], "coins": coins}
    if repo_url:
        u = urllib.parse.urlparse(repo_url)
        if u.scheme != "https" or not u.hostname:
            raise UploadError("repo_url must be an https:// URL")
        payload["repo_url"] = repo_url[:300]
    if commit_sha:
        if not SHA_RE.match(commit_sha):
            raise UploadError("commit_sha must be 7-40 lowercase hex characters")
        payload["commit_sha"] = commit_sha
    return payload


def post(url, token, payload, idem, timeout=30):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": f"Bearer {token}", "Idempotency-Key": idem,
        "Content-Type": "application/json", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode() or "{}")
        except ValueError:
            detail = {}
        return e.code, detail


def sync_results(conn, scan_id, repo_url=None, commit_sha=None, poster=post):
    base, url = endpoint()
    token = load_token()
    payload = build_payload(conn, scan_id, repo_url, commit_sha)
    status, resp = poster(url, token, payload, scan_id)
    if status not in (200, 201):
        msg = resp.get("detail") if isinstance(resp, dict) else None
        raise UploadError(f"dashboard answered HTTP {status}" + (f": {msg}" if msg else ""))
    with conn:
        conn.execute("UPDATE scans SET uploaded_at=?, upload_result=? WHERE scan_id=?",
                     (now_iso(), json.dumps({"status": status}), scan_id))
    return {"uploaded": len(payload["coins"]), "replay": status == 200 and bool(resp.get("replay")),
            "dashboard_url": resp.get("url") or f"{base}/scans/{scan_id}"}

