"""Chapter Of Life Instagram bot — editorial quality upgrade.

Modes: verify (identity only), preview (local artifact only), publish (real Instagram post).
Keeps the existing GitHub Secret and repository variable names.
"""
import hashlib
import json
import os
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"
OUT.mkdir(exist_ok=True)
IST = ZoneInfo("Asia/Kolkata")
TODAY = datetime.now(IST).date().isoformat()
DOW = datetime.now(IST).weekday()
TOPICS = [
    "Love & Relationships", "Human Behaviour", "Friendship",
    "Self-Respect & Boundaries", "Loneliness & Overthinking",
    "Self-Growth & Life Lessons",
    "Krishna-inspired philosophy, ORIGINAL reflection only (never a fabricated scripture quote)",
]
MODE = os.getenv("RUN_MODE", "verify").strip().lower()
FORMAT = os.getenv("POST_FORMAT", "image").strip().lower() or "image"
if MODE not in ("verify", "preview", "publish"):
    raise ValueError("RUN_MODE must be verify, preview, or publish")
if FORMAT not in ("image", "reel"):
    raise ValueError("POST_FORMAT must be image or reel")
MARKER = ROOT / "history" / f"{TODAY}.json"
EXPECTED_USERNAME = os.getenv("EXPECTED_IG_USERNAME", "chapteroflife.__").lower().lstrip("@")


def required(name):
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing GitHub Secret: {name}")
    return value


def api_json(response):
    try:
        response.raise_for_status()
        return response.json()
    except requests.HTTPError as exc:
        # Never log complete API responses that might contain sensitive information.
        raise RuntimeError(f"API HTTP {response.status_code}: {response.text[:650]}") from exc


def recent_quotes():
    files = sorted((ROOT / "history").glob("*.json"), reverse=True)[:14]
    quotes = []
    for file in files:
        try:
            q = json.loads(file.read_text(encoding="utf-8")).get("quote")
            if isinstance(q, str) and q.strip():
                quotes.append(q.replace("\n", " / "))
        except (OSError, ValueError):
            pass
    return quotes


def build_prompt(feedback=""):
    previously = recent_quotes()
    avoidance = "\n".join(f"- {q}" for q in previously) if previously else "No prior published quotes recorded."
    return f"""You are an outstanding ORIGINAL Hindi micro-poet and careful copy editor for
Instagram page Chapter Of Life (@chapteroflife.__), audience young Indian Hindi speakers.
Today's theme: {TOPICS[DOW]}. Date: {TODAY}.

Write ONE original, emotionally intelligent, deeply relatable thought, easy for a reader
 to SEND TO SOMEONE THEY CARE ABOUT. The insight must be specific, not generic.
Use authentic conversational Hindi (Devanagari), never stilted translated Hindi.
Make the FINAL LINE the strongest, a meaningful emotional turn (not preachy).

STRUCTURE, STRICTLY:
- heading: 2-5 evocative Hindi words, no emoji, max 32 characters.
- quote: EXACTLY 4 or 5 hand-chosen short Hindi lines, separated by newline characters.
  Each line MUST have at most 35 Unicode characters (count spaces).
  Total quote length <= 150 characters excluding newlines.
  Each line should be a natural phrase; NO orphan words (like a single "है," on its own line).
  Quote MUST read gracefully from beginning to end; keep grammar and pronouns consistent.
  Don't use filler, clichés, forced rhymes, artificial dialogue or unsupported factual claims.
  For spiritual themes, write original philosophy, never impersonate Krishna or fabricate Gita verses.
- caption: 65-110 words ENGLISH, natural relationship/life keywords, one invite-to-comment question,
  4-7 focused hashtags at the end, no clickbait and no engagement bait.
- Avoid repetitive ideas (e.g. simply saying 'people change' or 'silence hurts').

RECENT POSTS TO AVOID REPEATING:
{avoidance}

{feedback}
Return ONLY a JSON object with exactly three STRING fields: "heading", "quote", "caption".
No markdown, no code fence, no explanations."""


def quality_check(content):
    problems = []
    if not isinstance(content, dict):
        return ["Output must be a JSON object"]
    heading = str(content.get("heading", "")).strip()
    quote = str(content.get("quote", "")).strip()
    caption = str(content.get("caption", "")).strip()
    lines = [x.strip() for x in quote.splitlines() if x.strip()]
    if not heading or len(heading) > 32 or "\n" in heading:
        problems.append("Heading must be one short Hindi line, maximum 32 characters")
    if not (4 <= len(lines) <= 5):
        problems.append("Quote must contain exactly 4 or 5 explicit newline-separated lines")
    if sum(len(line) for line in lines) > 150:
        problems.append("Quote total is over 150 characters")
    if any(len(line) > 35 for line in lines):
        problems.append("Every quote line must contain 35 characters or fewer")
    if any(len(line.strip(' ,.।!?…')) < 7 for line in lines):
        problems.append("Each line must be a meaningful phrase; no orphan words")
    if len(re.findall(r"[\u0900-\u097f]", quote)) < 25:
        problems.append("Quote should be natural Hindi in Devanagari")
    if len(caption.split()) < 45 or len(caption.split()) > 145:
        problems.append("English caption must be readable, roughly 65-110 words")
    if caption.count("#") < 4 or caption.count("#") > 8:
        problems.append("Caption needs 4-7 relevant hashtags")
    return problems


def gemini_request(prompt):
    key = required("GEMINI_API_KEY")
    model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip() or "gemini-3.5-flash-lite"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.78},
    }
    last_error = None
    for attempt in range(4):
        try:
            response = requests.post(url, headers={"x-goog-api-key": key}, json=payload, timeout=90)
            if response.status_code in (429, 500, 502, 503, 504):
                last_error = f"Gemini temporary HTTP {response.status_code}"
                if attempt < 3:
                    backoff = (12, 25, 50)[attempt]
                    print(f"{last_error}; retrying in {backoff}s")
                    time.sleep(backoff)
                    continue
            data = api_json(response)
            raw = data["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(raw)
        except (requests.RequestException, ValueError, KeyError, IndexError) as exc:
            last_error = f"Gemini response problem: {type(exc).__name__}"
            if attempt < 3:
                time.sleep((12, 25, 50)[attempt])
                continue
    raise RuntimeError(f"Gemini generation failed after retries: {last_error}")


def generate_content():
    feedback = ""
    for attempt in range(3):
        content = gemini_request(build_prompt(feedback))
        issues = quality_check(content)
        if not issues:
            return {key: str(content[key]).strip() for key in ("heading", "quote", "caption")}
        print(f"Editorial review rejected attempt {attempt+1}: {'; '.join(issues)}")
        feedback = "Correct these exact issues with a completely REWRITTEN fresh quote: " + "; ".join(issues)
    raise RuntimeError("AI did not satisfy quality checks after three tries; not publishing a low-quality post")


def font_file(candidates):
    for path in candidates:
        if Path(path).exists():
            return path
    raise RuntimeError("Missing Devanagari fonts. Workflow must install fonts-noto-core")


def render_post(content):
    """Render a strict four/five-line quote. Never wrap into orphan lines."""
    W, H = 1080, 1350
    bg, ink, muted = "#faf9f6", "#2f2e2d", "#807870"
    accent, accent_light = "#865447", "#f2e9e4"
    im = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(im)
    serif = font_file([
        "/usr/share/fonts/truetype/noto/NotoSerifDevanagari-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSerifDevanagari-SemiBold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
    ])
    sans = font_file([
        "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansDevanagariUI-Regular.ttf",
    ])
    latin = font_file([
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ])
    d.rounded_rectangle((55, 55, 1025, 1295), radius=32, outline="#e1dcd5", width=3)
    d.text((109, 127), "CHAPTER OF LIFE", font=ImageFont.truetype(latin, 35), fill="#655b54")
    d.line((109, 193, 971, 193), fill="#e6dfd7", width=2)
    d.text((109, 220), "कुछ एहसास, कुछ अल्फ़ाज़", font=ImageFont.truetype(sans, 27), fill=muted)

    heading = content["heading"].strip()
    head_size = 55
    while head_size >= 37:
        head_font = ImageFont.truetype(serif, head_size)
        if d.textlength(heading, font=head_font) <= 855:
            break
        head_size -= 2
    if d.textlength(heading, font=head_font) > 855:
        raise ValueError("Heading cannot fit without wrapping")
    d.text((109, 291), heading, font=head_font, fill=accent)
    d.rounded_rectangle((109, 390, 170, 397), radius=3, fill="#c5a08e")

    lines = [line.strip() for line in content["quote"].strip().splitlines() if line.strip()]
    font_size = 68
    while font_size >= 47:
        quote_font = ImageFont.truetype(serif, font_size)
        lengths = [d.textlength(line, font=quote_font) for line in lines]
        if all(length <= 836 for length in lengths):
            break
        font_size -= 2
    if any(length > 836 for length in lengths):
        raise ValueError("A line is too long for readable card typography")
    line_step = 110 if font_size >= 60 else 103
    content_height = (len(lines) - 1) * line_step + 92
    start_y = 500 + max(0, (540 - content_height) // 2)
    if start_y + content_height > 1132:
        raise ValueError("Quote overlaps footer")
    for i, line in enumerate(lines):
        y = start_y + i * line_step
        if i == len(lines)-1:
            width = d.textlength(line, font=quote_font)
            d.rounded_rectangle((101, y-8, min(973, 133 + width), y+font_size+33), radius=13, fill=accent_light)
            d.rectangle((102, y+3, 108, y+font_size+14), fill="#ad7d6b")
            d.text((122, y), line, font=quote_font, fill=accent)
        else:
            d.text((112, y), line, font=quote_font, fill=ink)

    d.line((110, 1179, 970, 1179), fill="#d5cdc4", width=2)
    d.text((110, 1212), "chapteroflife.__", font=ImageFont.truetype(latin, 28), fill=muted)
    sig = "~ Sat R."
    sigfont = ImageFont.truetype(latin, 29)
    d.text((970-d.textlength(sig, font=sigfont), 1211), sig, font=sigfont, fill=muted)
    target = OUT / "post.jpg"
    im.save(target, "JPEG", quality=94, optimize=True)
    return target


def make_reel(image_path):
    target = OUT / "reel.mp4"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-loop", "1", "-i", str(image_path), "-t", "9",
        "-vf", "scale=1080:1350,pad=1080:1920:0:285:color=0xfaf9f6,format=yuv420p",
        "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-movflags", "+faststart", str(target),
    ], check=True)
    return target


def cloudinary_upload(path):
    cloud = required("CLOUDINARY_CLOUD_NAME")
    key = required("CLOUDINARY_API_KEY")
    secret = required("CLOUDINARY_API_SECRET")
    timestamp = str(int(time.time()))
    # Avoid overwriting media accidentally if a manual run is repeated.
    public_id = f"chapteroflife/{TODAY}-{int(time.time())}-{FORMAT}"
    params = {"public_id": public_id, "timestamp": timestamp, "overwrite": "false"}
    signature_text = "&".join(f"{k}={v}" for k, v in sorted(params.items())) + secret
    signature = hashlib.sha1(signature_text.encode()).hexdigest()
    kind = "video" if FORMAT == "reel" else "image"
    with path.open("rb") as fp:
        response = requests.post(
            f"https://api.cloudinary.com/v1_1/{cloud}/{kind}/upload",
            data={**params, "api_key": key, "signature": signature}, files={"file": fp}, timeout=120,
        )
    return api_json(response)["secure_url"]


def ig(method, route, data=None):
    version = os.getenv("IG_GRAPH_VERSION", "v25.0")
    host = os.getenv("IG_API_HOST", "graph.facebook.com")
    url = f"https://{host}/{version}/{route}"
    headers = {"Authorization": f"Bearer {required('IG_ACCESS_TOKEN')}"}
    if method == "GET":
        return api_json(requests.get(url, params=data, headers=headers, timeout=45))
    return api_json(requests.post(url, data=data, headers=headers, timeout=45))


def verify_connection():
    uid = required("IG_USER_ID")
    if not uid.isdigit():
        raise ValueError("IG_USER_ID must be your numeric Instagram professional account ID")
    user = ig("GET", uid, {"fields": "id,username"})
    username = str(user.get("username", "")).lower().lstrip("@")
    if str(user.get("id")) != uid or username != EXPECTED_USERNAME:
        raise RuntimeError(f"Account mismatch: API @{username}, expected @{EXPECTED_USERNAME}. Publishing blocked.")
    print(f"Instagram connection verified for @{username}, ID suffix ...{uid[-4:]}")
    print("Identity verification alone does not establish content-publishing permission.")


def publish(media_url, caption):
    uid = required("IG_USER_ID")
    fields = {"caption": caption}
    if FORMAT == "reel":
        fields.update({"media_type": "REELS", "video_url": media_url, "share_to_feed": "true"})
    else:
        fields["image_url"] = media_url
    container_id = ig("POST", f"{uid}/media", fields)["id"]
    for _ in range(18):
        time.sleep(10 if FORMAT == "reel" else 4)
        status = ig("GET", container_id, {"fields": "status_code"})["status_code"]
        print("Instagram media processing:", status)
        if status == "FINISHED":
            break
        if status in ("ERROR", "EXPIRED"):
            raise RuntimeError("Instagram rejected the media container: " + status)
    else:
        raise TimeoutError("Instagram media still processing. No publish attempted.")
    return ig("POST", f"{uid}/media_publish", {"creation_id": container_id})["id"]


def main():
    verify_connection()
    if MODE == "verify":
        print("VERIFY ONLY - no AI content generation or publishing")
        return
    if MARKER.exists() and MODE == "publish":
        print("Already published today, skipping duplicate:", MARKER)
        return
    content = generate_content()
    (OUT / "content.json").write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "caption.txt").write_text(content["caption"] + "\n", encoding="utf-8")
    image_path = render_post(content)
    media_path = make_reel(image_path) if FORMAT == "reel" else image_path
    if MODE == "preview":
        print("PREVIEW ONLY - generated post.jpg and caption.txt. No upload and no Instagram post.")
        return
    media_url = cloudinary_upload(media_path)
    media_id = publish(media_url, content["caption"])
    MARKER.parent.mkdir(exist_ok=True)
    MARKER.write_text(json.dumps({
        "date": TODAY, "format": FORMAT, "media_id": media_id,
        "topic": TOPICS[DOW], "quote": content["quote"], "heading": content["heading"],
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print("Successfully published Instagram media, ID suffix:", str(media_id)[-6:])


if __name__ == "__main__":
    main()
