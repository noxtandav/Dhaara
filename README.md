# Dhaara

An AI-powered personal journal agent that runs on Telegram. Talk to it naturally — by text or voice, in English or Indian languages — and it organises your entries into structured daily markdown files across topic silos (Work, Personal, Habits, Finance, etc.).

Part of the **PAI (Personal AI)** ecosystem. Journal data is stored outside the project so future PAI agents can share it.

---

## Features

- **Telegram interface** — text and voice messages
- **Indian language support** — Sarvam AI handles speech-to-text, language detection, and translation
- **AI agent** — AWS Bedrock (any tool-use capable model) classifies entries, extracts mood, tags, and financial data
- **Silo-based organisation** — entries go into the right folder automatically; agent asks when unsure and suggests new silos when needed
- **Financial ledger** — expenses extracted and recorded as structured markdown tables
- **TELOS backgrounds** — manually maintained Work/Personal goal files give the agent context about your life
- **Shared data store** — markdown files outside the project, accessible to future PAI agents
- **Single authorised user** — bot ignores all other Telegram users

---

## Requirements

- Python 3.11+
- An AWS account with Bedrock access (Nova, Claude, or any tool-use capable model)
- A Sarvam AI API key — [sarvam.ai](https://sarvam.ai)
- A Telegram bot token — create one via [@BotFather](https://t.me/BotFather)
- Your Telegram user ID — get it from [@userinfobot](https://t.me/userinfobot)

---

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/your-username/dhaara.git
cd dhaara
```

### 2. Create a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate       # macOS/Linux
# venv\Scripts\activate        # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure

Copy the example config and fill in your values:

```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml`:

```yaml
telegram:
  bot_token: "YOUR_TELEGRAM_BOT_TOKEN"
  authorized_user_id: 123456789        # from @userinfobot

data_dir: "~/PAI/DhaaraData"           # where journal files are stored

bedrock:
  model_id: "amazon.nova-pro-v1:0"     # see config.example.yaml for options
  region: "ap-south-1"                 # your preferred AWS region
  aws_profile: "default"               # from ~/.aws/config

sarvam:
  api_key: "YOUR_SARVAM_API_KEY"
```

`config.yaml` is gitignored — it will never be committed.

### 5. Set up AWS credentials

Make sure your AWS profile has the following IAM permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream",
        "bedrock:GetFoundationModelAvailability",
        "bedrock:ListFoundationModels"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "aws-marketplace:ViewSubscriptions",
        "aws-marketplace:Subscribe"
      ],
      "Resource": "*"
    }
  ]
}
```

Also enable model access for your chosen provider in the AWS Bedrock console:
**AWS Console → Amazon Bedrock → Model access → Enable models**

### 6. Run

```bash
python -m src.main
```

---

## Choosing a Bedrock model

Dhaara works with any Bedrock model that supports **system prompts + tool use + multi-turn chat**.

| Model ID | Price (in/out per 1M tokens) | Notes |
|---|---|---|
| `us.amazon.nova-micro-v1:0` | ~$0.04 / ~$0.14 | Cheapest, text only |
| `us.amazon.nova-lite-v1:0` | ~$0.06 / ~$0.24 | Cheap + multimodal |
| `amazon.nova-pro-v1:0` | ~$0.80 / ~$3.20 | Good balance |
| `mistral.mistral-large-3-675b-instruct` | $0.50 / $1.50 | No prefix needed |
| `global.anthropic.claude-haiku-4-5-20251001-v1:0` | $1.00 / $5.00 | Fast Anthropic |
| `global.anthropic.claude-sonnet-4-6` | $3.00 / $15.00 | Best quality |

Newer Anthropic models require the `global.` prefix (cross-region inference profile). Amazon Nova models can be called directly or with the `us.` prefix.

Models that **do not work** (no tool use): `amazon.titan-*`, `deepseek.*`, `meta.llama2-*`, `mistral.mistral-7b-*`, `ai21.j2-*`, `cohere.command-text-*`

---

## Data storage

Journal data is stored in the directory specified by `data_dir` in `config.yaml` (default `~/PAI/DhaaraData/`). This is intentionally **outside the project** so multiple PAI agents can share it.

Structure:
```
DhaaraData/
  _config/
    silos.yaml          # silo definitions
  _telos/
    work.md             # manually maintained TELOS background
    personal.md         # manually maintained TELOS background
  Work/
    2026-04-02.md
  Personal/
    2026-04-02.md
  Habits/
    2026-04-02.md
  Finance/
    2026-04-02.md
```

Each entry is a timestamped markdown section with mood, tags, and (for Finance) a structured expense table.

---

## TELOS backgrounds

TELOS is a personal context framework (by Daniel Miessler). Edit `_telos/work.md` and `_telos/personal.md` in your data directory to give the agent context about your goals, projects, and priorities. The agent reads these files to better understand your entries.

---

## Bot commands

| Command | Description |
|---|---|
| `/start` | Introduction message |
| `/clear` | Clear conversation history for this session |

Everything else is treated as a journal entry or conversation.

---

## Example journal entries

Just talk naturally:

- `Worked on Dhaara for 2 hours. Getting close to finishing phase 1.`
- `Went for a 30 minute run this morning`
- `Feeling low today, couldn't focus on work`
- `Spent 30 on milk, 20 on cold drink, 150 on auto`
- `Read 40 pages of Atomic Habits. Almost done.`
- `Woke up at 9, slept badly — up 3 times in the night`
- Voice messages in Hindi, Tamil, or any Indian language work too

---

## Architecture

```
Telegram (text/voice)
  → Sarvam AI (STT + language detection + translation to English)
  → AWS Bedrock AI Agent (classify, extract, decide)
  → Journal Store (sandboxed markdown read/write)
  → Reply translated back to user's language via Sarvam AI
```

---

## Roadmap

- **Phase 1** (current) — Journal recording
- **Phase 2** — RAG-based retrieval, entry editing, daily summaries
- **Phase 3** — Mood trends, habit tracking dashboards, growth analysis

---

## Contributing

Contributions welcome once the project is open-sourced. Until then it is source-available for reference.

---

## License

TBD — will be open-sourced in a future release.
