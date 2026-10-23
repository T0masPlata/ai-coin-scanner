"""The real MCP server over stdio, driven by the official MCP client. Offline: the DB is
seeded with fake coins first, so no tool here touches the network.
Needs the `mcp` package (skipped without it): .venv/bin/python -m unittest tests.test_mcp_stdio
"""
import asyncio
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
try:
    from mcp import Client
    from mcp.client.stdio import StdioServerParameters
except ImportError:  # pragma: no cover
    Client = None

from vostuk_scanner import core, db, rubric  # noqa: E402
from tests.test_mcp import GOOD, FROZEN, NOW, fake_fetch  # noqa: E402


@unittest.skipIf(Client is None, "mcp SDK not installed")
class Stdio(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "s.db")
        c = db.connect(self.path)
        self.sid = core.scan_candidates(c, fetch=fake_fetch, now_ms=NOW)["scan_id"]
        for m in (GOOD, FROZEN):
            core.rugcheck(c, m, fetch=fake_fetch)
        c.close()

    async def calls(self, batch):
        params = StdioServerParameters(command=sys.executable, args=["-m", "vostuk_scanner"], cwd=ROOT,
                                       env={**os.environ, "VOSTUK_SCANNER_DB": self.path, "PYTHONPATH": ROOT})
        async with Client(params) as client:
            # all at once, the way Codex fans tool calls out
            return await asyncio.gather(*(client.call_tool(n, a) for n, a in batch))

    def run_calls(self, batch):
        out = []
        for r in asyncio.run(self.calls(batch)):
            text = "".join(getattr(c, "text", "") for c in r.content)
            out.append((r.is_error, text))
        return out

    def good(self, mint, score):
        return ("record_score", {"scan_id": self.sid, "mint": mint, "score": score,
                                 "verdict": "WATCH" if score >= 7 else "SKIP",
                                 "reasons": ["liq_usd=80000 is deep"],
                                 "rubric_version": rubric.RUBRIC_VERSION, "model_name": "stdio-test"})

    def test_parallel_record_score_all_land(self):
        res = self.run_calls([self.good(GOOD, 7), self.good(FROZEN, 1), ("get_rubric", {})])
        for is_error, text in res:
            self.assertFalse(is_error, text)
        c = db.connect(self.path)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM scores").fetchone()[0], 2)

    def test_tool_calls_work_from_different_threads(self):
        # The SDK runs sync tools on worker threads; a connection opened on one thread and
        # reused on another raises sqlite3.ProgrammingError. Deterministic version of the race.
        import threading
        from unittest import mock
        from vostuk_scanner import server
        out = []

        def one(score):
            try:
                name, a = self.good(GOOD, score)
                out.append(server._call(core.record_score, *[a[k] for k in (
                    "scan_id", "mint", "score", "verdict", "reasons", "rubric_version", "model_name")])["ok"])
            except Exception as e:  # noqa: BLE001
                out.append(repr(e))
        with mock.patch.dict(os.environ, {"VOSTUK_SCANNER_DB": self.path}):
            for score in (7, 8):
                t = threading.Thread(target=one, args=(score,))
                t.start()
                t.join()
        self.assertEqual(out, [True, True])

    def test_rejection_message_reaches_the_model(self):
        name, a = self.good(GOOD, 7)
        a["score"] = 11
        (is_error, text), = self.run_calls([(name, a)])
        self.assertTrue(is_error)
        self.assertIn("between 0 and 10", text)

    def test_missing_rugcheck_message_reaches_the_model(self):
        name, a = self.good(GOOD, 7)
        a["mint"] = "not-in-scan"
        (is_error, text), = self.run_calls([(name, a)])
        self.assertTrue(is_error)
        self.assertIn("not a candidate", text)

    def test_sync_without_token_says_how_to_fix(self):
        env = os.environ.pop("VOSTUK_UPLOAD_TOKEN", None)
        os.environ["VOSTUK_UPLOAD_TOKEN_FILE"] = os.path.join(tempfile.mkdtemp(), "missing.toml")
        try:
            (is_error, text), = self.run_calls([("sync_results", {"scan_id": self.sid})])
        finally:
            os.environ.pop("VOSTUK_UPLOAD_TOKEN_FILE")
            if env:
                os.environ["VOSTUK_UPLOAD_TOKEN"] = env
        self.assertIn("no upload token", json.loads(text)["error"])


if __name__ == "__main__":
    unittest.main()
