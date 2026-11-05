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
    "/usr/share/fonts/truetype/noto/NotoSerifDevanagari-SemiBold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-SemiBold.ttf",
    "/usr/share/fonts/opentype/noto/NotoSerifDevanagari-Bold.ttf",
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
    # Floating lights/bokeh.
    for _ in range(95):
        x0,y0=rng.randrange(width),rng.randrange(height)
        rad=rng.choice((1,2,3,4,7))
        d.ellipse((x0-rad,y0-rad,x0+rad,y0+rad),fill=(255,219,171,rng.randint(40,145)))
    # Organic canopy and blossoms along top border.
    for side in (0,1):
        anchor_x=0 if side==0 else width
        for b in range(12):
            x=anchor_x+ (1 if side==0 else -1)*rng.randrange(0,150)
            tip_x=x+(1 if side==0 else -1)*rng.randrange(110,310)
            y0=rng.randrange(-25,80)
            tip_y=y0+rng.randrange(60,300)
            d.line([(x,y0),(tip_x,tip_y)],fill=(55,72,52,175),width=rng.randrange(3,8))
            for k in range(4):
                t=(k+1)/5
                bx=x+(tip_x-x)*t
                by=y0+(tip_y-y0)*t
                dx=28*(1 if k%2 else -1)
                d.ellipse((bx-22,by-13,bx+dx+19,by+12),fill=(65+rng.randrange(18),97+rng.randrange(30),56,155))
                if rng.random()<.8:
                    blossom(d,bx+rng.randint(-8,12),by+rng.randint(-11,13),rng.randint(7,16),rng)
    # foreground flowers near bottom sides.
    for _ in range(45):
        x=rng.choice((rng.randrange(0,int(width*.23)),rng.randrange(int(width*.7),width)))
        y=rng.randint(int(height*.86),height+30)
        blossom(d,x,y,rng.randint(8,26),rng)
    im=Image.alpha_composite(im.convert('RGBA'),overlay).convert("RGB")
    return im


def blossom(d,x,y,r,rng):
    shade=rng.choice([(255,215,219,185),(255,229,218,188),(255,237,199,172),(239,190,205,180)])
    for j in range(5):
        a=j*math.tau/5
        px=x+math.cos(a)*r*.57
        py=y+math.sin(a)*r*.57
        d.ellipse((px-r*.45,py-r*.45,px+r*.45,py+r*.45),fill=shade)
    d.ellipse((x-r*.17,y-r*.17,x+r*.17,y+r*.17),fill=(255,186,92,215))


def ImageOps_fit(src,size):
    from PIL import ImageOps
    return ImageOps.fit(src,size,method=Image.Resampling.LANCZOS,centering=(.60,.5))


def anime_silhouette(canvas, category, variant=0):
    """Painterly character from behind (original vector illustration, not AI-rendered)."""
    w,h=canvas.size
    s=w/1080
    y_off=500 if h==1920 else 0
    rng=random.Random(seed_for(category,variant)+88)
    layer=Image.new("RGBA",(w,h),(0,0,0,0)); d=ImageDraw.Draw(layer)
    def P(points): return [(int(x*s),int((y+y_off)*s)) for x,y in points]
    def el(b,fill): d.ellipse((int(b[0]*s),int((b[1]+y_off)*s),int(b[2]*s),int((b[3]+y_off)*s)),fill=fill)
    # window / balustrade foreground
    d.line(P([(710,1160),(1100,1160)]),fill=(42,40,61,190),width=int(22*s))
    d.line(P([(777,1158),(777,1400)]),fill=(39,43,58,180),width=int(20*s))
    # legs, oversized cardigan, long dark hair blowing to the left
    d.polygon(P([(790,1040),(970,1045),(1120,1310),(1030,1370),(930,1255),(805,1220)]),fill=(57,64,88,238))
    d.polygon(P([(815,920),(985,880),(1065,1110),(1001,1235),(804,1150),(750,1080)]),fill=(235,199,184,253))
    d.line(P([(830,960),(814,1110),(1005,1150)]),fill=(211,160,156,240),width=int(14*s),joint='curve')
    # shoulder arm / hand up to cheek
    d.polygon(P([(970,965),(1011,988),(985,1080),(950,1070)]),fill=(240,202,181,255))
    d.polygon(P([(1010,967),(985,922),(1015,897),(1040,926)]),fill=(248,205,182,255))
    # hair shape / face silhouette
    d.polygon(P([(875,825),(924,796),(982,810),(1019,848),(1034,905),(1002,969),(955,996),(887,947),(855,873)]),fill=(50,37,50,255))
    # profile warm face
    el((958,841,1044,940),(242,190,169,255))
    d.polygon(P([(1036,884),(1060,897),(1036,908),(1015,941),(996,912)]),fill=(238,188,167,255))
    # hair front and side flowing
    d.polygon(P([(865,834),(927,782),(992,787),(1011,815),(992,845),(946,855),(935,907),(956,952),(913,990),(869,1040),(812,1063),(848,987),(817,919)]),fill=(56,38,51,255))
    d.arc((int(836*s),int((810+y_off)*s),int(1000*s),int((992+y_off)*s)),180,349,fill=(136,93,83,240),width=int(5*s))
    d.arc((int(854*s),int((819+y_off)*s),int(983*s),int((979+y_off)*s)),172,336,fill=(198,134,100,180),width=int(3*s))
    # Eyes: lowered and peaceful
    d.arc((int(1018*s),int((890+y_off)*s),int(1043*s),int((902+y_off)*s)),5,145,fill=(72,52,67,230),width=int(2*s))
    # little flower hair pin
    for angle in range(5):
        a=angle*math.tau/5
        x=899+14*math.cos(a); y=844+14*math.sin(a)
        el((x-9,y-9,x+9,y+9),(255,222,221,245))
    el((892,837,905,849),(244,193,95,255))
    # soft near-ground glow
    canvas.alpha_composite(layer)


def make_paper_layer(w,h,category):
    im=Image.new("RGBA",(w,h),(0,0,0,0)); d=ImageDraw.Draw(im)
    x1,y1,x2,y2= (67,151,723,1195) if h==1350 else (64,285,763,1642)
    rng=random.Random(seed_for(category,2))
    points=[]
    for x in range(x1,x2+1,14): points.append((x,y1+rng.randint(-5,5)))
    for y in range(y1,y2+1,14): points.append((x2+rng.randint(-5,5),y))
    for x in range(x2,x1-1,-14): points.append((x,y2+rng.randint(-5,5)))
    for y in range(y2,y1-1,-14): points.append((x1+rng.randint(-5,5),y))
    shadow=Image.new("RGBA",(w,h),(0,0,0,0)); sd=ImageDraw.Draw(shadow)
    sd.polygon([(x+15,y+15) for x,y in points],fill=(20,17,24,110))
    shadow=shadow.filter(ImageFilter.GaussianBlur(20))
    im.alpha_composite(shadow)
    d=ImageDraw.Draw(im)
    d.polygon(points,fill=(255,248,231,244))
    d.line(points+[points[0]],fill=(164,130,104,120),width=3,joint='curve')
    return im,(x1,y1,x2,y2)


def draw_stroke(d, x0,y0,x1,y1, fill, seed=1, thickness=31):
    rng=random.Random(seed)
    pts=[]
    for i in range(12):
        t=i/11; pts.append((int(x0+(x1-x0)*t),int(y0+(y1-y0)*t+rng.uniform(-4,4))))
    d.line(pts,fill=fill,width=thickness,joint='curve')
    # jagged transparent overpaint
    for _ in range(3):
        yy=y0+rng.randint(-thickness//3,thickness//3)
        d.line([(x0+8,yy),(x1-10,yy+rng.randint(-5,5))],fill=(*fill[:3], min(130,fill[3])),width=4)


def line_font_fit(draw, lines, available_width, max_size=52, min_size=31):
    for size in range(max_size,min_size-1,-1):
        ft=font(FONT_DEVANAGARI, size)
        if all(draw.textbbox((0,0),line,font=ft)[2] <= available_width for line in lines):
            return ft
    raise ValueError("Hindi line too long for paper panel. Shorten the text before publishing.")


def render_content(content,category,outfile,width=1080,height=1350,backgrounds_dir=None):
    assert (width,height) in ((1080,1350),(1080,1920))
    scene=scenic_background(width,height,category,1,backgrounds_dir).convert("RGBA")
    # When a user supplies a licensed image background, keep that artwork intact.
    custom_pictures = (bool(backgrounds_dir) and Path(backgrounds_dir).exists() and
                       any(p.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp')
                           for p in Path(backgrounds_dir).iterdir()))
    if not custom_pictures:
        anime_silhouette(scene,category,1)
    paper,bounds=make_paper_layer(width,height,category); scene.alpha_composite(paper)
    d=ImageDraw.Draw(scene)
    x1,y1,x2,y2=bounds
    cx=(x1+x2)//2
    pal=PALETTES.get(category,PALETTES["love"])
    small=font(FONT_LATIN,24)
    hi_t=font(FONT_DEVANAGARI_BOLD,44)
    # Top editorial masthead
    heading_y=y1+48
    name='C H A P T E R   O F   L I F E'
    d.text((cx,heading_y),name,font=small,fill=(114,84,80,255),anchor='ma')
    d.line((x1+59,heading_y+47,x2-59,heading_y+47),fill=(174,142,130,150),width=2)
    title=str(content.get('heading','')).strip()
    for size in range(48,30,-2):
        hi_t=font(FONT_DEVANAGARI_BOLD,size)
        if d.textbbox((0,0),title,font=hi_t)[2] < x2-x1-92: break
    title_y=heading_y+96
    tw=d.textbbox((0,0),title,font=hi_t)[2]
    draw_stroke(d,cx-tw//2-13,title_y+53,cx+tw//2+10,title_y+55,(*pal['marker'],170),3,25)
    d.text((cx,title_y),title,font=hi_t,fill=(66,50,53,255),anchor='ma')
    sub = 'कुछ एहसास, कुछ अल्फ़ाज़'
    subft = font(FONT_DEVANAGARI,23)
    d.text((cx,title_y+98),sub,font=subft,fill=(123,102,99,255),anchor='ma')
    subw=d.textbbox((0,0),sub,font=subft)[2]
    d.line((cx-subw//2-45,title_y+110,cx-subw//2-15,title_y+110),fill=(164,121,108,255),width=2)
    d.line((cx+subw//2+15,title_y+110,cx+subw//2+45,title_y+110),fill=(164,121,108,255),width=2)
    # Exact AI-provided newlines; never auto-wrap into stray one-word lines.
    lines=[s.strip() for s in str(content.get('quote','')).splitlines() if s.strip()]
    if not 4<=len(lines)<=5: raise ValueError('Quote must contain 4 to 5 lines')
    avail=x2-x1-115
    body_font=line_font_fit(d,lines,avail,max_size=53 if height==1350 else 58,min_size=30)
    footer=y2-100
    qtop=title_y+230
    qbot=footer-96
    step=min(101,(qbot-qtop)//(len(lines)-1))
    if step < 70: raise ValueError('Too much text to fit in card')
    qstart=qtop+max(0,(qbot-qtop-(len(lines)-1)*step)//2)
    for n,line in enumerate(lines):
        ty=qstart+n*step
        width_text=d.textbbox((0,0),line,font=body_font)[2]
        if n==len(lines)-1:
            draw_stroke(d,cx-width_text//2-12,ty+50,cx+width_text//2+16,ty+51,(*pal['marker'],207),19+n,37)
            linecolor=(89,52,59,255)
        else:
            linecolor=(57,48,52,255)
        d.text((cx,ty),line,font=body_font,fill=linecolor,anchor='ma')
    d.line((x1+63,footer-24,x2-63,footer-24),fill=(177,145,128,155),width=2)
    d.text((cx,footer),'chapteroflife.__',font=font(FONT_LATIN,24),fill=(103,81,79,255),anchor='ma')
    d.text((cx,footer+40),'~ Sat R.',font=font(FONT_LATIN,24),fill=(127,79,87,255),anchor='ma')
    path=Path(outfile)
    path.parent.mkdir(parents=True,exist_ok=True)
    scene.convert('RGB').save(path,'JPEG',quality=93,optimize=True)
    return path
