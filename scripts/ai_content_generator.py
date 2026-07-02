#!/usr/bin/env python3
"""
AI Content Generator — uses Claude to create viral reel content
based on trending AI topics found via Google News RSS.

Generates 2 caption variants (educational + news-reaction) and
picks the best fit based on whether a strong headline exists today.
"""

import os, sys, json, datetime, re, xml.etree.ElementTree as ET
from pathlib import Path

import requests
import anthropic

BASE      = Path(__file__).resolve().parent
REPO_ROOT = BASE.parent
OUTPUT    = REPO_ROOT / "generated" / "ai_topic.json"
TRACKER   = BASE / "topic_tracker.json"

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL      = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001")

EVERGREEN_HASHTAGS = [
    "#AI", "#GenAI", "#ArtificialIntelligence", "#AITools",
    "#ChatGPT", "#Claude", "#LLM", "#PromptEngineering",
    "#AIAgents", "#MachineLearning", "#TechTips", "#FutureOfAI",
    "#AIAutomation", "#DeepLearning", "#AIForBusiness",
]


def log(msg):
    print(msg, flush=True)


def _search_google_news(query, max_results=5):
    """Search Google News RSS (free, no API key)."""
    try:
        url = f"https://news.google.com/rss/search?q={query.replace(' ', '+')}&hl=en&gl=US"
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code != 200:
            return []
        root = ET.fromstring(resp.text)
        results = []
        for item in root.findall(".//item")[:max_results]:
            title = item.find("title")
            if title is not None and title.text:
                results.append(title.text.strip())
        return results
    except Exception as e:
        log(f"  Search query '{query}' failed: {e}")
        return []


def fetch_trending_topics():
    """Fetch trending AI headlines from Google News RSS."""
    queries = [
        "generative AI trending",
        "AI tools new",
        "LLM AI agents",
        "artificial intelligence viral",
    ]
    headlines = []
    for q in queries:
        headlines.extend(_search_google_news(q))
    return list(dict.fromkeys(headlines))[:15]


def load_used_titles():
    if not TRACKER.exists():
        return []
    with open(TRACKER) as f:
        tracker = json.load(f)
    return tracker.get("used_ai_titles", [])


def generate_content(trending_headlines, used_titles):
    """Call Claude to generate viral reel content."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    today  = datetime.date.today().strftime("%B %d, %Y")
    year   = datetime.date.today().year

    headlines_block = (
        "\n".join(f"- {h}" for h in trending_headlines)
        if trending_headlines
        else "No trending data available — use your knowledge of current AI trends."
    )
    strong_headline = trending_headlines[0] if trending_headlines else None

    used_block = (
        "\n".join(f"- {t}" for t in used_titles[-15:])
        if used_titles else "None yet."
    )

    hashtag_block = " ".join(EVERGREEN_HASHTAGS)

    prompt = f"""You are a viral Instagram Reels content strategist for @agentwave.ai, a Gen AI education account targeting developers, creators, and AI enthusiasts.

Today is {today}.

## Trending AI Headlines (today)
{headlines_block}

## Recently Used Topics (DO NOT repeat these)
{used_block}

## Task

Create ONE Instagram Reel topic about Gen AI that will perform well on Instagram.

Output ONLY this JSON (no markdown fences, no explanation):

{{
  "topic_title": "Short punchy title (max 8 words)",
  "hook": "One bold claim or surprising fact — no emoji, max 15 words",
  "points": ["Concise point 1 (max 10 words)", "Point 2", "Point 3", "Point 4"],
  "cta": "Engaging call to action (max 12 words)",
  "caption_variants": [
    {{
      "caption": "Educational angle: teaches something concrete, opens with a clear insight, 3–5 punchy lines, no fluff",
      "hashtags": "#Tag1 #Tag2 #Tag3 #Tag4 #Tag5",
      "virality_score": 8,
      "angle": "educational",
      "use_when": "always"
    }},
    {{
      "caption": "News-reaction angle: references today's headline directly, opinionated take, conversational tone",
      "hashtags": "#Tag1 #Tag2 #Tag3 #Tag4 #Tag5",
      "virality_score": 9,
      "angle": "news-reaction",
      "use_when": "strong_headline_exists"
    }}
  ],
  "has_strong_headline": true,
  "trend_source": "Which headline or trend inspired this topic",
  "bg_prompt": "Pollinations.ai image prompt for an engaging background"
}}

## Content guardrails
- Hook must NOT use emoji (the renderer strips them)
- Hook must be a genuine insight or surprising fact — no doom-bait, no fabricated statistics
- Do NOT name or attack specific companies negatively
- Points must each teach something non-obvious and be verifiable
- If referencing today's headline, quote it accurately — do not embellish
- bg_prompt: dark moody abstract (80%+ dark), 1–2 accent glow colors, NO literal objects (no laptops, people, screens). Must not compete with text overlay.
- EXACTLY 5 hashtags per variant — pick from evergreen list or propose 2 niche tags relevant to the topic: {hashtag_block}
- Year references must use {year}, never a hardcoded past year
- Output raw JSON only"""

    log(f"Calling Claude ({CLAUDE_MODEL})...")
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1200,
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
    content     = generate_content(headlines, used_titles)

    variants = content["caption_variants"]

    # Pick news-reaction variant when a strong headline exists, else educational
    has_strong = content.get("has_strong_headline", bool(headlines))
    preferred  = next(
        (v for v in variants if v["angle"] == "news-reaction" and has_strong),
        None,
    ) or next(
        (v for v in variants if v["angle"] == "educational"),
        variants[0],
    )

    day_id = datetime.date.today().timetuple().tm_yday

    topic = {
        "id":            day_id,
        "title":         content["topic_title"],
        "hook":          content["hook"],
        "emoji":         "🤖",
        "points":        content["points"],
        "hashtags":      preferred["hashtags"],
        "cta":           content["cta"],
        "caption":       preferred["caption"] + "\n\n" + preferred["hashtags"],
        "bg_prompt":     content.get("bg_prompt", ""),
        "ai_generated":  True,
        "trend_source":  content.get("trend_source", ""),
        "generated_date": str(datetime.date.today()),
        "all_variants":  variants,
        "chosen_angle":  preferred["angle"],
    }

    OUTPUT.parent.mkdir(exist_ok=True)
    with open(OUTPUT, "w") as f:
        json.dump(topic, f, indent=2)

    # NOTE: used_ai_titles is written to tracker only AFTER post_reel.py succeeds
    # (handled by confirm_post.py called from the workflow).

    log(f"\nGenerated: {topic['title']}")
    log(f"  Hook: {topic['hook'][:70]}")
    log(f"  Chosen caption: {preferred['angle']} (score: {preferred['virality_score']}/10)")
    log(f"  Trend source: {topic['trend_source']}")
    log(f"  Saved to: {OUTPUT}")


if __name__ == "__main__":
    main()
