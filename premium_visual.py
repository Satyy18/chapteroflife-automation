"""Original, zero-subscription scenic editorial renderer.
Uses only Pillow/numpy; optional user-owned backgrounds in assets/backgrounds.
Never asks an image model for Hindi text: overlay is typeset separately.
"""
from __future__ import annotations
import math
import random
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import numpy as np

PALETTES = {
    "self_respect": dict(sky1=(50,47,88), sky2=(193,116,129), sky3=(250,201,139), mountain=(95,82,103), dark=(39,45,68), marker=(240,180,173), eyebrow="#70535d"),
    "love": dict(sky1=(91,78,136), sky2=(239,144,158), sky3=(255,214,150), mountain=(125,95,121), dark=(59,56,85), marker=(241,171,190), eyebrow="#87586b"),
    "overthinking": dict(sky1=(37,48,90), sky2=(107,114,150), sky3=(206,161,148), mountain=(62,78,112), dark=(39,56,85), marker=(201,189,220), eyebrow="#655c82"),
    "friendship": dict(sky1=(65,108,121), sky2=(187,152,132), sky3=(255,215,158), mountain=(76,102,117), dark=(41,69,83), marker=(245,202,133), eyebrow="#806754"),
    "growth": dict(sky1=(54,91,97), sky2=(146,175,140), sky3=(248,218,156), mountain=(71,108,111), dark=(40,67,67), marker=(190,216,163), eyebrow="#57715e"),
    "spiritual": dict(sky1=(54,61,104), sky2=(194,135,139), sky3=(249,194,124), mountain=(70,73,112), dark=(40,48,76), marker=(246,207,136), eyebrow="#7c615f"),
    "human": dict(sky1=(65,73,106), sky2=(181,122,145), sky3=(248,206,174), mountain=(87,79,107), dark=(47,53,78), marker=(217,183,194), eyebrow="#725764"),
}

FONT_DEVANAGARI = [
    "/usr/share/fonts/truetype/noto/NotoSerifDevanagari-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
    "/usr/share/fonts/opentype/noto/NotoSerifDevanagari-Regular.ttf",
]
FONT_DEVANAGARI_BOLD = [
    # fonts-noto-core on GitHub Ubuntu runners includes Bold faces.
    "/usr/share/fonts/truetype/noto/NotoSerifDevanagari-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
    # Additional faces, when fonts-noto-extra is installed.
    "/usr/share/fonts/truetype/noto/NotoSerifDevanagari-SemiBold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-SemiBold.ttf",
    "/usr/share/fonts/opentype/noto/NotoSerifDevanagari-Bold.ttf",
    # Safe final fallback; keeps rendering working if a bold font is absent.
    "/usr/share/fonts/truetype/noto/NotoSerifDevanagari-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
]
FONT_LATIN = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
]


def font_file(candidates):
    for path in candidates:
        if Path(path).exists():
            return path
    raise RuntimeError("Missing installed Noto Devanagari fonts (fonts-noto-core).")


def font(candidates, size):
    return ImageFont.truetype(font_file(candidates), size)


def seed_for(category, variant):
    return sum((i + 1) * ord(c) for i, c in enumerate(category + str(variant))) % (2**32)


def scenic_background(width, height, category, variant=1, backgrounds_dir=None):
    """Make cinematic sunset/river illustrations; use user-owned asset when available."""
    rng = random.Random(seed_for(category, variant))
    if backgrounds_dir:
        paths = [p for p in sorted(Path(backgrounds_dir).glob("*")) if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")]
        if paths:
            src = Image.open(paths[(seed_for(category, variant)) % len(paths)]).convert("RGB")
            return ImageEnhance.Color(ImageOps_fit(src, (width, height))).enhance(.91)
    pal = PALETTES.get(category, PALETTES["love"])
    y = np.linspace(0, 1, height, dtype=np.float32)[:, None]
    c1 = np.array(pal["sky1"], dtype=np.float32)
    c2 = np.array(pal["sky2"], dtype=np.float32)
    c3 = np.array(pal["sky3"], dtype=np.float32)
    t = np.clip(y / .67, 0, 1)
    t2 = np.clip((y - .36) / .59, 0, 1)
    col = c1[None,None,:]*(1-t[...,None]) + c2[None,None,:]*t[...,None]
    col = col*(1-t2[...,None]) + c3[None,None,:]*t2[...,None]
    col = np.broadcast_to(col,(height,width,3)).copy()
    # Organic glow: keep highlights out of quote reading area when possible.
    xx = np.linspace(0,1,width,dtype=np.float32)[None,:]
    yy = np.linspace(0,1,height,dtype=np.float32)[:,None]
    glow = np.exp(-(((xx-.83)**2)/.045 + ((yy-.35)**2)/.022))
    col += glow[...,None]*np.array([24,19,7],dtype=np.float32)
    grain = np.random.default_rng(seed_for(category,variant)).normal(0,2.0,(height,width,1)).astype(np.float32)
    col = np.clip(col+grain,0,255).astype('uint8')
    im = Image.fromarray(col,"RGB")
    overlay = Image.new("RGBA",(width,height),(0,0,0,0))
    d = ImageDraw.Draw(overlay)
    # Sun and gentle haze.
    sx,sy=int(width*.83),int(height*.38)
    halo=Image.new("RGBA",(width,height),(0,0,0,0))
    hd=ImageDraw.Draw(halo)
    for rad,alpha in [(195,25),(130,27),(86,38),(52,80)]:
        hd.ellipse((sx-rad,sy-rad,sx+rad,sy+rad),fill=(255,233,181,alpha))
    halo=halo.filter(ImageFilter.GaussianBlur(25))
    overlay=Image.alpha_composite(overlay,halo)
    d=ImageDraw.Draw(overlay)
    d.ellipse((sx-40,sy-40,sx+40,sy+40),fill=(255,241,211,220))
    # Layered atmospheric mountain silhouettes.
    base=int(height*.68)
    for depth,color in [(0,(143,126,152,95)),(1,(*pal['mountain'],150)),(2,(*pal['dark'],205))]:
        yybase=base+depth*height*.075
        pts=[(-30,height),(0,yybase)]
        wave=rng.uniform(0,2*math.pi)
        for x in range(0,width+20,18):
            offset=(math.sin(x/91+wave)*33+math.sin(x/49+wave*.6)*16)
            pts.append((x,int(yybase+offset + rng.uniform(-3,3))))
        pts.extend([(width+30,height)])
        d.polygon(pts,fill=color)
    # reflective riverside and shimmering lights.
    water_top=int(height*.80)
    d.polygon([(0,water_top),(width,water_top-28),(width,height),(0,height)],fill=(*pal['dark'],195))
    for i in range(150):
        y0=rng.randrange(water_top,height)
        x0=int(sx+rng.gauss(0,(y0-water_top)*.31+18))
        if x0 < 0 or x0 >= width: continue
        ww=rng.randrange(3,48)
        aa=rng.randrange(30,115)
        d.line((x0-ww//2,y0,x0+ww//2,y0),fill=(251,206,140,aa),width=rng.choice((1,2,3)))
    # Tiny distant city/town skyline in evening.
    for i in range(34):
        x0=rng.randrange(0,width)
        by=water_top+rng.randrange(-4,38)
        h=rng.randint(12,90)
        w=rng.randint(8,28)
        d.polygon([(x0,by-h),(x0+w,by-h),(x0+w,by),(x0,by)],fill=(44,46,65,175))
        for yy0 in range(by-h+8,by-5,13):
            if rng.random()<.65:
                d.rectangle((x0+3,yy0,x0+5,yy0+3),fill=(255,196,118,160))
