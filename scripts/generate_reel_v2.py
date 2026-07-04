#!/usr/bin/env python3
"""
Instagram Reel Generator v2 — Animated + AI Backgrounds (Pollinations.ai)
- Free AI backgrounds via pollinations.ai (no API key needed)
- Text reveal animations (line by line)
- Fade in/out transitions
- Glowing accent elements
- 30 FPS, per-slide voiceover sync, loudnorm audio
"""

import os, sys, json, subprocess, textwrap, math, datetime, re, urllib.parse, shutil, asyncio, random
from pathlib import Path
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

BASE    = Path(__file__).resolve().parent
TOPICS  = BASE / "topics_genai.json"
TRACKER = BASE / "topic_tracker.json"
REPO_ROOT = BASE.parent
OUTDIR    = REPO_ROOT / "generated"
OUTDIR.mkdir(exist_ok=True)
FRAMES    = Path("/tmp/reel_frames")
FRAMES.mkdir(exist_ok=True)
BG_CACHE  = REPO_ROOT / "bg_cache"
BG_CACHE.mkdir(exist_ok=True)

W, H  = 1080, 1920
FPS   = 30

_FONT_SEARCH_DIRS = [
    "/usr/share/fonts/truetype/google-fonts",
    "/usr/share/fonts/truetype",
    "/usr/share/fonts",
    "/usr/local/share/fonts",
    str(REPO_ROOT / "fonts"),
]

_FONT_URLS = {
    "Poppins-Bold.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/poppins/Poppins-Bold.ttf",
    "Poppins-Medium.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/poppins/Poppins-Medium.ttf",
    "Poppins-Regular.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/poppins/Poppins-Regular.ttf",
}

def _find_font(name):
    for d in _FONT_SEARCH_DIRS:
        p = os.path.join(d, name)
        if os.path.isfile(p):
            return p
    return None

def _ensure_fonts():
    """Download Poppins fonts if not found on the system."""
    fonts_dir = REPO_ROOT / "fonts"
    missing = [n for n in _FONT_URLS if _find_font(n) is None]
    if not missing:
        return
    fonts_dir.mkdir(exist_ok=True)
    import requests
    for name in missing:
        dest = fonts_dir / name
        if dest.exists():
            continue
        print(f"  Downloading {name}...")
        resp = requests.get(_FONT_URLS[name], timeout=30)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
    print(f"  Fonts cached in {fonts_dir}")

_ensure_fonts()

FONT_BOLD  = _find_font("Poppins-Bold.ttf") or "Poppins-Bold.ttf"
FONT_MED   = _find_font("Poppins-Medium.ttf") or "Poppins-Medium.ttf"
FONT_REG   = _find_font("Poppins-Regular.ttf") or "Poppins-Regular.ttf"

print(f"  Font Bold:    {FONT_BOLD}")
print(f"  Font Medium:  {FONT_MED}")
print(f"  Font Regular: {FONT_REG}")

def fnt(path, size):
    try:
        f = ImageFont.truetype(path, size)
        return f
    except Exception as e:
        print(f"  WARNING: Font {path} size {size} failed ({e}), using default")
        return ImageFont.load_default()

def strip_emoji(t):
    return re.sub(r'[^\x00-\x7FÀ-ɏ‐-⁯ ]','',t).strip()

THEMES = [
    {"bg":(8,6,20),   "accent":(110,40,255),  "glow":(80,20,200),  "card":(22,16,50,200),  "sub":(180,140,255), "bright":(220,200,255), "overlay":(8,6,20,190)},
    {"bg":(4,14,30),  "accent":(0,160,255),   "glow":(0,80,180),   "card":(10,30,60,200),  "sub":(100,200,255), "bright":(180,230,255), "overlay":(4,14,30,185)},
    {"bg":(22,6,6),   "accent":(255,60,30),   "glow":(180,20,0),   "card":(44,14,10,200),  "sub":(255,150,120), "bright":(255,210,200), "overlay":(22,6,6,185)},
    {"bg":(4,20,12),  "accent":(0,200,90),    "glow":(0,120,50),   "card":(8,44,22,200),   "sub":(80,230,150),  "bright":(180,255,210), "overlay":(4,20,12,185)},
    {"bg":(20,12,0),  "accent":(255,150,0),   "glow":(180,80,0),   "card":(44,26,0,200),   "sub":(255,200,80),  "bright":(255,235,160), "overlay":(20,12,0,185)},
]

# ── AI Background prompts per theme ───────────────────────────────────────
BG_PROMPTS = {
    0: "AI neural network purple glowing circuits dark abstract cinematic 4k vertical",
    1: "futuristic blue data streams digital technology dark abstract cinematic 4k vertical",
    2: "red orange AI technology fire energy abstract dark cinematic 4k vertical",
    3: "green matrix digital forest AI technology glowing dark abstract cinematic 4k vertical",
    4: "golden orange AI brain neural network dark abstract cinematic 4k vertical",
}

TOPIC_PROMPTS = {
    1:  "prompt engineering AI brain text glowing dark abstract purple cinematic vertical",
    2:  "RAG retrieval augmented generation database knowledge network dark cinematic vertical",
    3:  "large language model LLM neural network glowing circuits dark cinematic vertical",
    4:  "AI agents autonomous robots futuristic dark glowing cinematic vertical",
    5:  "MCP model context protocol data connection abstract dark cinematic vertical",
    6:  "Claude GPT comparison AI models glowing dark abstract cinematic vertical",
    7:  "free AI tools technology collage dark glowing abstract cinematic vertical",
    8:  "vector database embeddings 3D abstract dark glowing cinematic vertical",
    9:  "fine-tuning AI model training neural network dark cinematic vertical",
    10: "AI hallucination abstract mind brain digital glitch dark cinematic vertical",
}

_custom_bg_prompt = None

def set_custom_bg_prompt(prompt):
    global _custom_bg_prompt
    _custom_bg_prompt = prompt

def get_bg_prompt(topic_id, theme_idx):
    if _custom_bg_prompt:
        return _custom_bg_prompt
    if topic_id in TOPIC_PROMPTS:
        return TOPIC_PROMPTS[topic_id]
    return BG_PROMPTS.get(theme_idx, BG_PROMPTS[0])


# ── Fetch AI background ────────────────────────────────────────────────────
def fetch_ai_background(topic_id, theme_idx, theme):
    """Download from Pollinations.ai (free). Falls back to gradient."""
    cache_path = BG_CACHE / f"bg_topic{topic_id}.jpg"
    if cache_path.exists():
        print(f"  Using cached background for topic {topic_id}")
        return Image.open(cache_path).convert("RGB")

    prompt = get_bg_prompt(topic_id, theme_idx)
    url = (f"https://image.pollinations.ai/prompt/"
           f"{urllib.parse.quote(prompt)}"
           f"?width=1080&height=1920&nologo=true&seed={topic_id*7+42}&enhance=true")
    print(f"  Fetching AI background: {prompt[:60]}...")
    import requests as _req
    for attempt in range(1, 3):
        try:
            resp = _req.get(url, timeout=90)
            resp.raise_for_status()
            img = Image.open(BytesIO(resp.content)).convert("RGB")
            img = img.resize((W, H), Image.BILINEAR)
            img.save(str(cache_path), quality=92)
            print(f"  Background downloaded ({img.size})")
            return img
        except Exception as e:
            print(f"  Pollinations attempt {attempt}/2 failed: {e}")
            if attempt < 2:
                import time; time.sleep(5)
    print("  Using gradient fallback")
    return None


def make_gradient_bg(theme):
    base = Image.new("RGBA",(W,H), (*theme["bg"], 255))
    glow = theme["glow"]
    for i in range(30, 0, -1):
        ov = Image.new("RGBA",(W,H),(0,0,0,0))
        d  = ImageDraw.Draw(ov)
        alpha = int(60*(i/30)**2)
        r = int(500*i/30)
        x,y = W//2, int(H*0.3)
        d.ellipse([x-r,y-r,x+r,y+r], fill=(*glow, alpha))
        base = Image.alpha_composite(base, ov)
    ov2 = Image.new("RGBA",(W,H),(0,0,0,0))
    d2  = ImageDraw.Draw(ov2)
    accent = theme["accent"]
    for i in range(20, 0, -1):
        a = int(40*(i/20)**2)
        r = int(350*i/20)
        d2.ellipse([W//2-r,int(H*0.7)-r,W//2+r,int(H*0.7)+r], fill=(*accent, a))
    base = Image.alpha_composite(base, ov2)
    return base.convert("RGB")


def prepare_background(topic_id, theme_idx, theme):
    """Get AI bg — keep it vibrant, just slightly darkened for text."""
    ai_bg = fetch_ai_background(topic_id, theme_idx, theme)

    if ai_bg is None:
        return make_gradient_bg(theme)

    from PIL import ImageEnhance
    ai_bg = ImageEnhance.Brightness(ai_bg).enhance(0.55)
    ai_bg = ImageEnhance.Color(ai_bg).enhance(1.2)
    ai_bg = ImageEnhance.Contrast(ai_bg).enhance(1.1)
    return ai_bg


# ── Engaging card backgrounds (Fable 5 style) ─────────────────────────────

def make_glass_card(w, h, theme, radius=44, tint_alpha=140):
    """True glassmorphism — semi-transparent so AI background glows through."""
    card = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    cd = ImageDraw.Draw(card)
    accent = theme["accent"]

    # Semi-transparent dark base — shows background through
    cd.rounded_rectangle([0, 0, w, h], radius, fill=(10, 8, 20, tint_alpha))

    # Bright shimmer at top (glass reflection)
    for i in range(min(h // 5, 120)):
        a = int(45 * (1 - i / (h // 5)) ** 2)
        cd.line([(radius, i), (w - radius, i)], fill=(255, 255, 255, a))

    # Glowing accent border
    for thickness in range(3, 0, -1):
        border_a = int(255 * (thickness / 3) ** 2)
        cd.rounded_rectangle([thickness, thickness, w - thickness, h - thickness],
                              max(1, radius - thickness),
                              outline=(*accent, border_a), width=1)
    return card


def make_gradient_card(w, h, theme, radius=44):
    """Glass card with accent-colored top glow — shows background through."""
    accent = theme["accent"]

    # Semi-transparent base
    base = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    bd = ImageDraw.Draw(base)
    bd.rounded_rectangle([0, 0, w, h], radius, fill=(8, 6, 18, 150))

    # Accent glow at top portion
    for y in range(min(h // 2, 300)):
        t = y / (h // 2)
        a = int(80 * (1 - t) ** 2)
        r, g, b = accent
        base.putpixel((0, y), (r, g, b, a))  # temp placeholder

    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ovd = ImageDraw.Draw(ov)
    for y in range(min(h // 2, 300)):
        t = y / (h // 2)
        a = int(90 * (1 - t) ** 2)
        ovd.line([(radius, y), (w - radius, y)], fill=(*accent, a))

    base = Image.alpha_composite(base, ov)

    # Bright border
    bd2 = ImageDraw.Draw(base)
    for i in range(3, 0, -1):
        ba = int(255 * (i / 3) ** 2)
        bd2.rounded_rectangle([i, i, w - i, h - i], max(1, radius - i),
                               outline=(*accent, ba), width=1)

    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w, h], radius, fill=255)
    base.putalpha(mask)
    return base


def make_neon_card(w, h, theme, radius=44):
    """Translucent card with bright neon glow border."""
    card = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    cd = ImageDraw.Draw(card)
    accent = theme["accent"]

    # Semi-transparent base — background glows through
    cd.rounded_rectangle([0, 0, w, h], radius, fill=(5, 5, 15, 160))

    # Neon glow layers — bright
    for i in range(12, 0, -1):
        a = int(100 * (i / 12) ** 2)
        cd.rounded_rectangle([i, i, w - i, h - i], max(1, radius - i),
                              outline=(*accent, a), width=2)

    # Bright solid inner border
    cd.rounded_rectangle([2, 2, w - 2, h - 2], radius - 2,
                          outline=(*accent, 255), width=2)

    # Corner glow dots
    dot_r = 8
    for cx, cy in [(radius, radius), (w-radius, radius), (radius, h-radius), (w-radius, h-radius)]:
        for dr in range(dot_r, 0, -2):
            da = int(200 * (dr / dot_r) ** 2)
            cd.ellipse([cx-dr, cy-dr, cx+dr, cy+dr], fill=(*accent, da))

    return card


def paste_card(img, card, x, y):
    """Alpha-composite a card onto img at position (x, y)."""
    base = img.convert("RGBA")
    base.paste(card, (x, y), card)
    return base.convert("RGB")


# ── Easing & helpers ───────────────────────────────────────────────────────
def ease_out(t): return 1-(1-max(0,min(1,t)))**3
def blend_c(c1, c2, t): return tuple(int(a+(b-a)*max(0,min(1,t))) for a,b in zip(c1,c2))

def draw_glow_overlay(base_img, cx, cy, radius, color, layers=8):
    ov = Image.new("RGBA",(W,H),(0,0,0,0))
    d  = ImageDraw.Draw(ov)
    for i in range(layers,0,-1):
        a = int(40*(i/layers)**2)
        r = int(radius*i/layers*1.5)
        d.ellipse([cx-r,cy-r,cx+r,cy+r], fill=(*color,a))
    return Image.alpha_composite(base_img.convert("RGBA"), ov).convert("RGB")

def rrect(draw, xy, r, fill, outline=None, width=0):
    draw.rounded_rectangle(xy, radius=r, fill=fill, outline=outline, width=width)

def wrap_text(text, font, max_w):
    avg = max(1, int(font.getlength("A")))
    cpl = max(1, int(max_w/avg))
    lines = []
    for para in strip_emoji(text).split("\n"):
        lines.extend(textwrap.wrap(para, width=cpl) or [""])
    return lines

def line_height(font, gap=12):
    bb = font.getbbox("Ag")
    return (bb[3]-bb[1]) + gap

def text_block_h(lines, font, gap=12):
    return line_height(font,gap)*len(lines)

def draw_text_shadow(draw, xy, text, font, fill, shadow_color=(0,0,0), shadow_offset=3):
    sx, sy = xy
    for dx in range(-shadow_offset, shadow_offset+1):
        for dy in range(-shadow_offset, shadow_offset+1):
            if dx == 0 and dy == 0:
                continue
            draw.text((sx+dx, sy+dy), text, font=font, fill=shadow_color)
    draw.text(xy, text, font=font, fill=fill)

def draw_reveal(draw, lines, y, font, color, t, gap=14, delay_per_line=0.12, reveal_dur=0.18):
    lh = line_height(font, gap)
    for i,line in enumerate(lines):
        start = i*delay_per_line
        a = ease_out((t-start)/reveal_dur)
        if a <= 0: continue
        alpha = int(255 * a)
        c = (*color[:3], alpha) if len(color) == 4 else color
        offset = int((1-a)*30)
        lw = int(font.getlength(line))
        x  = (W-lw)//2
        draw_text_shadow(draw, (x, y+i*lh-offset), line, font, c, shadow_offset=4)

def apply_fade(img, alpha):
    if alpha >= 1.0: return img
    black = Image.new("RGB",(W,H),(0,0,0))
    return Image.blend(black, img, max(0,min(1,alpha)))

def draw_follow_badge(img, handle, theme, t, position="bottom"):
    """Animated 'Follow @handle' branded badge on every slide."""
    draw = ImageDraw.Draw(img)
    a = ease_out(min(1, max(0, (t - 0.3) * 3)))
    if a <= 0:
        return img

    label = f"Follow {handle}"
    f_icon = fnt(FONT_BOLD, 32)
    f_text = fnt(FONT_MED, 30)
    icon_txt = "▶"
    icon_w = int(f_icon.getlength(icon_txt))
    label_w = int(f_text.getlength(label))
    total_w = icon_w + 12 + label_w
    pad_x, pad_y = 24, 14

    if position == "bottom":
        bx = (W - total_w) // 2 - pad_x
        by = H - 130
    else:
        bx = W - total_w - pad_x * 2 - 20
        by = 30

    pulse = math.sin(t * math.pi * 3) * 0.15 + 0.85
    badge_alpha = int(200 * a * pulse)

    badge = Image.new("RGBA", (total_w + pad_x * 2, pad_y * 2 + 40), (0, 0, 0, 0))
    bd = ImageDraw.Draw(badge)
    accent = theme["accent"]
    bd.rounded_rectangle(
        [0, 0, total_w + pad_x * 2, pad_y * 2 + 40], 24,
        fill=(*accent, badge_alpha),
    )

    icon_c = (255, 255, 255, int(255 * a))
    bd.text((pad_x, pad_y + 2), icon_txt, font=f_icon, fill=icon_c)
    bd.text((pad_x + icon_w + 12, pad_y + 4), label, font=f_text, fill=icon_c)

    img_rgba = img.convert("RGBA")
    img_rgba.paste(badge, (bx, by), badge)
    return img_rgba.convert("RGB")


def apply_ken_burns(img, t, zoom_in=True, strength=0.08):
    """Slow cinematic zoom in or out (Ken Burns effect)."""
    if zoom_in:
        scale = 1.0 + strength * ease_out(t)
    else:
        scale = 1.0 + strength * (1.0 - ease_out(t))
    new_w = int(W * scale)
    new_h = int(H * scale)
    resized = img.resize((new_w, new_h), Image.BILINEAR)
    left = (new_w - W) // 2
    top  = (new_h - H) // 2
    return resized.crop((left, top, left + W, top + H))


# ── VFX Effects ───────────────────────────────────────────────────────────

_particles = None

def _init_particles(n=35):
    global _particles
    rng = random.Random(42)
    _particles = []
    for _ in range(n):
        _particles.append({
            "x": rng.randint(0, W),
            "y": rng.randint(0, H),
            "r": rng.uniform(2, 8),
            "speed": rng.uniform(40, 120),
            "drift": rng.uniform(-20, 20),
            "phase": rng.uniform(0, math.pi * 2),
            "brightness": rng.uniform(0.4, 1.0),
        })

def draw_particles(img, theme, t, intensity=1.0):
    if _particles is None:
        _init_particles()
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    accent = theme["accent"]
    for p in _particles:
        px = (p["x"] + p["drift"] * t * 3) % W
        py = (p["y"] - p["speed"] * t * 3) % H
        pulse = (math.sin(t * math.pi * 4 + p["phase"]) * 0.3 + 0.7)
        alpha = int(120 * p["brightness"] * pulse * intensity)
        r = p["r"] * (0.8 + pulse * 0.4)
        glow_r = r * 3
        d.ellipse([px - glow_r, py - glow_r, px + glow_r, py + glow_r],
                  fill=(*accent, int(alpha * 0.2)))
        d.ellipse([px - r, py - r, px + r, py + r],
                  fill=(255, 255, 255, alpha))
    return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")


def draw_light_sweep(img, t, color=(255, 255, 255), width=120):
    if t < 0 or t > 1:
        return img
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    sweep_x = int(-width + (W + width * 2) * ease_out(t))
    for i in range(width, 0, -2):
        a = int(35 * (i / width) ** 2)
        x = sweep_x + (width - i)
        d.line([(x, 0), (x - H // 3, H)], fill=(*color[:3], a), width=3)
    return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")


def draw_pulse_ring(img, cx, cy, t, color, max_r=200):
    if t < 0 or t > 1:
        return img
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    r = int(max_r * ease_out(t))
    alpha = int(180 * (1 - t))
    thickness = max(2, int(6 * (1 - t)))
    if r > 4 and alpha > 5:
        d.ellipse([cx - r, cy - r, cx + r, cy + r],
                  outline=(*color[:3], alpha), width=thickness)
        r2 = int(r * 0.7)
        a2 = int(alpha * 0.5)
        if r2 > 4:
            d.ellipse([cx - r2, cy - r2, cx + r2, cy + r2],
                      outline=(*color[:3], a2), width=max(1, thickness - 1))
    return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")


def draw_text_slam(draw, text, font, y_target, t, color=(255, 255, 255)):
    if t <= 0:
        return
    lw = int(font.getlength(text))
    x = (W - lw) // 2
    if t < 0.3:
        p = ease_out(t / 0.3)
        scale = 2.0 - 1.0 * p
        alpha_val = p
        y = y_target - int(80 * (1 - p))
    elif t < 0.45:
        shake_t = (t - 0.3) / 0.15
        shake = int(4 * math.sin(shake_t * math.pi * 6) * (1 - shake_t))
        x += shake
        scale = 1.0
        alpha_val = 1.0
        y = y_target
    else:
        scale = 1.0
        alpha_val = 1.0
        y = y_target
    if alpha_val > 0:
        draw_text_shadow(draw, (x, y), text, font, color, shadow_offset=5)


def draw_shimmer_line(img, y, t, theme, width_pct=0.6):
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    line_w = int(W * width_pct)
    x_start = (W - line_w) // 2
    shimmer_x = x_start + int(line_w * ((t * 2) % 1.0))
    for i in range(60, 0, -1):
        a = int(50 * (i / 60) ** 2)
        sx = shimmer_x + (60 - i) - 30
        if x_start <= sx <= x_start + line_w:
            d.line([(sx, y), (sx, y + 3)], fill=(*theme["accent"], a), width=2)
    d.line([(x_start, y), (x_start + line_w, y + 1)],
           fill=(*theme["accent"], 100), width=2)
    return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")


def draw_energy_border(img, t, theme, thickness=3):
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    accent = theme["accent"]
    progress = (t * 1.5) % 1.0
    perimeter = 2 * (W + H)
    glow_len = int(perimeter * 0.3)
    start = int(perimeter * progress)
    for i in range(glow_len):
        pos = (start + i) % perimeter
        fade = 1.0 - abs(i - glow_len / 2) / (glow_len / 2)
        a = int(120 * fade ** 2)
        if pos < W:
            px, py = pos, 0
        elif pos < W + H:
            px, py = W - 1, pos - W
        elif pos < 2 * W + H:
            px, py = W - 1 - (pos - W - H), H - 1
        else:
            px, py = 0, H - 1 - (pos - 2 * W - H)
        for t2 in range(thickness):
            dx = t2 if px == 0 else (-t2 if px >= W - 1 else 0)
            dy = t2 if py == 0 else (-t2 if py >= H - 1 else 0)
            d.point((px + dx, py + dy), fill=(*accent, a))
    return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")


# ── Slide renderers ────────────────────────────────────────────────────────

def make_cover_frame(bg, topic, theme, handle, t):
    """
    Dedicated cover / in-feed thumbnail slide (1.5 s, silent).
    Instagram uses the first video frame as the thumbnail; this ensures
    viewers see the hook text immediately rather than a blank background.
    All elements are fully visible from t=0 — no entrance animations.
    """
    # Boost brightness above the animated slides for maximum visual impact
    cover_bg = ImageEnhance.Brightness(bg).enhance(1.3)   # ~71 % of original vs 55 %
    cover_bg = ImageEnhance.Color(cover_bg).enhance(1.15)
    img = apply_ken_burns(cover_bg, 0.5, zoom_in=True, strength=0.06)  # fixed mid-zoom

    # Bottom-half gradient: improves text contrast without blacking out the top
    grad = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd   = ImageDraw.Draw(grad)
    for y in range(H // 3, H):
        a = int(180 * ((y - H // 3) / (H * 2 / 3)) ** 1.8)
        gd.line([(0, y), (W, y)], fill=(0, 0, 0, a))
    img = Image.alpha_composite(img.convert("RGBA"), grad).convert("RGB")

    # Accent glow behind the text area
    img = draw_glow_overlay(img, W // 2, H // 2 - 40, 380, theme["glow"], 10)

    # Particles + energy border for visual interest
    img = draw_particles(img, theme, t, intensity=1.0)
    img = draw_energy_border(img, t, theme, thickness=4)

    draw = ImageDraw.Draw(img)

    # ── Top pill ──────────────────────────────────────────────────────────
    pf   = fnt(FONT_MED, 46)
    ptxt = "GEN AI MASTER SERIES"
    pw   = int(pf.getlength(ptxt))
    rrect(draw, [(W-pw)//2-36, 108, (W+pw)//2+36, 108+70], 35, theme["accent"])
    draw.text(((W-pw)//2, 122), ptxt, font=pf, fill=(255, 255, 255))

    # ── Hook headline — fully visible, no animation ───────────────────────
    hook_font = fnt(FONT_BOLD, 108)
    lines  = wrap_text(topic["hook"], hook_font, W - 100)
    bh     = text_block_h(lines, hook_font, 28)
    base_y = H // 2 - bh // 2 - 60
    lh     = line_height(hook_font, 28)
    for i, line in enumerate(lines):
        lw = int(hook_font.getlength(line))
        draw_text_shadow(draw, ((W-lw)//2, base_y + i*lh),
                         line, hook_font, (255, 255, 255), shadow_offset=6)

    # ── Sub-tag line ──────────────────────────────────────────────────────
    sf   = fnt(FONT_MED, 46)
    stxt = "GenAI • Daily Education Reel"
    sw   = int(sf.getlength(stxt))
    draw_text_shadow(draw, ((W-sw)//2, base_y + bh + 28),
                     stxt, sf, theme["sub"], shadow_offset=3)

    # ── Shimmer accent line ───────────────────────────────────────────────
    img = draw_shimmer_line(img, base_y + bh + 100, t, theme, width_pct=0.55)
    draw = ImageDraw.Draw(img)

    # ── Handle button ─────────────────────────────────────────────────────
    pulse = math.sin(t * math.pi * 3) * 0.06 + 0.94
    hf    = fnt(FONT_BOLD, 62)
    hw    = int(hf.getlength(handle))
    hbx   = (W - hw) // 2 - 38
    img   = draw_glow_overlay(img, W//2, H-220, int(110*pulse), theme["accent"], 6)
    draw  = ImageDraw.Draw(img)
    rrect(draw, [hbx, H-274, hbx+hw+76, H-168], 34, theme["accent"])
    draw.text(((W-hw)//2, H-270), handle, font=hf, fill=(255, 255, 255))

    # ── "PLAY  TAP TO WATCH" nudge (ASCII-safe — Poppins has no ▶ glyph) ──
    nf   = fnt(FONT_MED, 38)
    ntxt = "PLAY  TAP TO WATCH"
    nw   = int(nf.getlength(ntxt))
    draw_text_shadow(draw, ((W-nw)//2, H-310), ntxt, nf, theme["bright"], shadow_offset=2)

    return img


def make_hook_frame(bg, topic, theme, handle, t, slide_idx=0, total_slides=7):
    img  = apply_ken_burns(bg, t, zoom_in=True, strength=0.12)
    pulse = math.sin(t*math.pi*2)*0.5+0.5
    img  = draw_glow_overlay(img, W//2, int(H*0.28+pulse*15), 350, theme["glow"], 10)

    # Subtle tinted overlay — not pure black
    accent = theme["accent"]
    bg = theme["bg"]
    ov_r = min(20, bg[0] + accent[0] // 10)
    ov_g = min(20, bg[1] + accent[1] // 10)
    ov_b = min(20, bg[2] + accent[2] // 10)
    ov = Image.new("RGBA",(W,H),(ov_r, ov_g, ov_b, 110))
    img = Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")

    # Floating particles
    img = draw_particles(img, theme, t, intensity=0.8)

    # Light sweep across screen (first 60% of slide)
    sweep_t = (t - 0.05) / 0.55
    img = draw_light_sweep(img, sweep_t, color=theme["accent"])

    # Energy border
    img = draw_energy_border(img, t, theme, thickness=3)

    draw = ImageDraw.Draw(img)

    # Series pill — slides down
    pill_y = int(-80 + ease_out(min(1,t*3))*220)
    pf     = fnt(FONT_MED, 44)
    ptxt   = "GEN AI MASTER SERIES"
    pw     = int(pf.getlength(ptxt))
    rrect(draw,[(W-pw)//2-32,pill_y,(W+pw)//2+32,pill_y+66],33,theme["accent"])
    draw.text(((W-pw)//2,pill_y+12),ptxt,font=pf,fill=(255,255,255))

    # Hook text — slam effect (zooms in and shakes)
    hook_font = fnt(FONT_BOLD, 110)
    lines = wrap_text(topic["hook"], hook_font, W-100)
    bh    = text_block_h(lines, hook_font, 28)
    base_y = H//2 - bh//2

    slam_t = max(0, (t - 0.08))
    for i, line in enumerate(lines):
        line_t = max(0, slam_t - i * 0.12)
        if line_t <= 0:
            continue
        lw = int(hook_font.getlength(line))
        lx = (W - lw) // 2
        ly = base_y + i * line_height(hook_font, 28)
        if line_t < 0.15:
            p = ease_out(line_t / 0.15)
            ly = ly - int(60 * (1 - p))
        elif line_t < 0.25:
            shake = int(3 * math.sin((line_t - 0.15) / 0.10 * math.pi * 8) * (1 - (line_t - 0.15) / 0.10))
            lx += shake
        draw_text_shadow(draw, (lx, ly), line, hook_font, (255,255,255), shadow_offset=5)

    # Pulse ring on text reveal
    ring_t = max(0, (t - 0.20)) * 2.5
    if ring_t > 0:
        img = draw_pulse_ring(img, W // 2, H // 2, min(1, ring_t), theme["accent"], max_r=300)
        draw = ImageDraw.Draw(img)

    # Progress bar
    rrect(draw,[40,H-58,W-40,H-50],4,(30,30,50))
    rrect(draw,[40,H-58,40+int((W-80)*(slide_idx+1)/total_slides),H-50],4,theme["accent"])

    img = draw_follow_badge(img, handle, theme, t)
    return img


def make_title_frame(bg, topic, theme, handle, t, slide_idx=1, total_slides=7, static_card=None):
    img  = apply_ken_burns(bg, t, zoom_in=False)
    img  = draw_glow_overlay(img, W//2, H//3, 300, theme["glow"], 8)

    card = static_card if static_card is not None else make_glass_card(W-60, int(H*0.55), theme, radius=44, tint_alpha=190)
    img  = paste_card(img, card, 30, int(H*0.22))

    img = draw_particles(img, theme, t, intensity=0.5)

    draw = ImageDraw.Draw(img)

    lf   = fnt(FONT_BOLD,46)
    lt   = "TODAY'S LESSON"
    lw   = int(lf.getlength(lt))
    draw_text_shadow(draw, ((W-lw)//2,int(H*0.28)), lt, lf, theme["accent"])

    bw = int(160*ease_out(min(1,max(0,(t-0.15)*4))))
    if bw>0: rrect(draw,[(W-bw)//2,int(H*0.28)+62,(W+bw)//2,int(H*0.28)+72],4,theme["accent"])

    # Shimmer line under label
    img = draw_shimmer_line(img, int(H*0.28)+72, t, theme, width_pct=0.3)
    draw = ImageDraw.Draw(img)

    title_font = fnt(FONT_BOLD, 110)
    lines  = wrap_text(topic["title"], title_font, W-180)
    bh     = text_block_h(lines, title_font, 24)
    draw_reveal(draw, lines, H//2-bh//2-20, title_font, (255,255,255),
                max(0,(t-0.2)), delay_per_line=0.10, reveal_dur=0.18, gap=24)

    df   = fnt(FONT_REG,40)
    dtxt = datetime.date.today().strftime('%b %d, %Y')
    dw   = int(df.getlength(dtxt))
    da   = ease_out(min(1,max(0,(t-0.5)*3)))
    draw_text_shadow(draw, ((W-dw)//2,int(H*0.68)), dtxt, df,
                     blend_c((0,0,0),theme["sub"],da))

    rrect(draw,[40,H-58,W-40,H-50],4,(30,30,50))
    rrect(draw,[40,H-58,40+int((W-80)*(slide_idx+1)/total_slides),H-50],4,theme["accent"])

    img = draw_follow_badge(img, handle, theme, t)
    return img


def make_point_frame(bg, topic, theme, handle, idx, t, total, slide_idx=2, total_slides=7, static_card=None):
    img  = apply_ken_burns(bg, t, zoom_in=(idx % 2 == 0))
    pulse = math.sin(t*math.pi*1.5)*0.5+0.5
    cx,cy = W//2, 350
    img  = draw_glow_overlay(img, cx, cy, int(130+pulse*20), theme["glow"], 8)

    img = draw_particles(img, theme, t + idx * 0.5, intensity=0.4)

    draw = ImageDraw.Draw(img)

    # Number circle
    s = ease_out(min(1,t*5))
    r = int(120*s)
    if r>4:
        draw.ellipse([cx-r,cy-r,cx+r,cy+r],fill=theme["accent"])
        nf  = fnt(FONT_BOLD,int(100*s))
        nt  = str(idx+1)
        nw  = int(nf.getlength(nt)); nb = nf.getbbox(nt)
        draw.text((cx-nw//2,cy-nb[3]//2-nb[1]),nt,font=nf,fill=(255,255,255))

    # Pulse ring when number appears
    ring_t = max(0, t * 4 - 0.5)
    if 0 < ring_t < 1:
        img = draw_pulse_ring(img, cx, cy, ring_t, theme["accent"], max_r=200)
        draw = ImageDraw.Draw(img)

    cf   = fnt(FONT_BOLD,44)
    ctxt = f"of {total}"
    cw   = int(cf.getlength(ctxt))
    ca   = ease_out(min(1,max(0,(t-0.12)*4)))
    draw_text_shadow(draw, ((W-cw)//2,500), ctxt, cf, blend_c((0,0,0),theme["sub"],ca))

    # Gradient card — slides up; crop pre-built card to visible height each frame
    ct     = ease_out(min(1, max(0, (t-0.1)*3)))
    cy2    = int(620 + (1-ct)*200)
    card_h = H - cy2 - 120   # visible height (grows as card slides up)
    if static_card is not None:
        # Cheap crop: no pixel redraw, just adjusts the bounding box
        visible = static_card.crop((0, 0, static_card.size[0], min(card_h, static_card.size[1])))
        img = paste_card(img, visible, 30, cy2)
    else:
        card = make_gradient_card(W-60, card_h, theme, radius=44)
        img  = paste_card(img, card, 30, cy2)
    draw = ImageDraw.Draw(img)

    # Point text — big and bold
    pt    = strip_emoji(topic["points"][idx])
    pt_font = fnt(FONT_BOLD, 100)
    lines = wrap_text(pt, pt_font, W-180)
    bh    = text_block_h(lines, pt_font, 22)
    mid_y = cy2 + card_h//2 - bh//2
    draw_reveal(draw, lines, mid_y, pt_font, (255,255,255),
                max(0,(t-0.25)), delay_per_line=0.12, reveal_dur=0.18, gap=22)

    rrect(draw,[40,H-58,W-40,H-50],4,(30,30,50))
    rrect(draw,[40,H-58,40+int((W-80)*(slide_idx+1)/total_slides),H-50],4,theme["accent"])

    img = draw_follow_badge(img, handle, theme, t)
    return img


def make_cta_frame(bg, topic, theme, handle, t, slide_idx=6, total_slides=7, static_card=None):
    img  = apply_ken_burns(bg, t, zoom_in=True, strength=0.10)
    pulse = math.sin(t*math.pi*2)*0.5+0.5
    img  = draw_glow_overlay(img, W//2, H//2, int(250+pulse*50), theme["accent"], 10)

    card = static_card if static_card is not None else make_neon_card(W-40, int(H*0.75), theme, radius=50)
    img  = paste_card(img, card, 20, int(H*0.10))

    # Heavy particles + energy border on CTA
    img = draw_particles(img, theme, t, intensity=1.2)
    img = draw_energy_border(img, t, theme, thickness=4)

    draw = ImageDraw.Draw(img)

    tf   = fnt(FONT_BOLD,64)
    ttxt = "FOLLOW FOR MORE"
    tw   = int(tf.getlength(ttxt))
    ta   = ease_out(min(1,t*4))
    draw_text_shadow(draw, ((W-tw)//2,int(H*0.16)), ttxt, tf,
                     blend_c((0,0,0),theme["accent"],ta))

    bw = int(160*ease_out(min(1,max(0,(t-0.12)*4))))
    if bw>0: rrect(draw,[(W-bw)//2,int(H*0.16)+76,(W+bw)//2,int(H*0.16)+86],4,theme["accent"])

    # Shimmer under "FOLLOW FOR MORE"
    img = draw_shimmer_line(img, int(H*0.16)+86, t, theme, width_pct=0.4)
    draw = ImageDraw.Draw(img)

    cta_font = fnt(FONT_BOLD, 96)
    lines  = wrap_text(topic["cta"], cta_font, W-160)
    bh     = text_block_h(lines, cta_font, 22)
    draw_reveal(draw, lines, H//2-bh//2-60, cta_font, (255,255,255),
                max(0,(t-0.2)), delay_per_line=0.12, reveal_dur=0.18, gap=22)

    tags  = [h for h in topic["hashtags"].split() if h.startswith("#")][:5]
    tstr  = "  ".join(tags)
    xf    = fnt(FONT_MED,38)
    xw    = int(xf.getlength(tstr))
    xa    = ease_out(min(1,max(0,(t-0.4)*3)))
    draw_text_shadow(draw, ((W-xw)//2,int(H*0.70)), tstr, xf,
                     blend_c((0,0,0),theme["sub"],xa))

    # Handle button — big and glowing
    hf  = fnt(FONT_BOLD,64)
    hw  = int(hf.getlength(handle))
    hbx = (W-hw)//2-40
    img  = draw_glow_overlay(img, W//2, H-220, int(120+pulse*30), theme["accent"], 6)
    draw = ImageDraw.Draw(img)
    rrect(draw,[hbx,H-280,hbx+hw+80,H-170],36,theme["accent"])
    hbt = ease_out(min(1,max(0,(t-0.5)*3)))
    draw.text(((W-hw)//2,H-275),handle,font=hf,fill=blend_c(theme["bg"],(255,255,255),hbt))

    # Pulse ring on handle button
    ring_t = max(0, (t - 0.55)) * 3
    if 0 < ring_t < 1:
        img = draw_pulse_ring(img, W // 2, H - 225, ring_t, theme["accent"], max_r=160)
        draw = ImageDraw.Draw(img)

    rrect(draw,[40,H-58,W-40,H-50],4,(30,30,50))
    rrect(draw,[40,H-58,40+int((W-80)*(slide_idx+1)/total_slides),H-50],4,theme["accent"])
    return img


# ── Render slide ──────────────────────────────────────────────────────────
def render_slide(bg, frame_fn, duration_s, fade_in=0.18, fade_out=0.18):
    n = int(duration_s*FPS)
    frames = []
    for i in range(n):
        t   = i/max(1,n-1)
        img = frame_fn(bg, t)
        fi  = i/(fade_in*FPS) if i<fade_in*FPS else 1.0
        fo  = (n-1-i)/(fade_out*FPS) if (n-1-i)<fade_out*FPS else 1.0
        frames.append(apply_fade(img, min(fi,fo)))
    return frames


# ── TTS Voiceover ─────────────────────────────────────────────────────────
VOICE = "en-US-AndrewMultilingualNeural"


def get_audio_duration(path):
    """Return duration in seconds via ffprobe, or None on failure."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(path)],
            capture_output=True, text=True, timeout=10,
        )
        return float(json.loads(r.stdout)["format"]["duration"])
    except Exception as e:
        print(f"  Could not measure audio duration: {e}")
        return None


def generate_segment_voiceovers(topic, seg_dir):
    """Generate one MP3 per slide in parallel.
    Returns list of (Path|None, duration_s) in slide order:
    [hook, title, point0..N, cta]
    """
    try:
        import edge_tts
    except ImportError:
        print("  edge-tts not installed, skipping voiceover")
        return None

    slide_scripts = [
        ("hook",  strip_emoji(topic["hook"].replace("\n", ". "))),
        ("title", strip_emoji(topic["title"])),
    ]
    for i, p in enumerate(topic["points"]):
        slide_scripts.append((f"point{i}", strip_emoji(p)))
    slide_scripts.append(("cta", strip_emoji(topic["cta"])))

    print(f"  Generating {len(slide_scripts)} voiceover segments...")

    async def _gen_all():
        coros = []
        for name, text in slide_scripts:
            if text.strip():
                out = seg_dir / f"seg_{name}.mp3"
                comm = edge_tts.Communicate(text, VOICE, rate="+0%", pitch="+2Hz")
                coros.append(comm.save(str(out)))
        await asyncio.gather(*coros)

    asyncio.run(_gen_all())

    results = []
    for name, _ in slide_scripts:
        out = seg_dir / f"seg_{name}.mp3"
        if out.exists() and out.stat().st_size > 0:
            dur = get_audio_duration(out) or 2.0
            results.append((out, dur))
            print(f"    {name}: {dur:.1f}s")
        else:
            print(f"    {name}: MISSING — using 2.0s default")
            results.append((None, 2.0))
    return results


def concatenate_audio_segments(segments, slide_durs, output_path):
    """
    Pad each TTS segment to its exact slide duration, then concatenate.

    segments  : list of (path_or_None, tts_dur_s) — one per slide
    slide_durs: list of floats — final video duration for each slide
    output_path: destination MP3

    Each segment is padded with silence to whole_dur=slide_dur (via apad),
    then trimmed to that same value so any overshoot is removed.
    Missing segments (path=None) become pure silence via anullsrc.
    """
    assert len(segments) == len(slide_durs), (
        f"segments len {len(segments)} != slide_durs len {len(slide_durs)}"
    )

    cmd          = ["ffmpeg", "-y"]
    filter_parts = []
    idx          = 0   # ffmpeg input index

    for i, ((path, _), dur) in enumerate(zip(segments, slide_durs)):
        d = f"{dur:.4f}"
        if path and Path(path).exists():
            cmd += ["-i", str(path)]
            # apad fills silence up to whole_dur; atrim removes any rare overshoot
            filter_parts.append(
                f"[{idx}:a]apad=whole_dur={d},atrim=duration={d}[a{i}]"
            )
        else:
            # Pure silence — lavfi anullsrc needs no real file
            cmd += ["-f", "lavfi", "-i", f"anullsrc=r=24000:cl=mono"]
            filter_parts.append(
                f"[{idx}:a]atrim=duration={d}[a{i}]"
            )
        idx += 1

    n          = len(segments)
    concat_in  = "".join(f"[a{i}]" for i in range(n))
    filter_parts.append(f"{concat_in}concat=n={n}:v=0:a=1[outa]")

    cmd += [
        "-filter_complex", ";".join(filter_parts),
        "-map", "[outa]",
        "-c:a", "libmp3lame", "-b:a", "192k",
        str(output_path),
    ]

    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        print("ffmpeg pad+concat error:", r.stderr[-500:])
        return None

    # Sanity-check: total audio should equal total video (±0.1 s)
    actual   = get_audio_duration(output_path)
    expected = sum(slide_durs)
    if actual is not None:
        drift = actual - expected
        if abs(drift) > 0.1:
            print(f"  WARNING audio drift {drift:+.2f}s "
                  f"(got {actual:.2f}s, expected {expected:.2f}s)")
        else:
            print(f"  Audio {actual:.2f}s == video {expected:.2f}s ✓")

    return Path(output_path)


def _find_music():
    """Return first MP3/M4A/WAV in assets/music/, or None."""
    music_dir = REPO_ROOT / "assets" / "music"
    if not music_dir.exists():
        return None
    for pat in ("*.mp3", "*.m4a", "*.wav"):
        files = sorted(music_dir.glob(pat))
        if files:
            return files[0]
    return None


# ── Build video ────────────────────────────────────────────────────────────
def build_video(all_frames, output_path, voiceover_path=None):
    for f in FRAMES.glob("*.png"):
        try: f.unlink()
        except: pass
    print(f"  Saving {len(all_frames)} frames...")
    for i, img in enumerate(all_frames):
        img.save(str(FRAMES / f"f{i:05d}.png"))

    if voiceover_path and Path(voiceover_path).exists():
        silent_path = Path("/tmp/reel_silent.mp4")
        cmd_silent = [
            "ffmpeg", "-y", "-framerate", str(FPS),
            "-i", str(FRAMES / "f%05d.png"),
            "-vf", "scale=1080:1920,format=yuv420p",
            "-c:v", "libx264", "-preset", "fast", "-crf", "22", "-r", str(FPS),
            str(silent_path),
        ]
        r = subprocess.run(cmd_silent, capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            print("ffmpeg silent video error:", r.stderr[-500:])
            raise RuntimeError("ffmpeg failed (silent)")

        print("  Merging + normalising audio...")
        music = _find_music()
        if music:
            print(f"  Mixing background music: {music.name}")
            af = ("[1:a]loudnorm=I=-14:TP=-2:LRA=7[voice];"
                  "[2:a]volume=-20dB,aloop=loop=-1:size=2e+09[music];"
                  "[voice][music]amix=inputs=2:duration=first,aformat=channel_layouts=stereo[outa]")
            cmd_merge = [
                "ffmpeg", "-y",
                "-i", str(silent_path), "-i", str(voiceover_path), "-i", str(music),
                "-filter_complex", af,
                "-map", "0:v", "-map", "[outa]",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                "-movflags", "+faststart", str(output_path),
            ]
        else:
            cmd_merge = [
                "ffmpeg", "-y",
                "-i", str(silent_path), "-i", str(voiceover_path),
                "-filter_complex", "[1:a]loudnorm=I=-14:TP=-2:LRA=7,aformat=channel_layouts=stereo[outa]",
                "-map", "0:v", "-map", "[outa]",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                "-movflags", "+faststart", str(output_path),
            ]
        r = subprocess.run(cmd_merge, capture_output=True, text=True, timeout=180)
        if r.returncode != 0:
            print("ffmpeg merge error:", r.stderr[-500:])
            print("  Falling back to video without audio")
            shutil.copy2(str(silent_path), str(output_path))
        try: silent_path.unlink()
        except: pass
    else:
        cmd = [
            "ffmpeg", "-y", "-framerate", str(FPS),
            "-i", str(FRAMES / "f%05d.png"),
            "-vf", "scale=1080:1920,format=yuv420p",
            "-c:v", "libx264", "-preset", "fast", "-crf", "22", "-r", str(FPS),
            "-movflags", "+faststart", str(output_path),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            print("ffmpeg error:", r.stderr[-1000:])
            raise RuntimeError("ffmpeg failed")
    return output_path


# ── Main ──────────────────────────────────────────────────────────────────
def _load_ai_topic():
    """Check for AI-generated topic from ai_content_generator.py."""
    ai_path = OUTDIR / "ai_topic.json"
    if not ai_path.exists():
        return None
    with open(ai_path) as f:
        return json.load(f)


def generate(topic_id=None):
    with open(TOPICS) as f: data = json.load(f)
    topics = data["topics"]
    handle = data.get("handle", "@agentwave.ai")

    ai_topic = None if topic_id else _load_ai_topic()

    if ai_topic:
        topic = ai_topic
        if topic.get("bg_prompt"):
            set_custom_bg_prompt(topic["bg_prompt"])
        print(f"  Using AI-generated topic: {topic['title']}")
    elif topic_id:
        topic = next((t for t in topics if t["id"] == int(topic_id)), topics[0])
    else:
        tracker = {}
        if TRACKER.exists():
            with open(TRACKER) as f: tracker = json.load(f)
        used      = set(tracker.get("used", []))
        last_id   = tracker.get("last_id", 0)
        remaining = [t for t in topics if t["id"] not in used]
        if not remaining: used = set(); remaining = topics
        remaining.sort(key=lambda t: t["id"])
        topic = next((t for t in remaining if t["id"] > last_id), remaining[0])
        used.add(topic["id"])
        with open(TRACKER, "w") as f:
            json.dump({"last_id": topic["id"], "used": list(used),
                       "last_date": str(datetime.date.today())}, f, indent=2)

    theme_idx    = topic["id"] % len(THEMES)
    theme        = THEMES[theme_idx]
    npts         = len(topic["points"])
    COVER_DUR    = 1.5                      # silent cover / thumbnail slide
    # total_slides: cover + hook + title + N points + cta
    total_slides = 3 + npts + 1

    print(f"\n Animating Reel: #{topic['id']} — {topic['title']}")

    bg = prepare_background(topic["id"], theme_idx, theme)

    # ── Per-slide voiceover (generated first to drive timing) ─────────────
    # segments list covers hook..cta only (cover slide is silent)
    seg_dir   = Path("/tmp/reel_segs")
    seg_dir.mkdir(exist_ok=True)
    segments  = generate_segment_voiceovers(topic, seg_dir)
    n_content = 2 + npts + 1   # hook + title + points + cta

    PAD = 0.4   # silence padding after each segment
    if segments and len(segments) == n_content:
        hook_dur   = max(2.0, segments[0][1]           + PAD)
        title_dur  = max(1.5, segments[1][1]           + PAD)
        point_durs = [max(2.0, segments[2+i][1] + PAD) for i in range(npts)]
        cta_dur    = max(2.5, segments[-1][1]          + PAD)
        total_dur  = COVER_DUR + hook_dur + title_dur + sum(point_durs) + cta_dur
        print(f"  Durations → cover:{COVER_DUR:.1f}s hook:{hook_dur:.1f}s "
              f"title:{title_dur:.1f}s pts:{[round(d,1) for d in point_durs]} "
              f"cta:{cta_dur:.1f}s total:{total_dur:.1f}s")
    else:
        hook_dur, title_dur = 2.5, 2.0
        point_durs = [3.0] * npts
        cta_dur    = 3.5

    # ── Pre-build static card layers (reused every frame, built once) ──────
    title_card = make_glass_card(W-60, int(H*0.55), theme, radius=44, tint_alpha=190)
    point_card = make_gradient_card(W-60, H-620-120,  theme, radius=44)
    cta_card   = make_neon_card(W-40,  int(H*0.75),  theme, radius=50)

    # ── Render slides ──────────────────────────────────────────────────────
    # Slide indices: 0=cover 1=hook 2=title 3..=points last=cta
    all_frames = []

    print(f"  Slide 1/{total_slides}: Cover ({COVER_DUR:.1f}s) [thumbnail]")
    all_frames += render_slide(
        bg, lambda b, t: make_cover_frame(b, topic, theme, handle, t),
        COVER_DUR, fade_in=0.0, fade_out=0.0)

    print(f"  Slide 2/{total_slides}: Hook ({hook_dur:.1f}s)")
    all_frames += render_slide(
        bg, lambda b, t: make_hook_frame(b, topic, theme, handle, t, 1, total_slides),
        hook_dur, fade_in=0.0)

    print(f"  Slide 3/{total_slides}: Title ({title_dur:.1f}s)")
    all_frames += render_slide(
        bg, lambda b, t: make_title_frame(b, topic, theme, handle, t, 2, total_slides, title_card),
        title_dur)

    for i in range(npts):
        print(f"  Slide {i+4}/{total_slides}: Point {i+1} ({point_durs[i]:.1f}s)")
        ix = i; six = i + 3
        all_frames += render_slide(
            bg, lambda b, t, ix=ix, six=six: make_point_frame(
                b, topic, theme, handle, ix, t, npts, six, total_slides, point_card),
            point_durs[i])

    print(f"  Slide {total_slides}/{total_slides}: CTA ({cta_dur:.1f}s)")
    all_frames += render_slide(
        bg, lambda b, t: make_cta_frame(b, topic, theme, handle, t, 3+npts, total_slides, cta_card),
        cta_dur)

    print(f"  Total: {len(all_frames)} frames → {len(all_frames)/FPS:.1f}s")

    date_str  = datetime.date.today().strftime("%Y%m%d")
    out_path  = OUTDIR / f"reel_v2_{date_str}_topic{topic['id']}.mp4"

    # ── Concatenate per-slide segments, each padded to its slide duration ──
    # Prepend a silence slot for the cover; rest follows hook..cta order
    cover_seg  = (None, COVER_DUR)
    all_segs   = [cover_seg] + (segments or [])
    slide_durs = [COVER_DUR, hook_dur, title_dur] + point_durs + [cta_dur]
    vo_full    = Path("/tmp/reel_voiceover_full.mp3")
    voiceover  = concatenate_audio_segments(all_segs, slide_durs, vo_full) \
                 if segments else None

    build_video(all_frames, out_path, voiceover_path=voiceover)

    caption = topic.get("caption") or (
        f"{topic['title']}\n\n"
        + "\n".join(f"• {p}" for p in topic["points"])
        + f"\n\n{topic['cta']}\n\n{topic.get('hashtags','')}"
    )
    meta = {
        "video_path":    str(out_path),
        "caption":       caption,
        "topic_id":      topic["id"],
        "topic_title":   topic["title"],
        "generated_at":  datetime.datetime.now().isoformat(),
    }
    with open(OUTDIR / "latest_reel_meta.json", "w") as f:
        json.dump(meta, f, indent=2)
    print(f"\n Done! {out_path}")
    return str(out_path), meta


if __name__=="__main__":
    tid = sys.argv[1] if len(sys.argv)>1 else None
    generate(tid)
