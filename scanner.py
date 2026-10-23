#!/usr/bin/env python3
"""AI coin scanner: finds new Solana meme coins, runs basic safety checks,
and asks YOUR AI to rate each one.

READ-ONLY. This program never connects a wallet, never signs anything and
never buys or sells. It only reads public data and writes a report.

Run:  python3 scanner.py            (one scan)
      python3 scanner.py --loop 10  (scan every 10 minutes)
      python3 scanner.py --no-ai    (skip the AI step, free)
"""
import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

import ai

HERE = os.path.dirname(os.path.abspath(__file__))
UA = {"User-Agent": "ai-coin-scanner/1.0 (educational, read-only)"}

DEX_LATEST = "https://api.dexscreener.com/token-profiles/latest/v1"
DEX_TOKENS = "https://api.dexscreener.com/tokens/v1/solana/{}"
RUGCHECK = "https://api.rugcheck.xyz/v1/tokens/{}/report/summary"


# ---------------------------------------------------------------- settings

DEFAULTS = {
    "AI_PROVIDER": "anthropic",       # anthropic | openai | none
    "AI_MODEL": "",                   # blank = provider default (see ai.py)
    "AI_BASE_URL": "",                # only for openai-compatible servers
    "MIN_LIQUIDITY_USD": "20000",
    "MIN_VOLUME_24H_USD": "50000",
    "MIN_AGE_HOURS": "1",
    "MAX_AGE_HOURS": "72",
    "MAX_RUGCHECK_SCORE": "5000",     # RugCheck risk score, higher = riskier
    "MAX_AI_CALLS_PER_SCAN": "10",    # caps what one scan can cost you
}


def load_env(path):
    """Read KEY=value lines from a .env file into os.environ (if not already set)."""
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def setting(name):
    return os.environ.get(name, DEFAULTS[name])


def num(name):
    """Read a number setting. Accepts 20,000 or $20000 or a trailing # comment."""
    raw = setting(name).split("#")[0].replace(",", "").replace("$", "").strip()
    try:
        return float(raw)
    except ValueError:
        sys.exit(f"{name}={setting(name)!r} in .env is not a number")


# ---------------------------------------------------------------- fetching

def get_json(url, timeout=15):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def latest_solana_tokens():
    """Newest token profiles posted to DexScreener, Solana only."""
    seen, out = set(), []
    for p in get_json(DEX_LATEST):
        addr = p.get("tokenAddress")
        if p.get("chainId") == "solana" and addr and addr not in seen:
            seen.add(addr)
            out.append(addr)
    return out


def best_pair(address):
    """The pair with the most liquidity for this token, or None."""
    pairs = get_json(DEX_TOKENS.format(address)) or []
    pairs = [p for p in pairs if p.get("chainId") == "solana"]
    if not pairs:
        return None
    return max(pairs, key=lambda p: (p.get("liquidity") or {}).get("usd") or 0)


def rugcheck(address):
    """RugCheck summary: {'score': int, 'risks': [...]}. None if unavailable."""
    try:
        return get_json(RUGCHECK.format(address))
    except (OSError, ValueError):  # network errors, timeouts, bad JSON
        return None


# ---------------------------------------------------------------- filters

def coin_facts(pair, now_ms=None):
    """Flatten a DexScreener pair into the numbers the filters and the AI use."""
    now_ms = now_ms or time.time() * 1000
    created = pair.get("pairCreatedAt") or now_ms
    info = pair.get("info") or {}
    txns = (pair.get("txns") or {}).get("h24") or {}
    return {
        "address": pair["baseToken"]["address"],
        "symbol": pair["baseToken"].get("symbol", "?"),
        "name": pair["baseToken"].get("name", "?"),
        "url": pair.get("url", ""),
        "price_usd": float(pair.get("priceUsd") or 0),
        "liquidity_usd": (pair.get("liquidity") or {}).get("usd") or 0,
        "volume_24h_usd": (pair.get("volume") or {}).get("h24") or 0,
        "market_cap_usd": pair.get("marketCap") or pair.get("fdv") or 0,
        "price_change_1h_pct": (pair.get("priceChange") or {}).get("h1") or 0,
        "price_change_24h_pct": (pair.get("priceChange") or {}).get("h24") or 0,
        "buys_24h": txns.get("buys", 0),
        "sells_24h": txns.get("sells", 0),
        "age_hours": round((now_ms - created) / 3_600_000, 1),
        "has_website": bool(info.get("websites")),
        "socials": [s.get("type") for s in info.get("socials") or []],
    }


def check_numbers(f):
    """Return a list of reasons this coin fails the number filters (empty = passes)."""
    fails = []
    if f["liquidity_usd"] < num("MIN_LIQUIDITY_USD"):
        fails.append(f"liquidity ${f['liquidity_usd']:,.0f} below minimum")
    if f["volume_24h_usd"] < num("MIN_VOLUME_24H_USD"):
        fails.append(f"24h volume ${f['volume_24h_usd']:,.0f} below minimum")
    if f["age_hours"] < num("MIN_AGE_HOURS"):
        fails.append(f"too new ({f['age_hours']}h)")
    if f["age_hours"] > num("MAX_AGE_HOURS"):
        fails.append(f"too old ({f['age_hours']}h)")
    return fails


def check_safety(rc):
    """Return a list of rug-risk reasons from a RugCheck summary (empty = passes).

    A missing report counts as a FAIL: if we cannot check it, we do not trust it.
    """
    if rc is None:
        return ["no RugCheck report (could not check)"]
    fails = []
    if (rc.get("score") or 0) > num("MAX_RUGCHECK_SCORE"):
        fails.append(f"RugCheck risk score {rc.get('score')}")
    for risk in rc.get("risks") or []:
        if risk.get("level") == "danger":
            fails.append(f"RugCheck danger: {risk.get('name')}")
    return fails


# ---------------------------------------------------------------- output

def print_table(rows):
    if not rows:
        print("No coins passed the filters this scan.")
        return
    print(f"\n{'SYMBOL':<12}{'AGE h':>7}{'LIQ $':>12}{'VOL 24h $':>13}{'AI':>5}  VERDICT / WHY")
    for r in rows:
        ai_score = "-" if r["ai_score"] is None else str(r["ai_score"])
        print(f"{r['symbol'][:11]:<12}{r['age_hours']:>7}{r['liquidity_usd']:>12,.0f}"
              f"{r['volume_24h_usd']:>13,.0f}{ai_score:>5}  {r['ai_verdict']}: {r['ai_reason'][:70]}")
        print(f"{'':<12}{r['url']}")


TEXT_FIELDS = ("symbol", "name", "ai_verdict", "ai_reason")


def csv_safe(value):
    """Coin names are written by strangers. A name like =HYPERLINK(...) would run as a
    formula when you open the CSV in Excel or Sheets, so prefix it with ' to keep it text."""
    s = str(value)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def append_csv(rows, path):
    fields = ["scanned_at", "symbol", "name", "address", "age_hours", "price_usd",
              "liquidity_usd", "volume_24h_usd", "market_cap_usd", "ai_score",
              "ai_verdict", "ai_reason", "url"]
    new = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerows([{k: csv_safe(v) if k in TEXT_FIELDS else v for k, v in r.items()}
                     for r in rows])


# ---------------------------------------------------------------- main loop

def scan(use_ai=True, verbose=False):
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    provider = setting("AI_PROVIDER") if use_ai else "none"
    print("NOT FINANCIAL ADVICE - educational watchlist only. Most new meme coins go to zero.")
    print(f"[{now}] scanning (AI: {provider})")

    addresses = latest_solana_tokens()
    print(f"  {len(addresses)} new Solana tokens found")

    passed = []
    for addr in addresses:
        time.sleep(0.3)  # be polite to the free APIs
        try:
            pair = best_pair(addr)
        except (OSError, ValueError) as e:  # one bad response skips one coin, not the scan
            if verbose:
                print(f"  skip {addr[:8]}... fetch failed: {e}")
            continue
        if not pair:
            continue
        f = coin_facts(pair)
        fails = check_numbers(f)
        if not fails:
            fails = check_safety(rugcheck(addr))
        if fails:
            if verbose:
                print(f"  skip {f['symbol']:<10} {'; '.join(fails)}")
            continue
        passed.append(f)
    print(f"  {len(passed)} passed numbers + safety")

    max_calls = int(num("MAX_AI_CALLS_PER_SCAN"))
    rows = []
    for i, f in enumerate(passed):
        if provider != "none" and i < max_calls:
            r = ai.rate_coin(f, provider, setting("AI_MODEL"), setting("AI_BASE_URL"))
        else:
            r = {"score": None, "verdict": "not rated", "reason": "AI off or call cap reached"}
        rows.append({**f, "scanned_at": now, "ai_score": r["score"],
                     "ai_verdict": r["verdict"], "ai_reason": r["reason"]})

    rows.sort(key=lambda r: -1 if r["ai_score"] is None else r["ai_score"], reverse=True)
    print_table(rows)
    if rows:
        print("\nNOT FINANCIAL ADVICE. A score is a reason to look, not to buy.")
    if rows:
        out = os.path.join(HERE, "scans.csv")
        append_csv(rows, out)
        print(f"\nSaved to {out}")


def main():
    load_env(os.path.join(HERE, ".env"))
    ap = argparse.ArgumentParser(description="Read-only AI meme coin scanner. Never trades.")
    ap.add_argument("--loop", type=float, metavar="MINUTES", help="scan again every N minutes")
    ap.add_argument("--no-ai", action="store_true", help="skip the AI step (free)")
    ap.add_argument("--verbose", "-v", action="store_true", help="show why each coin was skipped")
    args = ap.parse_args()

    while True:
        try:
            scan(use_ai=not args.no_ai, verbose=args.verbose)
        except (OSError, ValueError) as e:
            print(f"  network error: {e}", file=sys.stderr)
        if not args.loop:
            break
        time.sleep(max(args.loop, 1) * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nstopped.")
