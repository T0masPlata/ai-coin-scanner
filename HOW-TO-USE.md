# How to use the AI Coin Scanner

This guide takes you from nothing to a working scanner that uses your own AI. It takes about
15 minutes. You don't need to know how to code, but you will type a few commands.

There are two ways to give it a brain. **Option A is the default and the one we recommend.**

- **Option A: use the Claude or ChatGPT plan you already pay for.** No API key, no extra bill.
  The scanner runs as a small tool server (an "MCP server") that your own **Claude Code** or
  **Codex** app talks to. The AI runs in *your* app, under *your* login, on *your* plan. We never
  see, ask for, or store your Claude or ChatGPT login, password, token or cookies, and there is no
  "Login with Claude" button anywhere. [Jump to Option A](#option-a-use-your-claude-or-chatgpt-plan).
- **Option B: an API key.** The original way: the scanner calls the AI company directly with a
  key you pay for per use. [Jump to Option B](#option-b-use-an-api-key).

> **What this does:** every scan, it pulls the newest Solana meme coins that have a DexScreener
> profile, throws out the ones that are too small, too old or look like rugs, and asks your AI to
> score the rest from 0 to 10.
>
> **What this does NOT do:** it never buys, sells or touches a wallet. It is a watchlist tool.
> Not financial advice. Most new meme coins go to zero.

---

## Step 1. Install Python

You need Python 3.10 or newer. Option B uses no extra packages; Option A installs one (the
official MCP SDK) in step A1.

Check if you already have it. Open a terminal (Mac: the **Terminal** app; Windows: **PowerShell**)
and type:

```
python3 --version
```

If you see `Python 3.10` or higher, skip ahead. If not, download it from
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

---

## Option A: use your Claude or ChatGPT plan

You need **one** of these, signed in with your normal subscription:

- **Claude Code** (Claude Pro/Max): install from [claude.com/claude-code](https://claude.com/claude-code), then run `claude` once and sign in.
- **Codex CLI** (ChatGPT Plus/Pro): `npm install -g @openai/codex`, then `codex login` and pick
  **Sign in with ChatGPT**.

### A1. Install the scanner's tool server

In the `ai-coin-scanner` folder from step 2:

```
python3 -m venv .venv
.venv/bin/pip install -e .
```

(Windows: `.venv\Scripts\pip install -e .`, and use `.venv\Scripts\python` below.)

This installs one extra package, the official MCP SDK. Check it starts:

```
.venv/bin/python -m vostuk_scanner --version
```

### A2. Connect it to your AI app

Use the **full path** to the folder (run `pwd` inside it to see it). Below it is
`/path/to/ai-coin-scanner`; replace that with yours.

**Claude Code:**

```
claude mcp add vostuk -- /path/to/ai-coin-scanner/.venv/bin/python -m vostuk_scanner
```

Check with `claude mcp list`: you should see `vostuk ... Connected`.

**Codex:** open `~/.codex/config.toml` (create it if missing) and add:

```toml
[mcp_servers.vostuk]
command = "/path/to/ai-coin-scanner/.venv/bin/python"
args = ["-m", "vostuk_scanner"]
# Lets Codex call the scanner without asking each time. Leave it out and Codex will ask
# you to approve the tool calls instead. In `codex exec` (non-interactive) it is REQUIRED,
# otherwise every call is refused with "requires approval, but approval policy is never".
default_tools_approval_mode = "approve"

[mcp_servers.vostuk.env]
# only needed for step A4 (uploading to your dashboard)
VOSTUK_UPLOAD_TOKEN_FILE = "/home/you/.config/vostuk/credentials.toml"
```

You do **not** need to turn off Codex's sandbox or give it network access. We tested this on
Codex 0.156.0: the scanner's tool server runs outside the sandbox and reaches DexScreener and
RugCheck by itself, even under `workspace-write` (where Codex's own shell commands have no
network). If a future Codex version ever reports "network unavailable" from `scan_candidates`, add
this to `config.toml`, and do not disable the sandbox entirely:

```toml
[sandbox_workspace_write]
network_access = true
```

### A3. Ask your AI to scan

Open Claude Code or Codex in any folder and type:

```
Use the vostuk scanner tools to scan and score new Solana coins. Follow the rubric's sequence exactly. At the end, show me a table of what you scored.
```

Non-interactive works too: `claude -p "..."` or `codex exec "..."` with the same text.

What happens: your AI calls `scan_candidates` (newest coins from DexScreener, filtered), then
`rugcheck` for each one, reads the scoring rubric with `get_rubric`, and calls `record_score` for
each coin. The scanner **checks every score**: it must be a whole number 0-10, WATCH only for 7 or
more, every reason must name the number it is based on, a coin whose freeze authority is still on
can score at most 2, and a coin with no RugCheck lookup is refused. A bad score comes back with an
error telling the AI how to fix it. The scanner also works out its own simple score from the same
numbers, and any AI score more than 4 points away from it is flagged "divergent".

Results are saved on your computer in `~/.local/share/vostuk/scanner.db` (SQLite). Change it
with `VOSTUK_SCANNER_DB=/some/file.db`.

Tip: add "Use max_candidates=5" to the prompt for a quicker, cheaper scan. Each scan uses some of
your plan's usage, the same as any other request you make in that app.

### A4 (optional). Send results to your dashboard

Your dashboard at **dashboard.vostuk.com** shows your scans, coin by coin. It is invite-only
for now.

1. Sign in to the dashboard and open **Upload tokens > Create token**. Copy it; it is shown once
   and starts with `vsk_`.
2. Save it in a file only you can read:

   ```
   mkdir -p ~/.config/vostuk
   printf 'upload_token = "%s"\n' 'vsk_PASTE_IT_HERE' > ~/.config/vostuk/credentials.toml
   chmod 600 ~/.config/vostuk/credentials.toml
   ```

   The scanner refuses to read the file if other users can read it. (Or set the
   `VOSTUK_UPLOAD_TOKEN` environment variable instead.)
3. Ask your AI: `...and when you're done, call sync_results for the scan.`

**Never paste the token into a chat, a prompt, a screenshot or a git commit.** The AI never needs
to see it: the scanner reads it from the file. If it leaks, revoke it on the dashboard and make a
new one.

What is uploaded: the scan id and time, scanner and rubric version, the model name your AI reported,
and for each scored coin its address, symbol, pair, the numbers, the RugCheck summary, score,
verdict, reasons and divergent flag. It is built from the local database only, so your prompts,
chat, files, paths, environment and keys cannot be in it. Re-sending the same scan does not
create a duplicate. The dashboard never connects to your computer; it only receives uploads.

---

## Option B: use an API key

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
key from the developer console. (To use your subscription instead, see Option A.)

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
| A: `vostuk` not in `claude mcp list`, or "Failed to connect" | Use the full path to `.venv/bin/python` in `claude mcp add`, and run step A1 again |
| A: Codex says "requires approval, but approval policy is never" | Add `default_tools_approval_mode = "approve"` under `[mcp_servers.vostuk]` (step A2) |
| A: `record_score rejected: ...` in the AI's output | Normal: the scanner refused a bad score and told the AI why. It usually fixes it on its own |
| A: `no rugcheck row` | The AI tried to score a coin before checking it. It should call `rugcheck` and retry |
| A: `sync_results` says `no upload token` | Do step A4. Check the file is `chmod 600` |
| A: `dashboard answered HTTP 401` | The upload token was revoked or mistyped. Make a new one on the dashboard |
| `0 passed` every time | Normal on quiet days. Run with `-v`, or lower the filters in `.env` |

## Rules worth keeping

- **It's a watchlist, not a buy button.** A high score is a reason to look, not to buy.
- **Test before money.** If you ever build buying on top of this, run it on pretend money for
  weeks first and compare it with buying at random. Most strategies lose.
- **Never put a wallet key in this project.** It doesn't need one.
- **Never launch, pump or promote your own coins with it.**

Not financial advice. Educational project. MIT license, no warranty.
