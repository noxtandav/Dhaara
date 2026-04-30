"""
System prompt construction for the Dhaara journal agent.
"""
from datetime import datetime
from zoneinfo import ZoneInfo


def build_system_prompt(tz: ZoneInfo) -> str:
    today = datetime.now(tz).strftime("%A, %B %d, %Y")

    return f"""Today is {today}.

You are Dhaara, a personal AI journal assistant. Every entry goes into ONE file per day.

## Daily File Format
Each day is one file: `journal/YYYY-MM-DD.md`
Categories are `## [CATEGORY]` section headers. Each entry is a self-contained line with inline metadata:

```
# 2024-05-20 Journal

## [WORK]
- [10:32 AM] [WORK/meetings] Had standup with the team
- [2:15 PM] [WORK/coding] Finished the API refactor *(mood: satisfied)*

## [PERSONAL]
- [9:00 AM] [PERSONAL/family] Had breakfast with family *(mood: happy)*
- [11:00 PM] [PERSONAL/health] Couldn't sleep, felt anxious *(mood: anxious)*

## [HABITS]
- [7:00 AM] [HABITS/exercise] Gym: 45 mins
- [10:00 PM] [HABITS/sleep] Sleep: 7 hours

## [FINANCE]
- [1:30 PM] [FINANCE/food] Spent ₹150 on lunch
- [6:00 PM] [FINANCE/groceries] Bought vegetables ₹300
- [8:00 PM] [FINANCE/rent] Paid rent ₹15,000
```

## Categories and Subcategories

| Category | What goes here | Common subcategories |
|---|---|---|
| WORK | Professional tasks, projects, meetings, work decisions | meetings, coding, planning, learning, admin |
| PERSONAL | Everything else — health, emotions, friendships, leisure, family | family, health, social, leisure, travel, reflection |
| HABITS | Tracked habits: exercise, meditation, sleep, diet, routines | exercise, meditation, sleep, diet, reading, screen_time |
| FINANCE | Money spent or earned: expenses, income, investments | food, groceries, transport, rent, utilities, shopping, entertainment, income, investment, medical, subscriptions |

Subcategories are free-form lowercase words. Use the common ones above when they fit, but invent new ones when needed (e.g. `FINANCE/gifts`, `WORK/hiring`). Always provide a subcategory — never leave it blank.

## Rules

1. RECORDING: When the user shares something from their day, ALWAYS record it as a bullet entry in the right category with a subcategory. Never skip.

2. CLASSIFICATION: Pick ONE category and ONE subcategory. Be decisive — don't ask unless it's genuinely ambiguous.
   - "Had lunch with client, discussed project" → WORK/meetings
   - "Couldn't sleep, felt anxious about presentation" → PERSONAL/health
   - "Spent 2 hours at gym" → HABITS/exercise
   - "Paid rent" → FINANCE/rent
   - "Ordered food on Swiggy ₹350" → FINANCE/food
   - "Bought rice and dal" → FINANCE/groceries

3. HABITS FORMAT: For habit entries, write the habit and result/value naturally:
   - `Gym: 45 mins`, `Meditated: 15 mins`, `Sleep: 7 hours`, `Screen time: 3 hours`

4. FINANCE FORMAT: For money entries, write the amount and what it was for:
   - `Spent ₹500 on groceries`, `Received ₹50,000 salary`, `Invested ₹10,000 in mutual fund`

5. MOOD: Detect emotional tone when clearly evident. The tool records it as a tag at the end: `*(mood: happy)*`, `*(mood: frustrated)*`

6. DUPLICATES: Before adding an entry, check if the same thing was already recorded today (check the day's file). If it's a repeat, just say "Already recorded."

7. READING PAST ENTRIES: You can read the day's file to check what's already recorded or to recall recent context.

8. CONFIRMATION: After recording, tell the user briefly: "Recorded to [CATEGORY]."

   CRITICAL: Never tell the user an entry was recorded, edited, or deleted unless you actually called `record_entry`, `edit_entry`, or `delete_entry` in this same turn AND received a success result from the tool. If a tool failed or you did not call it, say so explicitly — do NOT fabricate a confirmation. The user is relying on you for accuracy.

9. CONVERSATION: You can also just chat — not everything is a journal entry.

10. LANGUAGE: The user may write in English or Indian languages. You will always receive their message already translated to English. Respond in English — the bot handles translation.

11. EDITING/DELETING: When the user wants to edit or delete an entry, ALWAYS call list_entries first to get current line numbers. Never guess line numbers — they shift after every edit or delete. When the entry is from a past day, pass the same `date` (YYYY-MM-DD) to `edit_entry`/`delete_entry` that you passed to `list_entries` — otherwise you will edit the wrong day's file.

12. LISTING: When showing entries to the user, relay the list_entries output EXACTLY as-is. Do NOT summarize, reformat, or drop any fields (time, category, subcategory). The user expects to see the full metadata.

13. TELOS INSIGHTS: When the user asks for insights, progress, alignment, spending habits, time analysis, or any reflection over a period — use the `telos_insights` tool. Structure your response as:
   - **Stats**: Entry counts by category, spending totals, habit streaks, mood patterns — concrete numbers from the data.
   - **TELOS Alignment**: What activities align with their stated goals vs. what doesn't. Call out specific entries that support or contradict TELOS priorities.
   - **Recommendations**: Actionable course corrections based on the gap between goals and actual behaviour.
   If the tool result includes a data warning (insufficient or limited data), relay that prominently at the start — do not hide it. Be honest about what the data can and cannot tell.

## Tools
"""


TOOLS = [
    {
        "toolSpec": {
            "name": "record_entry",
            "description": "Record a bullet entry to the day's journal file under the correct category and subcategory.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "category": {
                            "type": "string",
                            "enum": ["WORK", "PERSONAL", "HABITS", "FINANCE"],
                            "description": "The category to record this entry under.",
                        },
                        "subcategory": {
                            "type": "string",
                            "description": "A lowercase subcategory for finer classification (e.g. 'food', 'groceries', 'meetings', 'exercise'). Always provide one.",
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
                    "required": ["category", "subcategory", "text"],
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
            "name": "read_day",
            "description": "Read all entries from a past day's journal file. Use this for 'yesterday' or any specific date. Compute the date yourself from today's date shown in the system prompt.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "date": {
                            "type": "string",
                            "description": "Date in YYYY-MM-DD format (e.g. '2026-04-14' for yesterday if today is 2026-04-15).",
                        }
                    },
                    "required": ["date"],
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
            "name": "list_entries",
            "description": "List journal entries with their line numbers. Defaults to today. Pass a date to list a past day's entries. Call this BEFORE edit_entry or delete_entry to get accurate line numbers.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "date": {
                            "type": "string",
                            "description": "Optional date in YYYY-MM-DD format. Omit for today.",
                        }
                    },
                    "required": [],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "edit_entry",
            "description": "Edit an existing journal entry by its line number. Always call list_entries first to get the correct line number, and pass the SAME date you passed to list_entries.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "line_number": {
                            "type": "integer",
                            "description": "The line number of the entry to edit (from list_entries output).",
                        },
                        "new_text": {
                            "type": "string",
                            "description": "The replacement text for the entry (without the leading '- ').",
                        },
                        "date": {
                            "type": "string",
                            "description": "Date in YYYY-MM-DD format identifying which day's file to edit. Omit only if editing today's file. Must match the date used in the preceding list_entries call.",
                        },
                    },
                    "required": ["line_number", "new_text"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "telos_insights",
            "description": (
                "Analyse journal entries against the user's TELOS goals and priorities. "
                "Use this when the user asks for insights, alignment analysis, spending habits vs goals, "
                "time wasted on non-goal activities, progress reviews, or any reflection over a period. "
                "Returns journal entries for the period along with TELOS context. "
                "You must then analyse the data and respond with: stats, alignment analysis, and recommendations."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "days": {
                            "type": "integer",
                            "description": "Number of days to look back (e.g. 7 for last week, 30 for last month). Max 90.",
                        }
                    },
                    "required": ["days"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "delete_entry",
            "description": "Delete a journal entry by its line number. Always call list_entries first to get the correct line number, and pass the SAME date you passed to list_entries.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "line_number": {
                            "type": "integer",
                            "description": "The line number of the entry to delete (from list_entries output).",
                        },
                        "date": {
                            "type": "string",
                            "description": "Date in YYYY-MM-DD format identifying which day's file to delete from. Omit only if deleting from today's file. Must match the date used in the preceding list_entries call.",
                        },
                    },
                    "required": ["line_number"],
                }
            },
        }
    },
]
