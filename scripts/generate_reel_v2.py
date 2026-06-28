#!/usr/bin/env python3
"""
Instagram Reel Generator v2 — Animated + AI Backgrounds (Pollinations.ai)
- Free AI backgrounds via pollinations.ai (no API key needed)
- Text reveal animations (line by line)
- Fade in/out transitions
- Glowing accent elements
- 12 FPS smooth motion
"""

import os, sys, json, subprocess, textwrap, math, datetime, re, urllib.request, shutil
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
FPS   = 12

_FONT_SEARCH_DIRS = [
    "/usr/share/fonts/truetype/google-fonts",
    "/usr/share/fonts/truetype",
    "/usr/share/fonts",
    "/usr/local/share/fonts",
]

def _find_font(name):
    for d in _FONT_SEARCH_DIRS:
        p = os.path.join(d, name)
        if os.path.isfile(p):
            return p
    return None

FONT_BOLD  = _find_font("Poppins-Bold.ttf") or "Poppins-Bold.ttf"
FONT_MED   = _find_font("Poppins-Medium.ttf") or "Poppins-Medium.ttf"
FONT_REG   = _find_font("Poppins-Regular.ttf") or "Poppins-Regular.ttf"

def fnt(path, size):
    try:    return ImageFont.truetype(path, size)
    except: return ImageFont.load_default()

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
           f"{urllib.request.quote(prompt)}"
           f"?width=1080&height=1920&nologo=true&seed={topic_id*7+42}&enhance=true")
    print(f"  Fetching AI background: {prompt[:60]}...")
    try:
        import requests
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        img = Image.open(BytesIO(resp.content)).convert("RGB")
        img = img.resize((W, H), Image.LANCZOS)
        img.save(str(cache_path), quality=92)
        print(f"  Background downloaded ({img.size})")
        return img
    except Exception as e:
        print(f"  Pollinations unavailable ({e}), using gradient fallback")
        return None


def make_gradient_bg(theme):
    img = Image.new("RGB",(W,H), theme["bg"])
    draw = ImageDraw.Draw(img)
    # Radial-ish gradient via concentric ellipses
    glow = theme["glow"]
    for i in range(30, 0, -1):
        alpha = int(20*(i/30)**2)
        r = int(400*i/30)
        x,y = W//2, int(H*0.3)
        draw.ellipse([x-r,y-r,x+r,y+r], fill=(*glow, alpha))
    return img


def prepare_background(topic_id, theme_idx, theme):
    """Get AI bg, darken it, ready for text overlay."""
    ai_bg = fetch_ai_background(topic_id, theme_idx, theme)

    if ai_bg is None:
        return make_gradient_bg(theme)

    # Darken + desaturate to make text pop
    from PIL import ImageEnhance
    ai_bg = ImageEnhance.Brightness(ai_bg).enhance(0.35)
    ai_bg = ImageEnhance.Color(ai_bg).enhance(0.7)

    # Tint overlay with theme color
    tint = Image.new("RGB",(W,H), theme["bg"])
    ai_bg = Image.blend(ai_bg, tint, 0.45)
    return ai_bg


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

def draw_reveal(draw, lines, y, font, color, t, gap=12, delay_per_line=0.12, reveal_dur=0.18):
    lh = line_height(font, gap)
    for i,line in enumerate(lines):
        start = i*delay_per_line
        a = ease_out((t-start)/reveal_dur)
        if a <= 0: continue
        c = blend_c((0,0,0), color, a)
        # Slide up effect
        offset = int((1-a)*30)
        lw = int(font.getlength(line))
        x  = (W-lw)//2
        draw.text((x, y+i*lh-offset), line, font=font, fill=c)

def apply_fade(img, alpha):
    if alpha >= 1.0: return img
    black = Image.new("RGB",(W,H),(0,0,0))
    return Image.blend(black, img, max(0,min(1,alpha)))

def apply_ken_burns(img, t, zoom_in=True, strength=0.08):
    """Slow cinematic zoom in or out (Ken Burns effect)."""
    if zoom_in:
        scale = 1.0 + strength * ease_out(t)
    else:
        scale = 1.0 + strength * (1.0 - ease_out(t))
    new_w = int(W * scale)
    new_h = int(H * scale)
    resized = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - W) // 2
    top  = (new_h - H) // 2
    return resized.crop((left, top, left + W, top + H))


# ── Slide renderers ────────────────────────────────────────────────────────

def make_hook_frame(bg, topic, theme, handle, t):
    img  = apply_ken_burns(bg, t, zoom_in=True)
    pulse = math.sin(t*math.pi*2)*0.5+0.5
    img  = draw_glow_overlay(img, W//2, int(H*0.28+pulse*15), 350, theme["glow"], 10)
    draw = ImageDraw.Draw(img)

    # Series pill
    pill_y = int(-80 + ease_out(min(1,t*3))*220)
    pf     = fnt(FONT_MED, 34)
    ptxt   = "GEN AI MASTER SERIES"
    pw     = int(pf.getlength(ptxt))
    rrect(draw,[(W-pw)//2-28,pill_y,(W+pw)//2+28,pill_y+56],28,theme["accent"])
    draw.text(((W-pw)//2,pill_y+10),ptxt,font=pf,fill=(255,255,255))

    # Day badge
    t2 = ease_out(max(0,min(1,(t-0.08)*3)))
    cy = int(420+40*(1-t2))
    r  = int(100*t2)
    if r>5:
        img  = draw_glow_overlay(img, W//2, cy, r+30, theme["glow"], 6)
        draw = ImageDraw.Draw(img)
        draw.ellipse([W//2-r,cy-r,W//2+r,cy+r], fill=theme["accent"])
        nf = fnt(FONT_BOLD, int(80*t2))
        nt = str(topic["id"])
        nw = int(nf.getlength(nt)); nb = nf.getbbox(nt)
        draw.text((W//2-nw//2,cy-nb[3]//2-nb[1]),nt,font=nf,fill=(255,255,255))

    cf   = fnt(FONT_MED,38)
    ctxt = f"Day {topic['id']}"
    cw   = int(cf.getlength(ctxt))
    ca   = ease_out(min(1,max(0,(t-0.2)*4)))
    draw.text(((W-cw)//2,530+20),ctxt,font=cf,fill=blend_c((0,0,0),theme["sub"],ca))

    # Hook text
    lines = wrap_text(topic["hook"], fnt(FONT_BOLD,76), W-100)
    bh    = text_block_h(lines,fnt(FONT_BOLD,76),20)
    draw_reveal(draw,lines,H//2-bh//2+80,fnt(FONT_BOLD,76),(255,255,255),
                max(0,(t-0.22)),delay_per_line=0.10,reveal_dur=0.15)

    # Handle
    ha = ease_out(min(1,max(0,(t-0.65)/0.2)))
    hf = fnt(FONT_MED,36)
    hw = int(hf.getlength(handle))
    draw.text(((W-hw)//2,H-140),handle,font=hf,fill=blend_c((0,0,0),theme["sub"],ha))

    # Progress bar
    rrect(draw,[40,H-58,W-40,H-50],4,(30,30,50))
    rrect(draw,[40,H-58,40+int((W-80)*1/7),H-50],4,theme["accent"])
    return img


def make_title_frame(bg, topic, theme, handle, t):
    img  = apply_ken_burns(bg, t, zoom_in=False)
    img  = draw_glow_overlay(img, W//2, H//3, 300, theme["glow"], 8)
    draw = ImageDraw.Draw(img)

    # Frosted card
    card = Image.new("RGBA",(W-80,int(H*0.55)),(0,0,0,0))
    cd   = ImageDraw.Draw(card)
    cd.rounded_rectangle([0,0,W-80,int(H*0.55)],44,fill=(*theme["bg"],200))
    img_rgba = img.convert("RGBA")
    img_rgba.paste(card,(40,int(H*0.22)),card)
    img  = img_rgba.convert("RGB")
    draw = ImageDraw.Draw(img)

    lf   = fnt(FONT_MED,42)
    lt   = "TODAY'S LESSON"
    lw   = int(lf.getlength(lt))
    la   = ease_out(min(1,t*4))
    draw.text(((W-lw)//2,int(H*0.28)),lt,font=lf,fill=blend_c((0,0,0),theme["sub"],la))

    bw = int(120*ease_out(min(1,max(0,(t-0.15)*4))))
    if bw>0: rrect(draw,[(W-bw)//2,int(H*0.28)+58,(W+bw)//2,int(H*0.28)+68],4,theme["accent"])

    lines  = wrap_text(topic["title"],fnt(FONT_BOLD,84),W-180)
    bh     = text_block_h(lines,fnt(FONT_BOLD,84),20)
    draw_reveal(draw,lines,H//2-bh//2-20,fnt(FONT_BOLD,84),(255,255,255),
                max(0,(t-0.2)),delay_per_line=0.10,reveal_dur=0.18)

    df   = fnt(FONT_REG,38)
    dtxt = f"Day {topic['id']}  ·  {datetime.date.today().strftime('%b %d, %Y')}"
    dw   = int(df.getlength(dtxt))
    da   = ease_out(min(1,max(0,(t-0.5)*3)))
    draw.text(((W-dw)//2,int(H*0.68)),dtxt,font=df,fill=blend_c((0,0,0),theme["sub"],da))

    hf  = fnt(FONT_MED,36)
    hw  = int(hf.getlength(handle))
    ha  = ease_out(min(1,max(0,(t-0.65)*3)))
    draw.text(((W-hw)//2,H-140),handle,font=hf,fill=blend_c((0,0,0),theme["sub"],ha))

    rrect(draw,[40,H-58,W-40,H-50],4,(30,30,50))
    rrect(draw,[40,H-58,40+int((W-80)*2/7),H-50],4,theme["accent"])
    return img


def make_point_frame(bg, topic, theme, handle, idx, t, total):
    img  = apply_ken_burns(bg, t, zoom_in=(idx % 2 == 0))
    pulse = math.sin(t*math.pi*1.5)*0.5+0.5
    cx,cy = W//2, 400
    img  = draw_glow_overlay(img, cx, cy, int(130+pulse*20), theme["glow"], 8)
    draw = ImageDraw.Draw(img)

    # Number circle
    s = ease_out(min(1,t*5))
    r = int(110*s)
    if r>4:
        draw.ellipse([cx-r,cy-r,cx+r,cy+r],fill=theme["accent"])
        nf  = fnt(FONT_BOLD,int(90*s))
        nt  = str(idx+1)
        nw  = int(nf.getlength(nt)); nb = nf.getbbox(nt)
        draw.text((cx-nw//2,cy-nb[3]//2-nb[1]),nt,font=nf,fill=(255,255,255))

    cf   = fnt(FONT_MED,40)
    ctxt = f"of {total}"
    cw   = int(cf.getlength(ctxt))
    ca   = ease_out(min(1,max(0,(t-0.12)*4)))
    draw.text(((W-cw)//2,545),ctxt,font=cf,fill=blend_c((0,0,0),theme["sub"],ca))

    # Frosted card
    ct  = ease_out(min(1,max(0,(t-0.1)*3)))
    cy2 = int(660 + (1-ct)*200)
    card = Image.new("RGBA",(W-80,H-cy2-170),(0,0,0,0))
    cd   = ImageDraw.Draw(card)
    cd.rounded_rectangle([0,0,W-80,H-cy2-170],44,fill=(*theme["bg"],210))
    img_rgba = img.convert("RGBA")
    img_rgba.paste(card,(40,cy2),card)
    img  = img_rgba.convert("RGB")
    draw = ImageDraw.Draw(img)

    # Point text
    pt    = strip_emoji(topic["points"][idx])
    lines = wrap_text(pt,fnt(FONT_BOLD,70),W-180)
    bh    = text_block_h(lines,fnt(FONT_BOLD,70),18)
    mid_y = cy2 + (H-cy2-170)//2 - bh//2
    draw_reveal(draw,lines,mid_y,fnt(FONT_BOLD,70),(255,255,255),
                max(0,(t-0.28)),delay_per_line=0.12,reveal_dur=0.18)

    hf  = fnt(FONT_MED,36)
    hw  = int(hf.getlength(handle))
    ha  = ease_out(min(1,max(0,(t-0.6)*3)))
    draw.text(((W-hw)//2,H-140),handle,font=hf,fill=blend_c((0,0,0),theme["sub"],ha))

    prog = (idx+3)/7
    rrect(draw,[40,H-58,W-40,H-50],4,(30,30,50))
    rrect(draw,[40,H-58,40+int((W-80)*prog),H-50],4,theme["accent"])
    return img


def make_cta_frame(bg, topic, theme, handle, t):
    img  = apply_ken_burns(bg, t, zoom_in=True, strength=0.10)
    pulse = math.sin(t*math.pi*2)*0.5+0.5
    img  = draw_glow_overlay(img, W//2, H-200, int(180+pulse*50), theme["accent"], 10)
    draw = ImageDraw.Draw(img)

    # Frosted card
    card = Image.new("RGBA",(W-70,int(H*0.72)),(0,0,0,0))
    cd   = ImageDraw.Draw(card)
    cd.rounded_rectangle([0,0,W-70,int(H*0.72)],50,fill=(*theme["bg"],210))
    img_rgba = img.convert("RGBA")
    img_rgba.paste(card,(35,int(H*0.12)),card)
    img  = img_rgba.convert("RGB")
    draw = ImageDraw.Draw(img)

    tf   = fnt(FONT_BOLD,56)
    ttxt = "FOLLOW FOR MORE"
    tw   = int(tf.getlength(ttxt))
    ta   = ease_out(min(1,t*4))
    draw.text(((W-tw)//2,int(H*0.18)),ttxt,font=tf,fill=blend_c((0,0,0),theme["accent"],ta))

    bw = int(120*ease_out(min(1,max(0,(t-0.12)*4))))
    if bw>0: rrect(draw,[(W-bw)//2,int(H*0.18)+68,(W+bw)//2,int(H*0.18)+78],4,theme["accent"])

    lines  = wrap_text(topic["cta"],fnt(FONT_BOLD,66),W-160)
    bh     = text_block_h(lines,fnt(FONT_BOLD,66),18)
    draw_reveal(draw,lines,H//2-bh//2-60,fnt(FONT_BOLD,66),(255,255,255),
                max(0,(t-0.2)),delay_per_line=0.12,reveal_dur=0.18)

    tags  = [h for h in topic["hashtags"].split() if h.startswith("#")][:4]
    tstr  = "  ".join(tags)
    xf    = fnt(FONT_REG,34)
    xw    = int(xf.getlength(tstr))
    xa    = ease_out(min(1,max(0,(t-0.4)*3)))
    draw.text(((W-xw)//2,int(H*0.73)),tstr,font=xf,fill=blend_c((0,0,0),theme["sub"],xa))

    # Handle button
    hbt = ease_out(min(1,max(0,(t-0.5)*3)))
    hf  = fnt(FONT_BOLD,60)
    hw  = int(hf.getlength(handle))
    hbx = (W-hw)//2-36
    img  = draw_glow_overlay(img, W//2, H-220, int(100+pulse*30), theme["accent"], 6)
    draw = ImageDraw.Draw(img)
    rrect(draw,[hbx,H-268,hbx+hw+72,H-168],34,theme["accent"])
    draw.text(((W-hw)//2,H-268),handle,font=hf,fill=blend_c(theme["bg"],(255,255,255),hbt))

    rrect(draw,[40,H-58,W-40,H-50],4,(30,30,50))
    rrect(draw,[40,H-58,W-40,H-50],4,theme["accent"])
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


# ── Build video ────────────────────────────────────────────────────────────
def build_video(all_frames, output_path):
    for f in FRAMES.glob("*.png"):
        try: f.unlink()
        except: pass
    print(f"  Saving {len(all_frames)} frames...")
    for i,img in enumerate(all_frames):
        img.save(str(FRAMES/f"f{i:05d}.png"))
    cmd = ["ffmpeg","-y","-framerate",str(FPS),"-i",str(FRAMES/"f%05d.png"),
           "-vf","scale=1080:1920,format=yuv420p","-c:v","libx264",
           "-preset","fast","-crf","22","-r",str(FPS),"-movflags","+faststart",
           str(output_path)]
    r = subprocess.run(cmd,capture_output=True,text=True,timeout=180)
    if r.returncode!=0:
        print("ffmpeg error:",r.stderr[-1000:])
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
    handle = data.get("handle","@agentwave.ai")

    ai_topic = None if topic_id else _load_ai_topic()

    if ai_topic:
        topic = ai_topic
        if topic.get("bg_prompt"):
            set_custom_bg_prompt(topic["bg_prompt"])
        print(f"  Using AI-generated topic: {topic['title']}")
    elif topic_id:
        topic = next((t for t in topics if t["id"]==int(topic_id)), topics[0])
    else:
        tracker = {}
        if TRACKER.exists():
            with open(TRACKER) as f: tracker = json.load(f)
        used      = set(tracker.get("used",[]))
        last_id   = tracker.get("last_id",0)
        remaining = [t for t in topics if t["id"] not in used]
        if not remaining: used=set(); remaining=topics
        remaining.sort(key=lambda t:t["id"])
        topic = next((t for t in remaining if t["id"]>last_id), remaining[0])
        used.add(topic["id"])
        with open(TRACKER,"w") as f:
            json.dump({"last_id":topic["id"],"used":list(used),
                       "last_date":str(datetime.date.today())},f,indent=2)

    theme_idx = topic["id"] % len(THEMES)
    theme     = THEMES[theme_idx]
    npts      = len(topic["points"])

    print(f"\n Animating Reel: #{topic['id']} — {topic['title']}")

    bg = prepare_background(topic["id"], theme_idx, theme)

    all_frames = []
    print("  Slide 1/7: Hook")
    all_frames += render_slide(bg, lambda b,t: make_hook_frame(b,topic,theme,handle,t), 4.0)
    print("  Slide 2/7: Title")
    all_frames += render_slide(bg, lambda b,t: make_title_frame(b,topic,theme,handle,t), 2.5)
    for i in range(npts):
        print(f"  Slide {i+3}/7: Point {i+1}")
        idx = i
        all_frames += render_slide(bg, lambda b,t,ix=idx: make_point_frame(b,topic,theme,handle,ix,t,npts), 4.0)
    print("  Slide 7/7: CTA")
    all_frames += render_slide(bg, lambda b,t: make_cta_frame(b,topic,theme,handle,t), 5.0)

    print(f"  Total: {len(all_frames)} frames → {len(all_frames)/FPS:.1f}s")

    date_str = datetime.date.today().strftime("%Y%m%d")
    out_path = OUTDIR/f"reel_v2_{date_str}_topic{topic['id']}.mp4"
    build_video(all_frames, out_path)

    if topic.get("caption"):
        caption = topic["caption"]
    else:
        caption = (f"{topic['title']}\n\n"
                   + "\n".join(f"• {p}" for p in topic["points"])
                   + f"\n\n{topic['cta']}\n\n{topic['hashtags']}")

    meta = {"video_path":str(out_path),"caption":caption,
            "topic_id":topic["id"],"topic_title":topic["title"],
            "generated_at":datetime.datetime.now().isoformat()}
    with open(OUTDIR/"latest_reel_meta.json","w") as f: json.dump(meta,f,indent=2)
    print(f"\n Done! {out_path}")
    return str(out_path), meta


if __name__=="__main__":
    tid = sys.argv[1] if len(sys.argv)>1 else None
    generate(tid)
