#!/usr/bin/env python3
"""
Called by the workflow AFTER post_reel.py succeeds.
Appends the AI-generated title to topic_tracker.json so it won't be reused.
Running this only on success avoids polluting the tracker on failed posts.
"""

import json, datetime
from pathlib import Path

BASE    = Path(__file__).resolve().parent
TRACKER = BASE / "topic_tracker.json"
OUTPUT  = BASE.parent / "generated" / "ai_topic.json"


def main():
    if not OUTPUT.exists():
        print("No ai_topic.json found — nothing to confirm.")
        return

    with open(OUTPUT) as f:
        topic = json.load(f)

    if not topic.get("ai_generated"):
        print("Topic was not AI-generated — tracker unchanged.")
        return

    title = topic.get("title", "")
    if not title:
        return

    tracker = {}
    if TRACKER.exists():
        with open(TRACKER) as f:
            tracker = json.load(f)

    ai_titles = tracker.get("used_ai_titles", [])
    if title not in ai_titles:
        ai_titles.append(title)
    tracker["used_ai_titles"] = ai_titles[-30:]

    with open(TRACKER, "w") as f:
        json.dump(tracker, f, indent=2)

    print(f"Tracker updated: added '{title}' to used_ai_titles ({len(ai_titles)} total)")


if __name__ == "__main__":
    main()
