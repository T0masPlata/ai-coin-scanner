# How to use the AI Coin Scanner

This guide takes you from nothing to a working scanner that uses your own AI. It takes about
15 minutes. You don't need to know how to code, but you will type a few commands.

> **What this does:** every scan, it pulls the newest Solana meme coins that have a DexScreener
> profile, throws out the ones that are too small, too old or look like rugs, and asks your AI to
> score the rest from 0 to 10.
>
> **What this does NOT do:** it never buys, sells or touches a wallet. It is a watchlist tool.
> Not financial advice. Most new meme coins go to zero.

---

## Step 1. Install Python

You need Python 3.9 or newer. Nothing else: the scanner uses no extra packages.

Check if you already have it. Open a terminal (Mac: the **Terminal** app; Windows: **PowerShell**)
and type:

```
python3 --version
```

If you see `Python 3.9` or higher, skip ahead. If not, download it from
[python.org/downloads](https://www.python.org/downloads/) and install it.
On Windows, tick **"Add Python to PATH"** during install, and type `python` instead of `python3`
everywhere in this guide.

**Mac, after installing from python.org:** open **Finder > Applications > Python 3.x** and
double-click **Install Certificates.command** once. Without it, every scan fails with
`CERTIFICATE_VERIFY_FAILED`.

## Step 2. Download the scanner

If you have git:

```
git clone https://github.com/T0masPlata/ai-coin-scanner.git
cd ai-coin-scanner
```

No git? On the GitHub page click **Code > Download ZIP**, unzip it, and `cd` into the folder.

Do a free test run with no AI, to prove the scanner itself works:

```
python3 scanner.py --no-ai
```

You should see something like:

```
[2026-10-23T19:05:00+00:00] scanning (AI: none)
  23 new Solana tokens found
  1 passed numbers + safety

SYMBOL        AGE h       LIQ $    VOL 24h $   AI  VERDICT / WHY
CI              1.1      67,924    1,162,983    -  not rated: AI off or call cap reached
            https://dexscreener.com/solana/fdckb3...
```

"0 passed" is normal too. Most new coins fail the filters. Add `-v` to see why each one was
skipped.

## Step 3. Get an AI key

Pick **one**. You pay the AI company directly for what you use.

**Claude (Anthropic)**
1. Go to [console.anthropic.com](https://console.anthropic.com) and sign up.
2. Add a few dollars of credit under **Billing**.
3. Go to **API Keys > Create Key** and copy it. It starts with `sk-ant-`.

**ChatGPT (OpenAI)**
1. Go to [platform.openai.com](https://platform.openai.com) and sign up.
2. Add a few dollars of credit under **Billing**.
3. Go to **API keys > Create new secret key** and copy it. It starts with `sk-`.

A ChatGPT Plus or Claude Pro subscription is **not** the same as an API key. You need the API
key from the developer console.

> **Keep your key secret.** Never paste it into a chat, a screenshot, a video or a GitHub
> commit. Anyone who has it can spend your money. If it leaks, delete it in the console and make
> a new one.

## Step 4. Put your key in the settings file

Make your own settings file from the template:

```
cp .env.example .env
```

(Windows: `copy .env.example .env`)

Open `.env` in any text editor and fill in two lines.

For Claude:
```
AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

For ChatGPT:
```
AI_PROVIDER=openai
OPENAI_API_KEY=sk-your-key-here
```

Save it. `.env` is listed in `.gitignore`, so git will never upload it.

**Want a different model?** Set `AI_MODEL=` to any model name your account can use. Leave it
blank for the default in `ai.py`.

**Running your own model locally?** Any OpenAI-compatible server works (Ollama, LM Studio, and
others). Set `AI_PROVIDER=openai`, `AI_BASE_URL=http://localhost:11434/v1` (your server's
address) and `AI_MODEL=` to the model name. No key is needed for a local server, and it's free.

## Step 5. Run it

```
python3 scanner.py
```

Now the **AI** column has a score and every coin has a verdict:

```
SYMBOL        AGE h       LIQ $    VOL 24h $   AI  VERDICT / WHY
CI              1.1      67,924    1,162,983    6  WATCH: Real buyers and deep pool, but no clear story
```

- **AI** is your AI's score, 0 to 10. The table is sorted best first.
- **WATCH** means your AI thinks it's worth a human look. **SKIP** means it doesn't.
- **AI error** means the call failed. The reason is printed next to it, usually a wrong key or
  no credit.

Every scan is also added to **`scans.csv`** in the same folder. Open it in Excel or Google Sheets
to see your history.

To keep it running and scan every 15 minutes:

```
python3 scanner.py --loop 15
```

Press **Ctrl+C** to stop.

## Step 6. Make it yours

This is the part worth learning. You can change how the scanner thinks without touching code.

**Change what your AI looks for: edit `prompt.txt`.** It's plain English. Tell it to care more
about the coin's story, be stricter, or look for something specific. Save and run again.

**Change which coins reach the AI: edit `.env`.**

| Setting | Default | What it does |
|---|---|---|
| `MIN_LIQUIDITY_USD` | 20000 | Money in the pool. Too little and you can't sell |
| `MIN_VOLUME_24H_USD` | 50000 | Trading in the last 24 hours. Low means nobody cares |
| `MIN_AGE_HOURS` | 1 | Skip coins younger than this. The first hour is the wildest |
| `MAX_AGE_HOURS` | 72 | Skip coins older than this |
| `MAX_RUGCHECK_SCORE` | 5000 | RugCheck's risk score. Higher means riskier |
| `MAX_AI_CALLS_PER_SCAN` | 10 | The most AI calls one scan can make. This caps your cost |

Note: brand-new pump.fun coins that haven't "graduated" yet show **$0 liquidity**, because they
still trade on pump.fun's own curve. The default filters skip them on purpose.

**Change the code:** ask an AI coding assistant (Claude Code, ChatGPT, Cursor) to do it. Good
first projects:
- "Add a column for how many socials the coin has."
- "Send me a Telegram message when a coin scores 8 or higher."
- "Record each coin's price 1 hour after the scan, so I can check whether high scores actually
  went up."

That last one matters most. **A score means nothing until you've checked it against what
happened next.**

After any change, run the tests:

```
python3 -m unittest
```

## What each check does

1. **Find coins:** the newest Solana token profiles on [DexScreener](https://dexscreener.com).
   Free, no key. A profile is something a coin's team pays DexScreener for, so this feed shows
   coins with a marketing budget, not every new coin. Having a profile is not a sign of quality.
2. **Number filters:** liquidity, 24h volume and age, from DexScreener.
3. **Safety check:** [RugCheck](https://rugcheck.xyz)'s report. A coin fails if its risk score is
   too high or it has any "danger" warning, such as the creator still being able to mint more
   coins or freeze yours. **If RugCheck can't be reached, the coin fails.** If we can't check it,
   we don't trust it.
4. **AI rating:** only coins that pass 1-3 go to your AI, so you only pay for coins worth asking
   about. The coin's name and links are written by strangers, so they're sent as data and the
   prompt tells the AI to ignore any instructions hidden in them.

## Cost

- DexScreener and RugCheck: free.
- AI: usually a fraction of a cent to a few cents per coin, depending on the model. Most scans
  rate 0-3 coins. `MAX_AI_CALLS_PER_SCAN` is your ceiling per scan.
- Set a monthly spending limit in your AI console. That's the real safety net.

## Troubleshooting

| You see | Fix |
|---|---|
| `python3: command not found` | Install Python (step 1). On Windows type `python` |
| `ANTHROPIC_API_KEY is not set` | Check `.env` exists in the same folder as `scanner.py` (not `.env.example`) and the key line has no `#` in front |
| `HTTP 401` | The key is wrong or was deleted. Make a new one |
| `HTTP 400 ... credit` or `HTTP 429` | Out of credit or rate-limited. Add credit or scan less often |
| `HTTP 404 ... model` | Your account can't use that model. Set `AI_MODEL=` to one it can |
| `CERTIFICATE_VERIFY_FAILED` | Mac only: Finder > Applications > Python 3.x > double-click **Install Certificates.command**, then run again |
| `AI_BASE_URL uses http:// to another machine` | Your key would travel unencrypted. Use an `https://` address, or remove `OPENAI_API_KEY` for a keyless local server |
| `reply was not valid JSON` | The AI didn't answer in the format `prompt.txt` asks for. Try a different model, or check you didn't remove the last lines of `prompt.txt` |
| `network error` | Your internet or the free API is down. Try again in a minute |
| `0 passed` every time | Normal on quiet days. Run with `-v`, or lower the filters in `.env` |

## Rules worth keeping

- **It's a watchlist, not a buy button.** A high score is a reason to look, not to buy.
- **Test before money.** If you ever build buying on top of this, run it on pretend money for
  weeks first and compare it with buying at random. Most strategies lose.
- **Never put a wallet key in this project.** It doesn't need one.
- **Never launch, pump or promote your own coins with it.**

Not financial advice. Educational project. MIT license, no warranty.
