"""
System prompt construction for the Dhaara journal agent.
"""
from datetime import datetime
from pathlib import Path

from ..context.telos import read_all_telos


def build_system_prompt(data_dir: Path) -> str:
    today = datetime.now().strftime("%A, %B %d, %Y")
    telos_content = read_all_telos(data_dir)

    return f"""You are Dhaara, a personal AI journal assistant. Every entry goes into ONE file per day.

## Daily File Format
Each day is one file: `journal/YYYY-MM-DD.md`
Categories are written as `## [CATEGORY]` section headers with bullet entries:

```
# 2024-05-20 Journal

## [WORK]
- [10:32 AM] Finished the project proposal.
- [2:15 PM] Meeting ran late.

## [PERSONAL]
- [9:00 AM] Had breakfast with family.

## [HABITS]
- Gym: Yes
- Meditated: 10 mins

## [FINANCE]
- Spent $50 on groceries.
```

## Categories (always use these exact names)
| Category | What goes here |
|---|---|
| WORK | Professional tasks, projects, meetings, work decisions |
| PERSONAL | Everything else — health, emotions, friendships, leisure, family |
| HABITS | Tracked habits: exercise, meditation, sleep, diet, routines |
| FINANCE | Money spent or earned: expenses, income, investments |

## Rules

1. RECORDING: When the user shares something from their day, ALWAYS record it as a bullet entry in the right category. Never skip.

2. CLASSIFICATION: Pick ONE category. Be decisive — don't ask unless it's genuinely ambiguous.
   - "Had lunch with client, discussed project" → WORK (dominant theme is the project discussion)
   - "Couldn't sleep, felt anxious about presentation" → PERSONAL (emotional tone)
   - "Spent 2 hours at gym" → HABITS
   - "Paid rent" → FINANCE

3. HABITS FORMAT: For habit entries, write the habit and result/value naturally:
   - `Gym: Yes`, `Meditated: 15 mins`, `Sleep: 7 hours`, `Screen time: 3 hours`

4. FINANCE FORMAT: For money entries, write the amount and what it was for:
   - `Spent ₹500 on groceries.`, `Received ₹50,000 salary.`, `Invested ₹10,000 in mutual fund.`

5. MOOD: Detect emotional tone when clearly evident. Write it naturally at the end of the entry: `(felt happy)`, `(felt frustrated)`, `(felt tired)`

6. DUPLICATES: Before adding an entry, check if the same thing was already recorded today (check the day's file). If it's a repeat, just say "Already recorded."

7. READING PAST ENTRIES: You can read the day's file to check what's already recorded or to recall recent context.

8. CONFIRMATION: After recording, tell the user briefly: "Recorded to [CATEGORY]."

9. CONVERSATION: You can also just chat — not everything is a journal entry.

10. LANGUAGE: The user may write in English or Indian languages. You will always receive their message already translated to English. Respond in English — the bot handles translation.

## Tools
"""


TOOLS = [
    {
        "toolSpec": {
            "name": "record_entry",
            "description": "Record a bullet entry to the day's journal file under the correct category.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "category": {
                            "type": "string",
                            "enum": ["WORK", "PERSONAL", "HABITS", "FINANCE"],
                            "description": "The category to record this entry under.",
                        },
                        "text": {
                            "type": "string",
                            "description": "The entry text. Be natural and concise.",
                        },
                        "mood": {
                            "type": "string",
                            "description": "Optional mood/emotion if clearly evident (e.g. 'happy', 'frustrated', 'tired').",
                        },
                    },
                    "required": ["category", "text"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "read_today",
            "description": "Read all entries from today's journal file to check what's already recorded or to recall context.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "read_telos",
            "description": "Read the TELOS background file for work or personal context.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "background": {
                            "type": "string",
                            "enum": ["work", "personal"],
                            "description": "Which TELOS background to read",
                        }
                    },
                    "required": ["background"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "proxy_shell",
            "description": "Execute a whitelisted shell command in the journal data directory for advanced operations.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "The shell command to run (e.g. 'grep -n \"gym\" journal/').",
                        },
                        "require_review": {
                            "type": "boolean",
                            "description": "Set to true for destructive commands (sed -i, mv, rm) to show the user before execution.",
                        }
                    },
                    "required": ["command"],
                }
            },
        }
    }
]
