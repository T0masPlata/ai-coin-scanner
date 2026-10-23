# AI Coin Scanner

A starter kit for building your own meme coin scanner, rated by **your own AI** (Claude or ChatGPT).
It finds new Solana coins, filters out the obvious junk and rug risks, and asks your AI which ones
are worth a closer look.

**It never trades.** No wallet, no keys to money, no buying or selling. It only reads public data
and prints a watchlist.

**Start here: [HOW-TO-USE.md](HOW-TO-USE.md)** - exact setup steps, from zero to your first scan.

```
python3 scanner.py --no-ai     # free test run, no AI
python3 scanner.py             # scan + AI ratings
python3 scanner.py --loop 15   # keep scanning every 15 minutes
```

| File | What it is |
|---|---|
| `scanner.py` | Fetches coins, runs the filters and safety checks, prints the table |
| `ai.py` | Sends each coin to your AI and reads back a score |
| `prompt.txt` | The instructions your AI follows. Edit this to change how it judges coins |
| `.env.example` | Settings template. Copy to `.env` and add your key |
| `tests/` | Offline tests: `python3 -m unittest` |

Educational project. Not financial advice. Most new meme coins go to zero.
