"""Offline tests for the MCP scanner: no internet, no AI, no cost.
Run: python3 -m unittest   (needs only the standard library; the MCP SDK is not imported)
"""
import json
import os
import stat
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vostuk_scanner import core, db, rubric, upload  # noqa: E402
from vostuk_scanner.rubric import ScoreRejected     # noqa: E402

NOW = 1_800_000_000_000
GOOD = "Good1111111111111111111111111111111111pump"
FROZEN = "Froz1111111111111111111111111111111111pump"
OTHER = "Othr1111111111111111111111111111111111pump"


def pair(mint, sym, liq=80_000, vol=300_000, age_h=5):
    return {"chainId": "solana", "pairAddress": "P" + mint[:8],
            "baseToken": {"address": mint, "symbol": sym},
            "liquidity": {"usd": liq}, "volume": {"h24": vol}, "fdv": 900_000,
            "priceChange": {"h1": 3}, "txns": {"h1": {"buys": 300, "sells": 200}},
            "pairCreatedAt": NOW - age_h * 3_600_000}


def report(freeze=False, mint_auth=False):
    return {"score_normalised": 3, "risks": [], "freezeAuthority": "X" if freeze else None,
            "mintAuthority": "Y" if mint_auth else None,
            "topHolders": [{"pct": 60, "owner": "POOL"}, {"pct": 5, "owner": "a"}, {"pct": 4, "owner": "b"}],
            "knownAccounts": {"POOL": {"type": "AMM"}},
            "markets": [{"lp": {"lpLockedPct": 100}}]}


def fake_fetch(url):
    if "token-profiles" in url or "token-boosts" in url:
        return [{"chainId": "solana", "tokenAddress": m} for m in (GOOD, FROZEN, OTHER)] + \
               [{"chainId": "ethereum", "tokenAddress": "0xabc"}]
    if "/tokens/v1/solana/" in url:
        return [pair(GOOD, "GOOD"), pair(FROZEN, "FRZ"), pair(OTHER, "TINY", liq=100)]
    if "rugcheck" in url:
        return report(freeze=FROZEN in url)
    raise AssertionError(url)


def args(**kw):
    a = {"score": 8, "verdict": "WATCH", "reasons": ["liq_usd=80000 is deep", "top10_pct=9 is spread out"],
         "rubric_version": rubric.RUBRIC_VERSION, "model_name": "test-model"}
    a.update(kw)
    return a


class Base(unittest.TestCase):
    def setUp(self):
        self.c = db.connect(":memory:")
        self.scan = core.scan_candidates(self.c, fetch=fake_fetch, now_ms=NOW)
        self.sid = self.scan["scan_id"]

    def rc(self, mint):
        return core.rugcheck(self.c, mint, fetch=fake_fetch)

    def score(self, mint=GOOD, **kw):
        return core.record_score(self.c, self.sid, mint, **args(**kw))


class Scan(Base):
    def test_filters_apply(self):
        mints = [c["mint"] for c in self.scan["candidates"]]
        self.assertIn(GOOD, mints)
        self.assertNotIn(OTHER, mints)          # liq 100 < min 5000
        self.assertEqual(len(mints), 2)

    def test_top10_ignores_pool(self):
        self.assertEqual(self.rc(GOOD)["top10_pct"], 9.0)

    def test_rugcheck_is_cached(self):
        self.assertFalse(self.rc(GOOD)["cached"])
        self.assertTrue(self.rc(GOOD)["cached"])


class RecordScoreRules(Base):
    def test_valid_score_is_stored(self):
        self.rc(GOOD)
        r = self.score()
        self.assertTrue(r["ok"])
        self.assertEqual(r["scored_count"], 1)
        self.assertEqual(r["remaining"], [FROZEN])

    def test_refuses_mint_without_rugcheck_row(self):
        with self.assertRaisesRegex(ScoreRejected, "no rugcheck row"):
            self.score()
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM scores").fetchone()[0], 0)

    def test_refuses_mint_not_in_scan(self):
        with self.assertRaisesRegex(ScoreRejected, "not a candidate"):
            self.score(mint=OTHER)

    def test_score_11_rejected(self):
        self.rc(GOOD)
        with self.assertRaisesRegex(ScoreRejected, "between 0 and 10"):
            self.score(score=11)

    def test_negative_score_rejected(self):
        self.rc(GOOD)
        with self.assertRaises(ScoreRejected):
            self.score(score=-1, verdict="SKIP")

    def test_non_integer_score_rejected(self):
        self.rc(GOOD)
        for bad in (7.5, "8", True):
            with self.assertRaisesRegex(ScoreRejected, "integer", msg=repr(bad)):
                self.score(score=bad)

    def test_verdict_enum(self):
        self.rc(GOOD)
        with self.assertRaisesRegex(ScoreRejected, "WATCH\" or \"SKIP"):
            self.score(verdict="BUY")

    def test_watch_requires_7(self):
        self.rc(GOOD)
        with self.assertRaisesRegex(ScoreRejected, "requires verdict 'SKIP'"):
            self.score(score=6, verdict="WATCH")

    def test_high_score_must_be_watch(self):
        self.rc(GOOD)
        with self.assertRaisesRegex(ScoreRejected, "requires verdict 'WATCH'"):
            self.score(score=9, verdict="SKIP")

    def test_rubric_version_mismatch(self):
        self.rc(GOOD)
        with self.assertRaisesRegex(ScoreRejected, "rubric_version"):
            self.score(rubric_version="r0")

    def test_reason_must_cite_metric_key(self):
        self.rc(GOOD)
        with self.assertRaisesRegex(ScoreRejected, "does not cite a metric key"):
            self.score(reasons=["looks like it will moon"])

    def test_reason_count_and_length(self):
        self.rc(GOOD)
        with self.assertRaises(ScoreRejected):
            self.score(reasons=[])
        with self.assertRaises(ScoreRejected):
            self.score(reasons=["liq_usd ok"] * 7)
        with self.assertRaisesRegex(ScoreRejected, "limit is 200"):
            self.score(reasons=["liq_usd " + "x" * 200])

    def test_freeze_authority_caps_score_at_2(self):
        self.rc(FROZEN)
        with self.assertRaisesRegex(ScoreRejected, "freeze_authority"):
            self.score(mint=FROZEN, score=3, verdict="SKIP")
        self.assertTrue(self.score(mint=FROZEN, score=2, verdict="SKIP")["ok"])

    def test_model_name_required(self):
        self.rc(GOOD)
        with self.assertRaises(ScoreRejected):
            self.score(model_name="  ")

    def test_divergent_flag(self):
        self.rc(GOOD)
        base = rubric.baseline_score(
            core.pair_metrics(pair(GOOD, "GOOD"), NOW),
            core.summarize_rugcheck(GOOD, report()))
        self.assertGreaterEqual(base, 5)
        r = core.record_score(self.c, self.sid, GOOD, **args(score=0, verdict="SKIP"))
        self.assertEqual(r["flag"], "divergent")
        r = self.score(score=base, verdict="WATCH" if base >= 7 else "SKIP")
        self.assertIsNone(r["flag"])


class BaselineRules(unittest.TestCase):
    def test_freeze_cap_in_baseline(self):
        m = {"liq_usd": 500_000, "vol_h24": 1_000_000, "age_min": 600, "buys_h1": 900, "sells_h1": 100}
        self.assertGreater(rubric.baseline_score(m, {}), 2)
        self.assertLessEqual(rubric.baseline_score(m, {"freeze_authority": True}), 2)

    def test_bounds(self):
        for m in ({}, {"liq_usd": 1e12, "vol_h24": 5e12, "buys_h1": 99, "sells_h1": 1, "age_min": 999}):
            self.assertTrue(0 <= rubric.baseline_score(m, {"top10_pct": 99}) <= 10)


class Upload(Base):
    TOKEN = "vsk_" + "A" * 43

    def scored(self):
        self.rc(GOOD)
        self.score(reasons=["liq_usd=80000 deep"])
        return self.sid

    def test_payload_comes_from_rows_only(self):
        p = upload.build_payload(self.c, self.scored())
        self.assertEqual(set(p), {"scan_id", "ts", "scanner_version", "rubric_version", "model_name", "coins"})
        coin = p["coins"][0]
        self.assertEqual(set(coin), {"mint", "symbol", "pair", "metrics", "rugcheck", "score",
                                     "verdict", "reasons", "flag"})
        self.assertEqual(set(coin["metrics"]), set(rubric.METRIC_KEYS))
        self.assertEqual(set(coin["rugcheck"]), set(rubric.RUGCHECK_KEYS))
        blob = json.dumps(p)
        for leak in (os.path.expanduser("~"), "PATH", "vsk_"):
            self.assertNotIn(leak, blob)

    def test_unscored_scan_is_not_uploaded(self):
        with self.assertRaisesRegex(upload.UploadError, "no recorded scores"):
            upload.build_payload(self.c, self.sid)

    def test_idempotency_key_is_scan_id_and_bearer_header(self):
        sid = self.scored()
        seen = {}

        def poster(url, token, payload, idem):
            seen.update(url=url, token=token, idem=idem)
            return 201, {"url": "https://dashboard.vostuk.com/scans/x"}
        with mock.patch.dict(os.environ, {"VOSTUK_UPLOAD_TOKEN": self.TOKEN}, clear=False):
            r = upload.sync_results(self.c, sid, poster=poster)
        self.assertEqual(seen["idem"], sid)
        self.assertEqual(seen["token"], self.TOKEN)
        self.assertNotIn("vsk_", seen["url"])
        self.assertEqual(r["uploaded"], 1)

    def test_server_error_is_reported(self):
        sid = self.scored()
        with mock.patch.dict(os.environ, {"VOSTUK_UPLOAD_TOKEN": self.TOKEN}):
            with self.assertRaisesRegex(upload.UploadError, "401"):
                upload.sync_results(self.c, sid, poster=lambda *a: (401, {"detail": "revoked"}))

    def test_token_file_must_be_0600(self):
        d = tempfile.mkdtemp()
        path = os.path.join(d, "credentials.toml")
        with open(path, "w") as f:
            f.write(f'upload_token = "{self.TOKEN}"\n')
        env = {"VOSTUK_UPLOAD_TOKEN": "", "VOSTUK_UPLOAD_TOKEN_FILE": path}
        os.chmod(path, 0o644)
        with mock.patch.dict(os.environ, env):
            with self.assertRaisesRegex(upload.UploadError, "chmod 600"):
                upload.load_token()
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
            self.assertEqual(upload.load_token(), self.TOKEN)

    def test_malformed_token_refused(self):
        with mock.patch.dict(os.environ, {"VOSTUK_UPLOAD_TOKEN": "sk-ant-oops"}):
            with self.assertRaisesRegex(upload.UploadError, "malformed"):
                upload.load_token()

    def test_no_plain_http_to_remote_dashboard(self):
        with mock.patch.dict(os.environ, {"VOSTUK_DASHBOARD_URL": "http://dashboard.vostuk.com"}):
            with self.assertRaises(upload.UploadError):
                upload.endpoint()
        with mock.patch.dict(os.environ, {"VOSTUK_DASHBOARD_URL": "http://127.0.0.1:8795"}):
            self.assertEqual(upload.endpoint()[1], "http://127.0.0.1:8795/api/v1/scans")


class NoModelNoMoney(unittest.TestCase):
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def sources(self):
        pkg = os.path.join(self.ROOT, "vostuk_scanner")
        out = {}
        for n in os.listdir(pkg):
            if n.endswith(".py"):
                with open(os.path.join(pkg, n)) as f:
                    out[n] = f.read()
        return out

    def test_no_wallet_or_signing_code(self):
        banned = ["private_key", "keypair", "sendTransaction", "signTransaction", "swap", "solders",
                  "solana.rpc", "jupiter"]
        for name, src in self.sources().items():
            for word in banned:
                self.assertNotIn(word, src, f"{word} found in vostuk_scanner/{name}")

    def test_server_imports_no_ai_client_or_credentials(self):
        banned = ["import anthropic", "import openai", "ANTHROPIC_API_KEY", "OPENAI_API_KEY",
                  "CLAUDE_CODE_OAUTH_TOKEN", "claude.ai", "chatgpt.com", "from .. import ai", "import ai"]
        for name, src in self.sources().items():
            for word in banned:
                self.assertNotIn(word, src, f"{word} found in vostuk_scanner/{name}")


if __name__ == "__main__":
    unittest.main()


class NotFinancialAdvice(unittest.TestCase):
    """The disclaimer is part of the product: it must reach the AI, the docs and the terminal."""
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def read(self, rel):
        with open(os.path.join(self.ROOT, rel)) as f:
            return f.read()

    def test_rubric_carries_disclaimer(self):
        self.assertIn("NOT FINANCIAL ADVICE", core.get_rubric()["disclaimer"])

    def test_docs_lead_with_disclaimer(self):
        for rel in ("README.md", "HOW-TO-USE.md"):
            self.assertIn("NOT FINANCIAL ADVICE", self.read(rel)[:600], rel)

    def test_server_instructions_and_cli_say_it(self):
        self.assertIn("NOT FINANCIAL ADVICE", self.read("vostuk_scanner/server.py").split('"""', 4)[3])
        self.assertGreaterEqual(self.read("scanner.py").count("NOT FINANCIAL ADVICE"), 2)
