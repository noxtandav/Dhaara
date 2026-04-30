# Dhaara

[![Tests](https://github.com/noxtandav/Dhaara/actions/workflows/test.yml/badge.svg)](https://github.com/noxtandav/Dhaara/actions/workflows/test.yml)

> *Dhaara* (धारा) — a stream, a current, a flow.

**Your personal journal, as a conversation.** Talk to it on Telegram — by voice or text, in English or any Indian language — and Dhaara quietly turns your thoughts into a well-organised, searchable archive of your life. No apps to open. No forms to fill. Just talk.

Dhaara is the first agent in the **PAI (Personal AI)** ecosystem — a set of agents that share a common data store and, over time, learn to help you across work, health, finances, and growth.

---

## Why Dhaara?

Most journaling apps ask you to sit down, open a page, and write. Most of us don't. Life happens in the gaps — in the auto ride, between meetings, while making chai. Dhaara lives in the one app you already check a hundred times a day: **Telegram**.

- 🎙️ **Voice-first.** Ramble in Hindi, Tamil, Marathi, English — or a mix. Dhaara understands.
- 🧠 **Agentic, not a form.** It classifies each entry, extracts mood and a free-form subcategory tag, and can edit or delete past entries when you ask.
- 📒 **One file per day.** Every day is a single markdown file with four sections — **WORK**, **PERSONAL**, **HABITS**, **FINANCE** — and timestamped bullet entries inside each.
- 🏷️ **Inline tags for free.** Every bullet carries its own `[time] [CATEGORY/subcategory]` prefix and optional `*(mood: ...)*`, so each line is a self-contained chunk that's perfect for RAG later.
- 💰 **Automatic expense capture.** "Spent 30 on milk, 150 on auto" lands as entries under `FINANCE/groceries` and `FINANCE/transport`.
- 🎯 **TELOS-aware.** You give it your goals and priorities in `_telos/` and the agent reads entries in that context.
- 🗂️ **Your data, your disk.** Plain markdown files. No cloud lock-in. No database. `grep` just works.
- 🔓 **BYO-model.** Runs on **AWS Bedrock** *or* **OpenRouter** — pick Claude, Nova, Mistral, Gemini, Llama, whatever you like.
- 👤 **Single-user by design.** The bot answers to exactly one Telegram ID — yours.
- 📊 **Analytics out of the box.** Streak nudges, activity heatmaps, mood timelines, weekly summaries, search with context, and a combined dashboard — all reading the same plain markdown. See [§ Tools](#tools).

---

## How it feels

```
you:   spent 30 on milk, 20 on cold drink, 150 on auto today
bot:   Recorded to [FINANCE].
       (three bullets added under FINANCE/groceries and FINANCE/transport)

you:   [voice note in Hindi] aaj kaafi thaka hua hoon, kaam pe focus nahi ho paa raha
bot:   Recorded to [PERSONAL]. (mood: tired)

you:   worked on dhaara for 2 hrs, phase 1 is nearly done
bot:   Recorded to [WORK].

you:   what did I eat today?
bot:   L12: - [1:30 PM] [FINANCE/food] Spent ₹150 on lunch
       L18: - [8:10 PM] [FINANCE/food] Ordered dinner from Swiggy ₹420

you:   delete the swiggy one
bot:   Deleted: - [8:10 PM] [FINANCE/food] Ordered dinner from Swiggy ₹420

you:   how am I tracking against my work TELOS this month?
bot:   ## Stats
       - 64 entries across 10 days (33% active)
       - Top finance: ₹60k investments, ₹55k EMI, ₹11k subscriptions
       - 9 distinct moods, satisfied (2) and concerned (2) lead

       ## TELOS Alignment
       ✓ "Ship Dhaara Phase 1" — Apr 16 "Found critical bugs and fixed
         those today" directly supports this
       ⚠ "Reduce infra bill 20%" — no infra entries; ₹16k subscriptions
         trending up instead

       ## Recommendations
       - The Hitachi/Clever vendor change shifts your runway. Refine
         the income-replacement plan in TELOS.
```

Every entry is appended to today's single markdown file under the right section. Nothing hidden. Nothing proprietary. Every bullet is timestamped and tagged inline, so the file itself is both a journal and an index.

---

## Quick start

You need:

- Python 3.11+
- A **Telegram bot token** — 2 minutes via [@BotFather](https://t.me/BotFather)
- Your **Telegram user ID** — from [@userinfobot](https://t.me/userinfobot)
- A **Sarvam AI API key** — [sarvam.ai](https://sarvam.ai) (for voice + Indian-language translation; free tier works)
- **One of:**
  - An **OpenRouter API key** — [openrouter.ai/keys](https://openrouter.ai/keys) *(easiest path — credit card, one model ID, done)*
  - An **AWS account with Bedrock access** *(if you prefer to run on your own cloud)*

### 1. Clone and install

```bash
git clone https://github.com/noxtandav/Dhaara.git
cd Dhaara

python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cp config.example.yaml config.yaml
```

Open `config.yaml` and fill in your values. The file is gitignored — it never leaves your machine.

**Minimal OpenRouter setup:**

```yaml
telegram:
  bot_token: "123456:ABC..."
  authorized_user_id: 123456789

data_dir: "~/PAI/DhaaraData"
timezone: "Asia/Kolkata"

ai:
  provider: "openrouter"

openrouter:
  model: "anthropic/claude-sonnet-4.5"
  api_key: "sk-or-v1-..."

sarvam:
  api_key: "..."
```

**Or use Bedrock:**

```yaml
ai:
  provider: "bedrock"

bedrock:
  model_id: "us.amazon.nova-pro-v1:0"
  region: "us-east-1"
  aws_profile: "default"
```

### 3. Verify your config (optional but recommended)

```bash
python scripts/check_config.py
```

A static linter that catches the things that bite first-time users — leftover placeholders from `config.example.yaml`, missing keys for the chosen AI provider, invalid timezones, oddly-shaped credentials. Exits non-zero on errors so you can wire it into a pre-deploy step. Add `-f json` for machine-readable output.

### 4. Initialize the data layout

```bash
python scripts/init.py            # creates data_dir/, journal/, _telos/ + seeds example TELOS files
python scripts/init.py --dry-run  # see what would happen first
```

Idempotent — re-running tells you what was already there and never overwrites your TELOS files. Pairs naturally with `check_config.py`: the linter validates your config, `init.py` realizes the file system that config points at.

### 5. Run

```bash
# Foreground (for testing)
python -m src.main
```

Message your bot — that's it. For production deployment with PM2 and the auto-scheduled review jobs, see [§ Running with PM2](#running-with-pm2) below.

---

## Running with PM2

For long-running deployments, dhaara ships with a [PM2](https://pm2.keymetrics.io/) manifest that registers **four apps in one go**: the always-on bot plus three scheduled review jobs.

| App | What it does | Schedule |
|---|---|---|
| `dhaara` | The Telegram bot | Always on, auto-restarts on failure |
| `dhaara-weekly` | Markdown weekly review → `<data_dir>/weekly/YYYY-Www.md` | Sundays 21:07 local |
| `dhaara-dashboard` | Rolling 7-day combined dashboard → `<data_dir>/dashboards/YYYY-MM-DD.md` | Daily 23:53 local |
| `dhaara-streak` | Desktop notification if your streak broke (macOS `osascript`) | Daily 19:37 local |

Schedules use off-the-round minutes (`:07`, `:53`, `:37`) to dodge the fleet-wide thundering herd of `0 21` / `0 0` / `0 19`.

### One-time setup

```bash
npm install -g pm2
cp ecosystem.config.js.example ecosystem.config.js
```

Open `ecosystem.config.js` and edit the two paths near the top:

- `dataDir` — should match your `config.yaml`'s `data_dir`
- `logsDir` — where PM2 writes process logs (default `./logs`, gitignored)

### Start and persist

```bash
pm2 start ecosystem.config.js   # registers all four apps
pm2 save                         # snapshot the process list
pm2 startup                      # prints a sudo line — run it once for boot survival
```

After `pm2 startup`, dhaara survives reboots. Any future `pm2 stop` / `pm2 delete` requires another `pm2 save` to persist.

### Operating it

```bash
pm2 list                            # what's registered, what's running
pm2 logs dhaara                     # tail the bot's output
pm2 logs dhaara-weekly --lines 50   # tail any specific app
pm2 restart dhaara                  # bounce the bot after a code change
pm2 trigger dhaara-dashboard        # force a scheduled job to fire NOW (testing)
pm2 stop dhaara-streak              # disable an app — then `pm2 save`
pm2 delete dhaara-weekly            # unregister entirely — then `pm2 save`
```

### Caveats and troubleshooting

- **`stopped` is the normal state for cron apps between fires.** They wake up on schedule, run once, and go back to sleep. Only `dhaara` should show `online` 24/7.
- **PM2 uses local OS time.** Match the timezone in your `config.yaml`. If the OS is UTC and the config says `Asia/Kolkata`, schedules above fire 5h30m later than you expect.
- **`autorestart: false` is mandatory for cron jobs.** Without it, PM2 immediately re-runs the script on exit and "every Sunday 21:07" becomes "as fast as Python can finish." The shipped manifest already sets this correctly.
- **Bot silent on Telegram?** `pm2 logs dhaara` — common causes: typo in token, two machines polling the same bot (`409 Conflict: terminated by other getUpdates request`), or model rate-limiting.
- **macOS notifications not appearing?** Confirm `osascript` (Script Editor) is allowed to send notifications under *System Settings → Notifications*.

### Linux users

The streak nudge uses macOS-only `osascript`. In `ecosystem.config.js`, swap the `osascript` line for:

```js
'notify-send "Dhaara" "$MSG"'
```

(requires `libnotify`). Or drop the app entirely with `pm2 delete dhaara-streak && pm2 save`.

---

## Choosing a model

Dhaara needs a model that supports **system prompts + tool use + multi-turn chat**. Anything modern from Anthropic, OpenAI, Google, Mistral, or Amazon Nova qualifies.

### OpenRouter (recommended for getting started)

Set any model ID from [openrouter.ai/models](https://openrouter.ai/models) that supports tool calling. Examples:

| Model | Strength |
|---|---|
| `anthropic/claude-sonnet-4.5` | Best quality, best reasoning |
| `anthropic/claude-haiku-4.5` | Fast and cheap |
| `openai/gpt-4o-mini` | Cheap general-purpose |
| `google/gemini-2.5-flash` | Very cheap, very fast |
| `mistralai/mistral-large` | EU-hosted option |

### AWS Bedrock

| Model ID | ~Price (in/out per 1M) | Notes |
|---|---|---|
| `us.amazon.nova-micro-v1:0` | $0.04 / $0.14 | Cheapest; text only |
| `us.amazon.nova-lite-v1:0` | $0.06 / $0.24 | Cheap + multimodal |
| `us.amazon.nova-pro-v1:0` | $0.80 / $3.20 | Good default |
| `global.anthropic.claude-haiku-4-5-20251001-v1:0` | $1 / $5 | Fast Anthropic |
| `global.anthropic.claude-sonnet-4-6` | $3 / $15 | Best quality |

> Newer Anthropic models on Bedrock require a cross-region inference profile prefix (`global.`, `us.`, etc.). Models without tool-use support (`titan-*`, `llama2-*`, `mistral-7b-*`, etc.) will not work.

**Bedrock IAM needs:**

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream",
      "bedrock:ListFoundationModels",
      "bedrock:GetFoundationModelAvailability"
    ],
    "Resource": "*"
  }]
}
```

Also enable your model in **AWS Console → Bedrock → Model access**.

---

## How your data is stored

Journal data lives under `data_dir` (default `~/PAI/DhaaraData/`). TELOS context lives alongside it under `_telos/` (by default `<data_dir>/../_telos`) so every future PAI agent can share the same personal context.

```
~/PAI/
├── _telos/                     # shared across all PAI agents
│   ├── work.md                 # you edit these
│   └── personal.md
└── DhaaraData/
    └── journal/
        ├── 2026-04-14.md
        ├── 2026-04-15.md
        └── 2026-04-16.md
```

**One file per day — that's it.** Inside each daily file, four fixed sections hold everything:

```markdown
# 2026-04-15 Journal

## [WORK]
- [10:32 AM] [WORK/meetings] Had standup with the team
- [2:15 PM] [WORK/coding] Finished the API refactor  *(mood: satisfied)*

## [PERSONAL]
- [9:00 AM] [PERSONAL/family] Had breakfast with family  *(mood: happy)*
- [11:00 PM] [PERSONAL/health] Couldn't sleep, felt anxious  *(mood: anxious)*

## [HABITS]
- [7:00 AM] [HABITS/exercise] Gym: 45 mins
- [10:00 PM] [HABITS/sleep] Sleep: 7 hours

## [FINANCE]
- [1:30 PM] [FINANCE/food] Spent ₹150 on lunch
- [6:00 PM] [FINANCE/groceries] Bought vegetables ₹300
- [8:00 PM] [FINANCE/rent] Paid rent ₹15,000
```

- **Four fixed categories**: `WORK`, `PERSONAL`, `HABITS`, `FINANCE`. The agent picks exactly one for each entry.
- **Free-form subcategories**: lowercase tags the agent invents as needed — `meetings`, `coding`, `groceries`, `rent`, `hiring`, `gifts`… whatever fits.
- **Inline metadata per bullet**: `[time]`, `[CATEGORY/subcategory]`, and optional `*(mood: ...)*`. Each line stands on its own — great for future RAG.
- **Safe by construction**: the journal store resolves every path inside `data_dir` and rejects anything that tries to escape.
- **Concurrent-safe**: file-locked writes via `filelock`, so the agent can append, edit, and delete entries without races.

---

## TELOS — give the agent context

TELOS is a personal-context framework from Daniel Miessler. Drop your work and life priorities into `_telos/work.md` and `_telos/personal.md` (by default in `<data_dir>/../_telos/`, shared across all PAI agents), and Dhaara will reason about your entries in that light. Example:

```markdown
# Work TELOS
- Shipping Dhaara Phase 1 by end of April
- Learning Rust on the side
- Quarterly OKR: reduce infra bill 20%
```

The agent re-reads these on every turn, so edit freely — no restart needed.

### Asking for TELOS insights

Ask the bot for reflection in plain English — *"how am I tracking against my work goals this month?"* / *"is my spending aligned with my TELOS?"* / *"what should I course-correct on?"* — and the agent calls a dedicated `telos_insights` tool that pulls the last N days of journal entries (capped at 90), bundles them with your TELOS files, and returns a structured response with three sections:

- **Stats** — concrete numbers: entry counts, finance totals, habit streaks, mood patterns.
- **TELOS Alignment** — which entries support each TELOS goal, which contradict, which goals see no action at all.
- **Recommendations** — actionable course corrections based on the gap.

The tool also computes a **data-quality flag** before responding. If you have fewer than 3 days of entries in the requested window, the response leads with `⚠ INSUFFICIENT DATA`. If coverage is below 30%, it leads with `⚠ LIMITED DATA`. The agent is instructed to relay these warnings prominently rather than glossing over them — sparse journaling produces sparse insights, and pretending otherwise is worse than admitting it.

The optional `telos_dir:` config knob lets you point at a custom location (default is `<data_dir>/../_telos/`, shared across PAI agents).

---

## Architecture

```
Telegram  ──►  Sarvam AI  ──►  AI Agent  ──►  Journal Store
(voice/text)   (STT + lang     (Bedrock or     (sandboxed
               detect +         OpenRouter,     markdown
               translation)     tool-use loop)  read/write)
                   ▲                                │
                   └──── reply translated back ─────┘
```

Key design choices:

- **Provider abstraction** — `src/ai/provider.py` lets you plug in new AI backends without touching the agent loop.
- **Typed tool interface** — the agent can only call a small, audited set of tools: `record_entry`, `read_today`, `read_day`, `read_telos`, `telos_insights`, `list_entries`, `edit_entry`, `delete_entry`. Every path is resolved inside `data_dir`; traversal attempts are rejected.
- **Local timezone** — timestamps honour whatever IANA zone you set in `config.yaml`.
- **Stateless per conversation** — `/clear` resets context; your daily markdown files are the long-term memory.

---

## Commands

| Command | Does |
|---|---|
| `/start` | Intro + health check |
| `/clear` | Reset conversation context (your journal data is untouched) |

Everything else is an entry or a conversation.

---

## Tools

Eleven standalone CLI scripts ship in `scripts/` for setup, daily nudges, reflection, exploration, and export. They all read the same plain-markdown journal — no separate database, no schema migrations. Pure stdlib at runtime (PyYAML is optional, only needed for `data_dir` auto-discovery from `config.yaml`).

**Setup** ([§ Quick start](#quick-start) walks you through these on first run)
- `init.py` — create `data_dir/`, `journal/`, `_telos/` + seed example TELOS files
- `check_config.py` — lint `config.yaml` (placeholders, missing keys, invalid timezones)

**Daily nudges**
- [`today.py`](#today) — single-day breakdown with finance subtotal and last-entry hint
- [`streak.py`](#streak-nudge) — current streak, designed to live in your shell prompt

**Reflection**
- [`weekly_summary.py`](#weekly-summary) — markdown weekly digest with week-over-week deltas
- [`dashboard.py`](#combined-dashboard) — combined "everything in one document" digest
- [`activity_heatmap.py`](#activity-calendar) — GitHub-contribution-style calendar
- [`mood_timeline.py`](#mood-timeline) — per-day mood heatmap
- [`stats.py`](#quick-stats) — period stats roll-up

**Exploration & export**
- [`search.py`](#search) — structured search with category/mood/date filters and surrounding context
- [`export_journal.py`](#export-and-pivots) — CSV/JSON export with optional pivot aggregation

All scripts share the same flag conventions where applicable: `--data-dir`, `--from / --to / --since 7d|4w|6m`, `--category`, `-f text|markdown|json`, `-o file|-`. Each has `--help`.

### Export and pivots

Every entry already lives as plain markdown, so `grep` works. But if you want a structured view for spreadsheets or pandas, there's a standalone exporter:

```bash
# All entries to CSV (stdout)
python scripts/export_journal.py

# Last 30 days, finance only, to a file
python scripts/export_journal.py --since 30d --category FINANCE -o finance.csv

# JSON for a specific date range
python scripts/export_journal.py --from 2026-04-01 --to 2026-04-30 -f json
```

It parses every `[time]`, `[CATEGORY/subcategory]`, mood, and text into one row per bullet — no extra dependencies beyond the standard library (PyYAML is used only if you let it auto-discover `data_dir` from `config.yaml`).

For pivots instead of raw rows, add `--group-by`:

```bash
# How is my finance spending distributed across subcategories?
python scripts/export_journal.py --category FINANCE --group-by subcategory

# Cross-tab category × subcategory across the whole journal
python scripts/export_journal.py --group-by category,subcategory

# Mood frequency + first/last date you tagged each one
python scripts/export_journal.py --group-by mood -f json
```

Each pivot row carries the grouping columns plus `count`, `sum_amount` (₹ totals for FINANCE rows; empty otherwise), `first_date`, and `last_date`. Rows sort by spending desc when any group has amounts, else by count desc. Valid keys: `category`, `subcategory`, `mood`, `date` (any combination, comma-separated).

### Quick stats

For a roll-up instead of raw rows, there's `scripts/stats.py`. It reuses the same parser and prints per-category counts, finance totals (with subcategory breakdown + top expenses), habit streaks, and mood distribution:

```bash
# Last 30 days, human-readable report
python scripts/stats.py --since 30d

# JSON for piping into a dashboard
python scripts/stats.py --since 30d -f json

# Habits-only view
python scripts/stats.py --category HABITS
```

Currency parsing is best-effort — it understands `₹`, `Rs`, `$`, and bare numbers in FINANCE entries, plus `k`, `lakh`/`lac`, and `cr`/`crore` multipliers.

### Combined dashboard

For an end-of-week or end-of-month review, `scripts/dashboard.py` weaves every visualization in the toolset into a single Markdown document — streak, snapshot, period summary, activity calendar, finance highlights, habits, mood timeline, and notable moments:

```bash
# Last 7 days, stdout
python scripts/dashboard.py

# Specific ISO week to a file
python scripts/dashboard.py --from 2026-04-13 --to 2026-04-19 \
    -o ~/PAI/DhaaraData/dashboards/2026-W16.md

# With week-over-week deltas
python scripts/dashboard.py --since 7d --compare-prev

# Last month
python scripts/dashboard.py --since 4w
```

Empty days/sections are gracefully omitted, so the report is always tight regardless of how much you journaled. Pure markdown — paste anywhere, archive as a long-term log, or pipe into a Telegram bot. With `--compare-prev`, a "Compared to the previous week" section lands between the period summary and the activity calendar, surfacing entry-count, spending, mood-drift, and top finance shifts vs. the same-length window before.

### Today

The "what have I journaled this morning?" glance — a focused, single-day breakdown:

```bash
# What's in today's file?
python scripts/today.py

# Yesterday's recap
python scripts/today.py --date 2026-04-29

# Markdown for a daily review note
python scripts/today.py -f markdown
```

You get one section per category in WORK / PERSONAL / HABITS / FINANCE order, entries sorted by time, finance subtotal in the section header, and a "Moods today" line at the bottom.

Empty days render a "Nothing recorded yet" message that also surfaces the gap since your previous entry — `Last entry: 13 days ago (2026-04-17 12:04 PM)` — so the report turns into a nudge instead of a dead end. If there are no entries anywhere yet, it says so explicitly.

### Streak nudge

A glanceable one-liner showing your current streak — designed to live in your shell prompt or status bar:

```bash
$ python scripts/streak.py
🔥 5-day streak

$ python scripts/streak.py --quiet         # just the number, for shell prompts
5

$ python scripts/streak.py --text          # full breakdown
🔥 Current streak: 5 days
   Longest streak: 12 days
   Last entry:     2026-04-30 (today)
   Total entries:  234 across 87 days
```

A habit you can see is a habit you keep — drop the short or `--quiet` form into your `PROMPT_COMMAND`, starship config, or tmux status bar, and you'll get a daily nudge for free.

### Activity calendar

GitHub-contribution-graph-style heatmap that answers "am I journaling consistently?" — rows are weeks, columns are weekdays, cells are bucketed entry counts (`▁▃▅▆▇`). The header line surfaces longest streak, current streak, and best day at a glance.

```bash
# Last 12 weeks (default)
python scripts/activity_heatmap.py

# Last year
python scripts/activity_heatmap.py --since 1y

# Markdown table for embedding in a journal note
python scripts/activity_heatmap.py --since 4w -f markdown
```

### Mood timeline

The agent already tags entries with optional moods. `scripts/mood_timeline.py` adds the missing time dimension — when did "anxious" appear? Was it a one-day spike or a sustained pattern?

```bash
# Last 30 days, ANSI heatmap (one row per mood, one column per day)
python scripts/mood_timeline.py

# Specific range, markdown for embedding in a journal note
python scripts/mood_timeline.py --from 2026-04-01 --to 2026-04-30 -f markdown

# JSON for a notebook / dashboard
python scripts/mood_timeline.py --since 6m -f json
```

Heatmap cells use bar characters (`▁▂▃▄▅▆▇█`) so density reads at a glance even on terminals without color support.

### Search

Plain markdown is `grep`-able already, but `scripts/search.py` understands the entry structure — filter by category, mood, date range, regex, and case-sensitivity in one go:

```bash
# Substring search across the last 30 days
python scripts/search.py dhaara --since 30d

# All "anxious" moments in April
python scripts/search.py --mood anxious --from 2026-04-01 --to 2026-04-30

# Case-sensitive regex over WORK entries only
python scripts/search.py "API\b" --regex --match-case --category WORK

# JSON for piping
python scripts/search.py "claude" -f json

# Surrounding context: 2 entries before and after each hit
python scripts/search.py Hitachi --context 2
```

Matches are highlighted in bold red on a TTY (use `--color always|never` to override). Exit code is 0 on hits, 1 on no matches — handy for shell scripting.

With `--context N` (or `-C N`), each match shows the N entries before and after it in chronological order. Adjacent windows merge automatically; non-adjacent blocks are separated by `--`. Actual matches are marked with `▸ ` so you can spot them within the context. JSON output shifts to a list-of-blocks shape with an `is_match` flag per entry.

### Weekly summary

For a shareable markdown digest of a single week — entry counts, finance highlights, habit streaks, mood distribution, and the entries that carried a mood — there's `scripts/weekly_summary.py`:

```bash
# Last 7 days
python scripts/weekly_summary.py

# Specific ISO week (Mon-Sun)
python scripts/weekly_summary.py --week 2026-W17

# Add week-over-week deltas (entries, spending, mood drift, top finance shifts)
python scripts/weekly_summary.py --week 2026-W17 --compare-prev

# Save next to your daily files
python scripts/weekly_summary.py --week 2026-W17 -o ~/PAI/DhaaraData/weekly/2026-W17.md
```

Output is plain Markdown — paste it into your journal repo, share it with a friend, or schedule it as a Sunday-night cron. With `--compare-prev`, you also get a "Compared to the previous week" section with concrete numbers like `Entries: 18 → 31 (+13, +72%)` and `food: ₹200 → ₹500 (+₹300)`.

---

## Roadmap

- **Phase 1** ✅ — Journaling, voice, multilingual, expense extraction, category classification, edit/delete by line number
- **Phase 2** ✅ — Lexical search with date/category/mood filters and `±N` context (`scripts/search.py`); daily and weekly markdown summaries (`today.py`, `weekly_summary.py`); CSV/JSON export with pivot aggregation (`export_journal.py`)
- **Phase 3** ✅ (mostly) — Mood timelines (`mood_timeline.py`), habit dashboards (`activity_heatmap.py`, `dashboard.py`), growth analysis (`stats.py`, week-over-week deltas)
- **Phase 4** 🚧 — Vector / RAG retrieval ("what did I write *semantically about* career anxiety last quarter?"); cross-agent workflows in the wider PAI ecosystem

---

## Contributing

Contributions are very welcome. Open an issue first for anything non-trivial so we can align on direction. Good first areas:

- New AI providers (Anthropic direct, Gemini direct, local Ollama via `src/ai/provider.py`)
- Phase 4 features: vector retrieval over past entries (the lexical foundation in `search.py` is ready to layer over)
- Better expense parsing across currencies (the `extract_amount` regex in `scripts/stats.py` is the obvious starting point — currently handles `₹`, `Rs`, `$`, plus `k` / `lakh` / `lac` / `cr` / `crore` multipliers)
- More tests for the agent loop (`src/ai/graph.py`) — the helper modules are well-covered but the LangGraph state machine is not directly exercised yet
- Linux notification path for `dhaara-streak` (currently macOS-only via `osascript`)

### Running tests

```bash
pip install -r requirements-dev.txt
pytest
```

The suite covers the journal formatter and all eleven CLI scripts — 437 unit tests in ~0.25s. Pure stdlib fixtures, no network. CI runs them on every push and PR against Python 3.11, 3.12, and 3.13 (see `.github/workflows/test.yml`).

---

## License

MIT — see `LICENSE`. Use it, fork it, make it yours.

---

*Built in India. Named for the quiet stream of thoughts we all carry.*
