# Gen AI Master — Daily Instagram Reels Bot

Automatically generates and posts a daily Gen AI tutorial Reel to [@agentwave.ai](https://instagram.com/agentwave.ai) using GitHub Actions + Zernio.

## How it works

1. **GitHub Actions** triggers at 10 AM IST (04:30 UTC) every day
2. `ai_content_generator.py` fetches trending headlines via Google News RSS and calls Claude to generate a topic + 2 caption variants (educational and news-reaction). If this step fails, the run falls back to the static `topics_genai.json` rotation automatically.
3. `generate_reel_v2.py` creates a 30 FPS 1080×1920 MP4 Reel:
   - Per-slide edge-tts voiceover generated first; each slide's duration = its narration + 0.4 s padding so narration stays perfectly in sync
   - AI background from Pollinations.ai (free, no key needed)
   - VFX: Ken Burns, floating particles, light sweep, pulse rings, energy border, text slam
   - Glassmorphism / gradient / neon translucent cards with AI background showing through
   - Loudnorm audio (-14 LUFS, Instagram standard); optional background music from `assets/music/`
4. `post_reel.py` uploads the MP4 to Zernio (presigned URL flow) and publishes to Instagram as a Reel
5. `confirm_post.py` appends the used title to `topic_tracker.json` **only after a successful post** so a failed run never marks a topic as consumed
6. `topic_tracker.json` is committed back so topics rotate without repeats

## Setup

### 1. Fork / clone this repo

### 2. Add GitHub Secrets
Go to **Settings → Secrets → Actions → New secret**:

| Secret | Value |
|--------|-------|
| `ZERNIO_API_KEY` | From [zernio.com/dashboard/api-keys](https://zernio.com/dashboard/api-keys) |
| `ANTHROPIC_API_KEY` | From [console.anthropic.com](https://console.anthropic.com) |

### 3. That's it!
The workflow runs daily at 04:30 UTC (10:00 AM IST). Trigger manually from the **Actions** tab at any time.

## Files

| File | Purpose |
|------|---------|
| `scripts/generate_reel_v2.py` | Generates 30 FPS animated Reel with per-slide audio sync |
| `scripts/ai_content_generator.py` | Claude-powered daily topic + caption generator |
| `scripts/post_reel.py` | Uploads to Zernio + posts to Instagram |
| `scripts/confirm_post.py` | Writes tracker entry after successful post |
| `scripts/topics_genai.json` | 30 static Gen AI tutorial topics (fallback) |
| `scripts/topic_tracker.json` | Tracks used topics |
| `.github/workflows/daily_reel.yml` | GitHub Actions schedule + fallback logic |

## Customise

- **Topics**: Edit `scripts/topics_genai.json` or let Claude generate them daily
- **Handle**: Change `"handle"` field in `topics_genai.json`
- **Post time**: Edit the cron in `.github/workflows/daily_reel.yml`
- **Voice**: Change `VOICE` constant in `generate_reel_v2.py` (any `edge-tts` voice)
- **Background music**: Drop an MP3 in `assets/music/` — it will be mixed at -20 dB under the voice
- **Theme**: Edit `THEMES` list in `generate_reel_v2.py`

## Local testing

```bash
# Install deps
pip install -r requirements.txt

# Generate with a specific static topic (no API keys needed)
python3 scripts/generate_reel_v2.py 1

# Generate with AI content (needs ANTHROPIC_API_KEY)
export ANTHROPIC_API_KEY=sk-...
python3 scripts/ai_content_generator.py
python3 scripts/generate_reel_v2.py

# Post (needs ZERNIO_API_KEY)
export ZERNIO_API_KEY=sk_...
python3 scripts/post_reel.py
python3 scripts/confirm_post.py
```
