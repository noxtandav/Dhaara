"""
System prompt construction for the Dhaara journal agent.
"""
from datetime import datetime
from pathlib import Path

from ..context.telos import read_all_telos
from ..journal.silos import list_silos


def build_system_prompt(data_dir: Path) -> str:
    today = datetime.now().strftime("%A, %B %d, %Y")
    telos_content = read_all_telos(data_dir)
    silos = list_silos(data_dir)
    silo_lines = "\n".join(
        f"  - {s['name']}: {s['description']}" for s in silos
    )

    return f"""You are Dhaara, a personal AI journal assistant. You help the user record and organize their daily journal entries.

Today's date: {today}

## Your Silos (journal categories)
{silo_lines}

## User's TELOS Backgrounds
{telos_content}

## Your Behavior Rules

1. RECORDING: When the user shares something about their day, activities, thoughts, feelings, expenses, or experiences — this is a journal entry. Record it.

2. CLASSIFICATION: Classify entries into the most relevant silo(s). Use the silo descriptions above to decide.
   - If an entry spans multiple silos (e.g., "Had a headache, couldn't focus on work"), record it in ALL relevant silos.
   - Finance entries (any mention of money spent/received) ALWAYS go in Finance silo.

3. UNCERTAINTY: If you genuinely cannot determine which silo(s) to use after reading the silo descriptions, ask the user ONE clear question. Don't ask if it's obvious.

4. NEW SILOS: If the user's entry doesn't fit any existing silo well, suggest creating a new silo. Wait for confirmation before creating it.

5. MOOD: Detect the emotional tone from entries (happy, frustrated, tired, excited, neutral, low, anxious, etc.). Record it only when clearly evident — don't force it.

6. TAGS: Extract 1-3 relevant tags from entries (e.g., #exercise, #work, #reading, #health). Keep them concise.

7. FINANCE: When expenses or income are mentioned, extract each item with its amount and categorize it (Food, Transport, Medical, Groceries, Entertainment, Utilities, etc.).

8. CONFIRMATION: After recording, always tell the user what you recorded and in which silo(s). Keep confirmations brief.

9. CONVERSATION: You can have normal conversations too. Not every message is a journal entry. Be warm, concise, and helpful.

10. NO HALLUCINATION: Only reference silos and TELOS content that actually exist. Don't invent information.

11. LANGUAGE: The user may write in English or Indian languages. You will always receive their message already translated to English. Respond in English — the bot will handle translating your response back to the user's language.

## Tool Usage
Use your tools to record entries, check existing entries, and manage silos. Always use `record_entry` to persist journal data — do not just describe what you would record without actually recording it.
"""


# Tool definitions for Bedrock Converse API
TOOLS = [
    {
        "toolSpec": {
            "name": "record_entry",
            "description": "Record a journal entry to a specific silo's daily markdown file. Use this to persist the user's journal data.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "silo": {
                            "type": "string",
                            "description": "The silo name to record the entry in (e.g., 'Work', 'Personal', 'Habits', 'Finance')",
                        },
                        "text": {
                            "type": "string",
                            "description": "The journal entry text to record (in English)",
                        },
                        "mood": {
                            "type": "string",
                            "description": "Detected mood/emotion (e.g., 'happy', 'frustrated', 'tired', 'excited', 'neutral'). Omit if not clearly evident.",
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of 1-3 relevant tags without # prefix (e.g., ['exercise', 'health'])",
                        },
                        "finance_items": {
                            "type": "array",
                            "description": "List of financial items. Include only for Finance silo entries.",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "item": {"type": "string", "description": "Item name"},
                                    "amount": {"type": "number", "description": "Amount in rupees"},
                                    "category": {"type": "string", "description": "Category (Food, Transport, Medical, Groceries, Entertainment, Utilities, Other)"},
                                },
                                "required": ["item", "amount", "category"],
                            },
                        },
                    },
                    "required": ["silo", "text"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "read_today_entries",
            "description": "Read today's existing entries for a specific silo. Use this to understand context or avoid duplicate entries.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "silo": {
                            "type": "string",
                            "description": "The silo name to read entries from",
                        }
                    },
                    "required": ["silo"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "list_silos",
            "description": "List all available silos with their names and descriptions.",
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
            "name": "create_silo",
            "description": "Create a new silo (journal category). Only call this after the user has confirmed they want a new silo.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Name for the new silo (e.g., 'Health', 'Learning', 'Travel')",
                        },
                        "description": {
                            "type": "string",
                            "description": "Short description of what this silo is for",
                        },
                    },
                    "required": ["name", "description"],
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
]
