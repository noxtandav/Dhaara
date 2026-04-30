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

# Production: keep it alive with PM2
npm install -g pm2
cp ecosystem.config.js.example ecosystem.config.js
pm2 start ecosystem.config.js --name dhaara
pm2 save && pm2 startup
```

Message your bot. That's it.

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
- **Typed tool interface** — the agent can only call a small, audited set of tools: `record_entry`, `read_today`, `read_day`, `read_telos`, `list_entries`, `edit_entry`, `delete_entry`. Every path is resolved inside `data_dir`; traversal attempts are rejected.
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

## Exporting your data

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

# Last month
python scripts/dashboard.py --since 4w
```

Empty days/sections are gracefully omitted, so the report is always tight regardless of how much you journaled. Pure markdown — paste anywhere, archive as a long-term log, or pipe into a Telegram bot.

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

You get one section per category in WORK / PERSONAL / HABITS / FINANCE order, entries sorted by time, finance subtotal in the section header, and a "Moods today" line at the bottom. Empty days render a clean "Nothing recorded yet" message.

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
```

Matches are highlighted in bold red on a TTY (use `--color always|never` to override). Exit code is 0 on hits, 1 on no matches — handy for shell scripting.

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
- **Phase 2** 🚧 — RAG retrieval ("what did I write about dhaara last month?"), entry editing, daily/weekly summaries
- **Phase 3** 🔭 — Mood trends, habit dashboards, growth analysis, cross-agent workflows in the wider PAI ecosystem

---

## Contributing

Contributions are very welcome. Open an issue first for anything non-trivial so we can align on direction. Good first areas:

- Adding new AI providers (Anthropic direct, Gemini direct, local Ollama)
- Phase 2 features: RAG retrieval over past entries, daily / weekly summaries
- Better expense parsing across currencies
- More tests (see below)

### Running tests

```bash
pip install -r requirements-dev.txt
pytest
```

The suite lives in `tests/` and covers the journal formatter, the export script, and the stats roll-up. Pure unit tests, no fixtures or network — 80+ tests in under a second. CI runs them on every push and PR against Python 3.11, 3.12, and 3.13 (see `.github/workflows/test.yml`).

---

## License

MIT — see `LICENSE`. Use it, fork it, make it yours.

---

*Built in India. Named for the quiet stream of thoughts we all carry.*
