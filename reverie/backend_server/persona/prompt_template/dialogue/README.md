This directory is the single home for NPC dialogue-related prompt templates.

Structure:
- `initiation/`: decide whether to start talking.
- `generation/`: produce conversation turns or whole dialogue snippets.
- `reflection/`: summarize, score, and derive memories from finished dialogue.

Guidelines for adding new dialogue templates:
- Put every new NPC conversation prompt under this directory.
- Group by the runtime scenario, not by model version.
- Prefer descriptive filenames tied to the behavior, for example `social_chat_support_v1.txt`.
- When replacing an old template, update code references first and then remove the old duplicate.
