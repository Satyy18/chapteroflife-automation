import os, io, re, json, time, hmac, hashlib, subprocess, textwrap
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent
OUT = ROOT / 'output'
OUT.mkdir(exist_ok=True)
IST = ZoneInfo('Asia/Kolkata')
TODAY = datetime.now(IST).date().isoformat()
DOW = datetime.now(IST).weekday()
TOPICS = [
    'Love & Relationships', 'Human Behaviour', 'Friendship',
    'Self-Respect & Boundaries', 'Loneliness & Overthinking',
    'Self-Growth & Life Lessons', 'Krishna-inspired philosophical reflection (not a fabricated scripture quote)'
]
MODE = os.getenv('RUN_MODE', 'verify').lower()
if MODE not in ('verify', 'preview', 'publish'):
    raise ValueError('RUN_MODE must be verify, preview or publish')
DRY = MODE != 'publish'
FORMAT = os.getenv('POST_FORMAT', 'image').lower()
if FORMAT not in ('image', 'reel'):
    raise ValueError('POST_FORMAT must be image or reel')
MARKER = ROOT / 'history' / f'{TODAY}.json'


def required(key):
    val = os.getenv(key)
    if not val:
        raise RuntimeError(f'Missing environment secret: {key}')
    return val


def api_json(response):
    try:
        response.raise_for_status()
        return response.json()
    except requests.HTTPError as exc:
        raise RuntimeError(f'API error HTTP {response.status_code}: {response.text[:800]}') from exc


def generate_content():
    key = required('GEMINI_API_KEY')
    model = os.getenv('GEMINI_MODEL', 'gemini-2.5-flash')
    prompt = f'''You are the original Hindi writer for @chapteroflife.__ on Instagram.
Today: {TODAY}; weekly theme: {TOPICS[DOW]}.
Create ONE fresh, poignant, relatable, non-cliche Hindi poetic thought suitable for a quote card.
Audience: Indian Gen Z. Write naturally with thoughtful emotional depth, not melodrama.
Text: 4-6 short Hindi lines; maximum ~130 Devanagari characters total; do not number lines.
No direct quotes from Gita or attribution to Krishna unless you know a verifiable source; favor original inspiration.
Caption: 80-140 words in English, natural SEO phrases, a clear question, 5-8 relevant hashtags, not spam.
Return ONLY valid JSON object with EXACT keys: "heading" (Hindi, up to 35 chars), "quote" (Hindi), "caption" (English). No Markdown fences.
Avoid repeating common clichés such as 'people change', 'silence is the loudest'.'''
    url = f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'
    data = api_json(requests.post(url, headers={'x-goog-api-key': key, 'Content-Type':'application/json'},
        json={'contents':[{'parts':[{'text':prompt}]}], 'generationConfig':{'responseMimeType':'application/json', 'temperature':0.85}}, timeout=70))
    raw = data['candidates'][0]['content']['parts'][0]['text']
    parsed = json.loads(raw)
    for field in ('heading', 'quote', 'caption'):
        if not isinstance(parsed.get(field), str) or not parsed[field].strip():
            raise ValueError(f'Invalid generated field: {field}')
    if len(parsed['quote']) > 230:
        raise ValueError('AI quote too long; skip instead of publishing broken design')
    return parsed


def font_path():
    for p in ('/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf',
              '/usr/share/fonts/truetype/noto/NotoSerifDevanagari-Regular.ttf'):
        if Path(p).exists(): return p
    raise RuntimeError('Install fonts-noto-core to render Hindi text')


def break_lines(draw, txt, font, max_width):
    lines = []
    for raw in txt.splitlines():
        words = raw.strip().split()
        line = ''
        for word in words:
            nxt = (line + ' ' + word).strip()
            if line and draw.textlength(nxt, font=font) > max_width:
                lines.append(line); line = word
            else: line = nxt
        if line: lines.append(line)
    return lines


def card(content):
    W, H = 1080, 1350  # 4:5 Instagram feed portrait
    im = Image.new('RGB', (W,H), '#f8f6f2')
    draw = ImageDraw.Draw(im)
    draw.rounded_rectangle((55,55,W-55,H-55), radius=28, outline='#ded9d0', width=3)
    draw.rectangle((105,190,125,265), fill='#b9a18e')
    f = font_path()
    small = ImageFont.truetype(f, 35)
    title = ImageFont.truetype(f, 56)
    quote = ImageFont.truetype(f, 63)
    draw.text((105,122), 'CHAPTER OF LIFE', font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',32), fill='#867565')
    heading = break_lines(draw, content['heading'], title, 820)
    y = 300
    for line in heading[:2]:
        draw.text((110,y), line, font=title, fill='#4f413b', stroke_width=0)
        y += 90
    y += 100
    body = break_lines(draw, content['quote'], quote, 820)
    if len(body) > 9:
        raise ValueError('Generated card too long to render clearly')
    for line in body:
        draw.text((110,y), line, font=quote, fill='#272829')
        y += 90
    if y > 1170:
        raise ValueError('Generated text overlaps footer')
    draw.line((110,1180,970,1180), fill='#d1c7ba', width=2)
    draw.text((110,1212),'chapteroflife.__', font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',30),fill='#786e65')
    draw.text((825,1212),'~ Sat R.',font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',30),fill='#786e65')
    target = OUT / 'post.jpg'
    im.save(target, 'JPEG', quality=94)
    return target


def video(image_path):
    target = OUT / 'reel.mp4'
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-loop','1','-i',str(image_path),
        '-t','9','-vf','scale=1080:1350,pad=1080:1920:0:285:color=0xf8f6f2,format=yuv420p',
        '-r','30','-c:v','libx264','-preset','veryfast','-crf','23','-movflags','+faststart',str(target)],check=True)
    return target


def cloudinary_upload(path):
    cloud, key, secret = (required(k) for k in ('CLOUDINARY_CLOUD_NAME','CLOUDINARY_API_KEY','CLOUDINARY_API_SECRET'))
    timestamp = str(int(time.time()))
    public_id = f'chapteroflife/{TODAY}-{FORMAT}'
    params = {'public_id':public_id,'timestamp':timestamp,'overwrite':'true'}
    signed = '&'.join(f'{k}={v}' for k,v in sorted(params.items())) + secret
    signature = hashlib.sha1(signed.encode()).hexdigest()
    resource_type = 'video' if FORMAT == 'reel' else 'image'
    with path.open('rb') as file:
        resp = requests.post(f'https://api.cloudinary.com/v1_1/{cloud}/{resource_type}/upload',
            data={**params,'api_key':key,'signature':signature}, files={'file':file}, timeout=120)
    return api_json(resp)['secure_url']


def ig(method, route, data=None):
    version = os.getenv('IG_GRAPH_VERSION','v25.0')
    host = os.getenv('IG_API_HOST','graph.facebook.com')
    base = f'https://{host}/{version}/{route}'
    token = required('IG_ACCESS_TOKEN')
    headers = {'Authorization':f'Bearer {token}'}
    if method == 'GET': return api_json(requests.get(base, params=data, headers=headers,timeout=45))
    return api_json(requests.post(base, data=data, headers=headers,timeout=45))


def publish(media_url, caption):
    uid = required('IG_USER_ID')
    fields = {'caption':caption}
    if FORMAT == 'reel':
        fields.update({'media_type':'REELS','video_url':media_url,'share_to_feed':'true'})
    else:
        fields['image_url'] = media_url
    container = ig('POST', f'{uid}/media', fields)['id']
    for i in range(18):
        time.sleep(10 if FORMAT == 'reel' else 4)
        status = ig('GET',container,{'fields':'status_code'})['status_code']
        print('Instagram container status:',status)
        if status == 'FINISHED': break
        if status in ('ERROR','EXPIRED'):
            raise RuntimeError('Instagram rejected media container: '+ status)
    else:
        raise TimeoutError('Instagram container not finished. Not publishing.')
    result = ig('POST',f'{uid}/media_publish',{'creation_id':container})
    return result['id']


def verify_connection():
    uid = required('IG_USER_ID').strip()
    if not uid.isdigit():
        raise ValueError('IG_USER_ID must be your numeric Instagram professional account ID')
    user = ig('GET', uid, {'fields': 'id,username'})
    username = str(user.get('username', '')).lower().lstrip('@')
    expected = os.getenv('EXPECTED_IG_USERNAME', 'chapteroflife.__').lower().lstrip('@')
    if str(user.get('id')) != uid or username != expected:
        raise RuntimeError(f'Instagram account mismatch: API returned @{username}. Expected @{expected}. Publishing blocked.')
    print(f'Instagram connection verified for @{username}, ID suffix ...{uid[-4:]}')
    print('Note: This identity check does not prove that content publishing permission is granted.')


def main():
    verify_connection()
    if MODE == 'verify':
        print('VERIFY ONLY - no AI generation, upload, or Instagram publishing performed')
        return
    if MARKER.exists() and MODE == 'publish':
        print('Post already published today; skipping:', MARKER)
        return
    content = generate_content()
    (OUT/'content.json').write_text(json.dumps(content,ensure_ascii=False,indent=2),encoding='utf-8')
    image_path = card(content)
    media_path = video(image_path) if FORMAT == 'reel' else image_path
    if DRY:
        print('PREVIEW - created output/post.jpg; no media uploaded or Instagram post published')
        return
    url = cloudinary_upload(media_path)
    media_id = publish(url, content['caption'])
    MARKER.parent.mkdir(exist_ok=True)
    MARKER.write_text(json.dumps({'date':TODAY,'format':FORMAT,'media_id':media_id,
        'topic':TOPICS[DOW]},indent=2),encoding='utf-8')
    print('Published Instagram media:',media_id)


if __name__ == '__main__':
    main()
