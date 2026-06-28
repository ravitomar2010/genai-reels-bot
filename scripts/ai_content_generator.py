#!/usr/bin/env python3
"""
AI Content Generator — uses Claude to create viral reel content
based on trending AI topics found via web search.

Searches Google News RSS for trending GenAI topics (free, no API key),
then asks Claude to craft a viral topic with 5 caption variants.
"""

import os, sys, json, datetime, re, xml.etree.ElementTree as ET
from pathlib import Path

import requests
import anthropic

BASE = Path(__file__).resolve().parent
REPO_ROOT = BASE.parent
OUTPUT = REPO_ROOT / "generated" / "ai_topic.json"
TRACKER = BASE / "topic_tracker.json"

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001")


def log(msg):
    print(msg, flush=True)


def fetch_trending_topics():
    """Fetch trending AI headlines from Google News RSS (free, no API key)."""
    queries = [
        "generative AI trending",
        "AI tools new",
        "LLM AI agents",
        "artificial intelligence viral",
    ]
    headlines = []
    for q in queries:
        try:
            url = f"https://news.google.com/rss/search?q={q.replace(' ', '+')}&hl=en&gl=US"
            resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code != 200:
                continue
            root = ET.fromstring(resp.text)
            for item in root.findall(".//item")[:5]:
                title = item.find("title")
                if title is not None and title.text:
                    headlines.append(title.text.strip())
        except Exception as e:
            log(f"  Search query '{q}' failed: {e}")
    return list(dict.fromkeys(headlines))[:15]


def load_used_titles():
    """Load previously used AI-generated titles to avoid repeats."""
    if not TRACKER.exists():
        return []
    with open(TRACKER) as f:
        tracker = json.load(f)
    return tracker.get("used_ai_titles", [])


def generate_content(trending_headlines, used_titles):
    """Call Claude to generate viral reel content."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    today = datetime.date.today().strftime("%B %d, %Y")

    if trending_headlines:
        headlines_block = "\n".join(f"- {h}" for h in trending_headlines)
    else:
        headlines_block = "No trending data available — use your knowledge of current AI trends."

    if used_titles:
        used_block = "\n".join(f"- {t}" for t in used_titles[-15:])
    else:
        used_block = "None yet."

    prompt = f"""You are a viral Instagram Reels content strategist for @agentwave.ai, a Gen AI education account targeting developers, creators, and AI enthusiasts.

Today is {today}.

## Trending AI Headlines
{headlines_block}

## Recently Used Topics (DO NOT repeat these)
{used_block}

## Task

Based on the trending topics, create ONE Instagram Reel topic about Gen AI that will go VIRAL.

Output ONLY this JSON (no markdown fences, no explanation):

{{
  "topic_title": "Short punchy title (max 8 words)",
  "hook": "Line 1: bold claim or question\\nLine 2: teaser ending with emoji",
  "points": ["Concise point 1 (max 10 words)", "Point 2", "Point 3", "Point 4"],
  "cta": "Engaging call to action (max 12 words)",
  "caption_variants": [
    {{
      "caption": "Full Instagram caption with emojis, line breaks, and personality",
      "hashtags": "#Tag1 #Tag2 #Tag3 #Tag4 #Tag5 #Tag6 #Tag7 #Tag8",
      "virality_score": 8,
      "angle": "educational / controversial / story / listicle / question"
    }},
    {{
      "caption": "Different angle caption...",
      "hashtags": "#DifferentMix #OfTags ...",
      "virality_score": 7,
      "angle": "..."
    }},
    {{
      "caption": "...",
      "hashtags": "...",
      "virality_score": 6,
      "angle": "..."
    }},
    {{
      "caption": "...",
      "hashtags": "...",
      "virality_score": 7,
      "angle": "..."
    }},
    {{
      "caption": "...",
      "hashtags": "...",
      "virality_score": 9,
      "angle": "..."
    }}
  ],
  "trend_source": "Which headline or trend inspired this topic"
}}

Rules:
- Hook line 1 must create a curiosity gap or make a bold/controversial claim
- Each point should surprise or teach something non-obvious
- ALL 5 caption variants must use a DIFFERENT angle (educational, controversial, personal story, listicle, question-based)
- Hashtags: mix 3 high-volume tags (#AI #GenAI #ArtificialIntelligence) with 5 niche tags
- Score each variant honestly 1-10 on viral potential
- Output raw JSON only"""

    log(f"Calling Claude ({CLAUDE_MODEL})...")
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)

    return json.loads(text)


def main():
    if not ANTHROPIC_API_KEY:
        raise EnvironmentError("ANTHROPIC_API_KEY not set in environment / GitHub secrets")

    log("=== AI Content Generator ===")

    log("Fetching trending AI topics...")
    headlines = fetch_trending_topics()
    log(f"Found {len(headlines)} trending headlines")
    for h in headlines[:5]:
        log(f"  • {h[:80]}")

    used_titles = load_used_titles()
    content = generate_content(headlines, used_titles)

    # Pick the highest-scoring variant
    variants = content["caption_variants"]
    best_idx = max(range(len(variants)), key=lambda i: variants[i].get("virality_score", 0))
    best = variants[best_idx]

    # Use day-of-year for theme cycling (1-365 maps to different visual themes)
    day_id = datetime.date.today().timetuple().tm_yday

    topic = {
        "id": day_id,
        "title": content["topic_title"],
        "hook": content["hook"],
        "emoji": "🤖",
        "points": content["points"],
        "hashtags": best["hashtags"],
        "cta": content["cta"],
        "caption": best["caption"] + "\n\n" + best["hashtags"],
        "ai_generated": True,
        "trend_source": content.get("trend_source", ""),
        "generated_date": str(datetime.date.today()),
        "all_variants": variants,
        "best_variant_index": best_idx,
    }

    OUTPUT.parent.mkdir(exist_ok=True)
    with open(OUTPUT, "w") as f:
        json.dump(topic, f, indent=2)

    # Update tracker with used title
    tracker = {}
    if TRACKER.exists():
        with open(TRACKER) as f:
            tracker = json.load(f)
    ai_titles = tracker.get("used_ai_titles", [])
    ai_titles.append(content["topic_title"])
    tracker["used_ai_titles"] = ai_titles[-30:]
    with open(TRACKER, "w") as f:
        json.dump(tracker, f, indent=2)

    log(f"\nGenerated: {topic['title']}")
    log(f"  Hook: {topic['hook'][:70]}...")
    log(f"  Best caption: variant #{best_idx + 1} (score: {best['virality_score']}/10, angle: {best['angle']})")
    log(f"  Trend source: {topic['trend_source']}")
    log(f"  Saved to: {OUTPUT}")


if __name__ == "__main__":
    main()
