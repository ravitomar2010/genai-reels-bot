# Gen AI Master — Daily Instagram Reels Bot

Automatically generates and posts a daily Gen AI tutorial Reel to [@agentwave.ai](https://instagram.com/agentwave.ai) using GitHub Actions + Zernio.

## How it works

1. **GitHub Actions** triggers at 10 AM IST every day
2. `generate_reel_v2.py` creates an animated 1080×1920 MP4 Reel with AI background
3. `post_reel.py` uploads to Zernio and posts to Instagram automatically
4. `topic_tracker.json` is committed back so topics rotate daily (30 topics = 1 month)

## Setup

### 1. Fork / clone this repo

### 2. Add GitHub Secret
Go to **Settings → Secrets → Actions → New secret**:
- Name: `ZERNIO_API_KEY`
- Value: your Zernio API key from [zernio.com/dashboard/api-keys](https://zernio.com/dashboard/api-keys)

### 3. That's it!
The workflow runs daily at 04:30 UTC (10:00 AM IST). You can also trigger it manually from the **Actions** tab.

## Files

| File | Purpose |
|------|---------|
| `scripts/generate_reel_v2.py` | Generates animated Reel video |
| `scripts/topics_genai.json` | 30 Gen AI tutorial topics |
| `scripts/topic_tracker.json` | Tracks which topics have been posted |
| `scripts/post_reel.py` | Uploads to Zernio + posts to Instagram |
| `.github/workflows/daily_reel.yml` | GitHub Actions schedule |

## Customise

- **Topics**: Edit `scripts/topics_genai.json`
- **Handle**: Change `"handle"` field in `topics_genai.json`
- **Post time**: Edit the cron in `.github/workflows/daily_reel.yml`
- **Voice**: Run `add_voice_character.py` locally to add voiceover
