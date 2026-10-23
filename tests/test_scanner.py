"""Offline tests: no internet, no AI key, no cost.  Run: python3 -m unittest"""
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ai        # noqa: E402
import scanner   # noqa: E402

NOW = 1_800_000_000_000
PAIR = {
    "chainId": "solana", "url": "https://dexscreener.com/solana/x",
    "baseToken": {"address": "Abc", "symbol": "TEST", "name": "Test Coin"},
    "priceUsd": "0.001", "liquidity": {"usd": 50_000}, "volume": {"h24": 200_000},
    "marketCap": 1_000_000, "priceChange": {"h1": 5, "h24": 40},
    "txns": {"h24": {"buys": 900, "sells": 700}},
    "pairCreatedAt": NOW - 5 * 3_600_000, "info": {"websites": [{"url": "x"}], "socials": []},
}


class Filters(unittest.TestCase):
    def facts(self, **changes):
        return {**scanner.coin_facts(PAIR, now_ms=NOW), **changes}

    def test_good_coin_passes(self):
        self.assertEqual(scanner.check_numbers(self.facts()), [])

    def test_low_liquidity_fails(self):
        self.assertTrue(scanner.check_numbers(self.facts(liquidity_usd=100)))

    def test_too_old_fails(self):
        self.assertTrue(scanner.check_numbers(self.facts(age_hours=500)))

    def test_age_is_computed(self):
        self.assertEqual(self.facts()["age_hours"], 5.0)

    def test_missing_rugcheck_fails(self):
        self.assertTrue(scanner.check_safety(None))

    def test_rugcheck_danger_fails(self):
        rc = {"score": 1, "risks": [{"name": "Mint authority still enabled", "level": "danger"}]}
        self.assertTrue(scanner.check_safety(rc))

    def test_clean_rugcheck_passes(self):
        self.assertEqual(scanner.check_safety({"score": 1, "risks": []}), [])


class AIReplies(unittest.TestCase):
    def test_parses_json(self):
        r = ai.parse_reply('Sure! {"score": 7, "verdict": "watch", "reason": "busy"}')
        self.assertEqual(r, {"score": 7, "verdict": "WATCH", "reason": "busy"})

    def test_rejects_out_of_range(self):
        self.assertIsNone(ai.parse_reply('{"score": 99, "verdict": "WATCH"}'))

    def test_rejects_garbage(self):
        self.assertIsNone(ai.parse_reply("I think it moons"))

    def test_unknown_verdict_becomes_skip(self):
        self.assertEqual(ai.parse_reply('{"score": 9, "verdict": "BUY NOW"}')["verdict"], "SKIP")

    def test_both_providers_send_coin_data(self):
        for provider, reply in [
            ("anthropic", {"content": [{"text": '{"score": 4, "verdict": "SKIP", "reason": "meh"}'}]}),
            ("openai", {"choices": [{"message": {"content": '{"score": 4, "verdict": "SKIP", "reason": "meh"}'}}]}),
        ]:
            with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k", "OPENAI_API_KEY": "k"}), \
                 mock.patch.object(ai, "_post", return_value=reply) as post:
                r = ai.rate_coin({"symbol": "TEST"}, provider)
            self.assertEqual(r["score"], 4, provider)
            self.assertIn("TEST", json.dumps(post.call_args.args[2]), provider)

    def test_missing_key_is_an_error_not_a_crash(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            r = ai.rate_coin({"symbol": "TEST"}, "anthropic")
        self.assertEqual(r["verdict"], "AI error")
        self.assertIn("ANTHROPIC_API_KEY", r["reason"])


class Hardening(unittest.TestCase):
    def test_csv_formula_is_neutralised(self):
        self.assertEqual(scanner.csv_safe('=HYPERLINK("x")'), '\'=HYPERLINK("x")')
        self.assertEqual(scanner.csv_safe("PEPE"), "PEPE")

    def test_csv_file_has_no_live_formula(self):
        import csv, tempfile
        path = os.path.join(tempfile.mkdtemp(), "s.csv")
        scanner.append_csv([{"symbol": "=1+1", "name": "@x", "ai_score": 5}], path)
        row = next(csv.DictReader(open(path)))
        self.assertTrue(row["symbol"].startswith("'"))
        self.assertTrue(row["name"].startswith("'"))

    def test_key_never_sent_over_plain_http_to_another_machine(self):
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "k"}), \
             mock.patch.object(ai, "_post") as post:
            r = ai.rate_coin({"symbol": "T"}, "openai", "m", "http://192.168.1.50:8000/v1")
        post.assert_not_called()
        self.assertIn("unencrypted", r["reason"])

    def test_local_http_server_is_allowed(self):
        reply = {"choices": [{"message": {"content": '{"score": 1, "verdict": "SKIP"}'}}]}
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "k"}), \
             mock.patch.object(ai, "_post", return_value=reply):
            self.assertEqual(ai.rate_coin({}, "openai", "m", "http://localhost:11434/v1")["score"], 1)

    def test_empty_ai_answer_is_an_error_not_a_crash(self):
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "k"}), \
             mock.patch.object(ai, "_post", return_value={"choices": []}):
            self.assertEqual(ai.rate_coin({}, "openai")["verdict"], "AI error")

    def test_human_style_numbers_in_env(self):
        with mock.patch.dict(os.environ, {"MIN_LIQUIDITY_USD": "$20,000  # twenty k"}):
            self.assertEqual(scanner.num("MIN_LIQUIDITY_USD"), 20000)


class NeverTrades(unittest.TestCase):
    def test_no_wallet_or_signing_code(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        banned = ["private_key", "keypair", "sendTransaction", "signTransaction", "swap"]
        for name in ("scanner.py", "ai.py"):
            src = open(os.path.join(root, name)).read()
            for word in banned:
                self.assertNotIn(word, src, f"{word} found in {name}")


if __name__ == "__main__":
    unittest.main()
