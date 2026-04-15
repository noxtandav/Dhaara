# Dhaara

> *Dhaara* (धारा) — a stream, a current, a flow.

**Your personal journal, as a conversation.** Talk to it on Telegram — by voice or text, in English or any Indian language — and Dhaara quietly turns your thoughts into a well-organised, searchable archive of your life. No apps to open. No forms to fill. Just talk.

Dhaara is the first agent in the **PAI (Personal AI)** ecosystem — a set of agents that share a common data store and, over time, learn to help you across work, health, finances, and growth.

---

## Why Dhaara?

Most journaling apps ask you to sit down, open a page, and write. Most of us don't. Life happens in the gaps — in the auto ride, between meetings, while making chai. Dhaara lives in the one app you already check a hundred times a day: **Telegram**.

- 🎙️ **Voice-first.** Ramble in Hindi, Tamil, Marathi, English — or a mix. Dhaara understands.
- 🧠 **Agentic, not a form.** It decides where your entry belongs, extracts mood, tags, and expenses, and asks smart questions when unsure.
- 📂 **Silo-based organisation.** Work, Personal, Habits, Finance, Health… auto-routed. New silos suggested when your life grows a new branch.
- 💰 **Automatic expense ledger.** "Spent 30 on milk, 150 on auto" becomes a structured table you can query.
- 🎯 **TELOS-aware.** You give it your goals and priorities; it reads entries in that context.
- 🗂️ **Your data, your disk.** Plain markdown files. No cloud lock-in. No database. `grep` just works.
- 🔓 **BYO-model.** Runs on **AWS Bedrock** *or* **OpenRouter** — pick Claude, Nova, Mistral, Gemini, Llama, whatever you like.
- 👤 **Single-user by design.** The bot answers to exactly one Telegram ID — yours.

---

## How it feels

```
you:   spent 30 on milk, 20 on cold drink, 150 on auto today
bot:   logged in Finance · ₹200 total · tagged: groceries, transport

you:   [voice note in Hindi] aaj kaafi thaka hua hoon, kaam pe focus nahi ho paa raha
bot:   noted in Personal · mood: low · would you like to capture anything about what's draining you?

you:   worked on dhaara for 2 hrs, phase 1 is nearly done 🎉
bot:   logged in Work · tagged: dhaara, milestone

you:   /summary today
bot:   [tomorrow, after Phase 2]
```

Every entry lands as a timestamped markdown section in one file per silo per day. Nothing hidden. Nothing proprietary.

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

### 3. Run

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

Everything lives under `data_dir` (default `~/PAI/DhaaraData/`) — deliberately outside the repo so future PAI agents can share it.

```
DhaaraData/
├── _config/
│   └── silos.yaml          # silo definitions (edited by the agent)
├── _telos/
│   ├── work.md             # your goals / context — you write these
│   └── personal.md
├── Work/
│   └── 2026-04-15.md
├── Personal/
│   └── 2026-04-15.md
├── Habits/
│   └── 2026-04-15.md
└── Finance/
    └── 2026-04-15.md
```

**One file per silo per day.** Each entry is a timestamped section with mood, tags, and — for Finance — a structured expense table. All reads and writes are sandboxed to this directory.

---

## TELOS — give the agent context

TELOS is a personal-context framework from Daniel Miessler. Drop your work and life priorities into `_telos/work.md` and `_telos/personal.md`, and Dhaara will reason about your entries in that light. Example:

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
- **Proxy shell** — silo edits go through a constrained tool interface; the model cannot escape `data_dir`.
- **Local timezone** — timestamps honour whatever IANA zone you set in `config.yaml`.
- **Stateless per conversation** — `/clear` resets context; your data is the long-term memory.

---

## Commands

| Command | Does |
|---|---|
| `/start` | Intro + health check |
| `/clear` | Reset conversation context (your journal data is untouched) |

Everything else is an entry or a conversation.

---

## Roadmap

- **Phase 1** ✅ — Journaling, voice, multilingual, expense extraction, silo routing
- **Phase 2** 🚧 — RAG retrieval ("what did I write about dhaara last month?"), entry editing, daily/weekly summaries
- **Phase 3** 🔭 — Mood trends, habit dashboards, growth analysis, cross-agent workflows in the wider PAI ecosystem

---

## Contributing

Contributions are very welcome. Open an issue first for anything non-trivial so we can align on direction. Good first areas:

- Adding new AI providers (Anthropic direct, Gemini direct, local Ollama)
- New silo templates (Health, Reading, Relationships)
- Better expense parsing across currencies
- Tests — we need them

---

## License

MIT — see `LICENSE`. Use it, fork it, make it yours.

---

*Built in Bengaluru. Named for the quiet stream of thoughts we all carry.*
