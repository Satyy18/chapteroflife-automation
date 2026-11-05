"""Chapter Of Life Premium Automation v2.

Modes: verify | preview | publish
Formats: image | reel
Free by default: original procedural illustrated scenes, original ambient reel music.
Optional paid AI image background requires TWO separate explicit environment opt-ins.
"""
from __future__ import annotations
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from io import BytesIO
from zoneinfo import ZoneInfo

import requests
from PIL import Image
from premium_visual import render_content
from music_original import make_original_ambient

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"
OUT.mkdir(parents=True, exist_ok=True)
IST = ZoneInfo("Asia/Kolkata")
TODAY = datetime.now(IST).date().isoformat()
DOW = datetime.now(IST).weekday()
MODE = os.getenv("RUN_MODE", "verify").strip().lower()
FORMAT = os.getenv("POST_FORMAT", "image").strip().lower()
TOPIC_OVERRIDE = os.getenv("TOPIC_OVERRIDE", "auto").strip().lower()
EXPECTED_USERNAME = os.getenv("EXPECTED_IG_USERNAME", "chapteroflife.__").lower().lstrip("@")
MARKER = ROOT / "history" / f"{TODAY}.json"

DAY_THEMES = ["love", "self_respect", "human", "overthinking", "friendship", "growth", "spiritual"]
THEMES = {
    "love": "Love & Relationships. Warm affection, trust and choosing each other, not clichés.",
    "self_respect": "Self-Respect & Boundaries. Kind but firm, emotionally nuanced.",
    "human": "Human Behaviour. Specific insight into subtle everyday behaviour and feelings.",
    "overthinking": "Loneliness & Overthinking. Gentle late-night insight, not clinical advice.",
    "friendship": "Friendship & Nostalgia. Old friends, changing routines, genuine care.",
    "growth": "Self-Growth & Life Lessons. Quiet progress and everyday resilience.",
    "spiritual": "Original Krishna-inspired philosophical reflection; NEVER pretend it is a Gita quotation.",
}


def required(key):
    val=os.getenv(key, "").strip()
    if not val: raise RuntimeError(f"Missing secret: {key}")
    return val


def api_json(response):
    try:
        response.raise_for_status()
        return response.json()
    except requests.HTTPError as ex:
        # Prevent accidentally logging secrets in full API URLs / responses.
        try:
            msg = str(response.json().get("error",{}).get("message", ""))
        except (ValueError, AttributeError):
            msg = ""
        msg = re.sub(r"(?:Bearer\s+)?[A-Za-z0-9_\-]{75,}", "[REDACTED]", msg)
        raise RuntimeError(f"API returned HTTP {response.status_code}: {msg[:250]}") from ex


def recent_quotes():
    files=sorted((ROOT / "history").glob("*.json"), reverse=True)[:21]
    previous=[]
    for f in files:
        try:
            doc=json.loads(f.read_text(encoding='utf-8'))
            if isinstance(doc.get("quote"), str): previous.append(doc["quote"].replace("\n"," / "))
        except (OSError, ValueError): pass
    return previous


def writing_prompt(topic, feedback=''):
    old=recent_quotes()
    previously='\n'.join('- '+t for t in old) if old else 'None'
    return f"""You are a Hindi literary editor and a premium Instagram writer for
Chapter Of Life (@chapteroflife.__). Theme: {THEMES[topic]}. Locale: India.

Write ONE ORIGINAL Hindi 4-5 line thought that someone would save or share with a close
friend/partner. Make it specific, emotionally real, and hopeful without fake motivation.
Use real, idiomatic Devanagari Hindi (not word-by-word English translation).
The FINAL line must provide an unexpected, memorable emotional turn.
Strong individual sentences; do not produce a list of moral lessons.

STRICT OUTPUT JSON containing exactly 3 string keys: heading, quote, caption.
heading: compelling natural Hindi title, 2-5 words, max 29 characters; NO emoji.
quote: EXACTLY 4 OR 5 short logical Hindi lines with explicit newline separators.
  Each line max 30 Unicode characters INCLUDING SPACES. Total max 140 chars excluding
  newlines. Every line must be a phrase, not an orphan 'है' or 'था'. Consistent grammar,
  cohesive thought across lines; avoid generic vague clichés and repeated comparisons.
  Avoid excessive punctuation, filler, preachiness, religious misquotations.
caption: 70-115 words in natural English, relevant search keywords integrated normally,
  one reflective question, 4-7 appropriate hashtags. No fake claims or aggressive CTAs.

Previous already posted content: {previously}
{feedback}
Only output valid JSON. No markdown or prefacing."""


def validate(content):
    errors=[]
    if not isinstance(content,dict): return ['Gemini did not return a JSON object']
    heading=str(content.get("heading","")).strip()
    quote=str(content.get("quote","")).strip()
    caption=str(content.get("caption","")).strip()
    lines=[l.strip() for l in quote.splitlines() if l.strip()]
    if not (4 <= len(lines) <= 5): errors.append('Quote must have 4-5 lines')
    if not heading or len(heading)>29 or '\n' in heading: errors.append('Heading too long')
    if len(quote.replace('\n','')) > 140: errors.append('Total quote too long')
    if any(len(line)>30 for line in lines): errors.append('A quote line exceeds 30 characters')
    if any(len(line.strip(' ,.!?।…')) < 8 for line in lines): errors.append('Quote has a tiny orphan line')
    if len(re.findall(r'[\u0900-\u097f]',quote)) < 25: errors.append('Quote should be Hindi in Devanagari')
    wc=len(caption.split())
    if not (55 <= wc <= 135): errors.append('Caption word count unexpected')
    hashtags=caption.count('#')
    if not 4 <= hashtags <= 7: errors.append('Caption should have 4-7 hashtags')
    # This is structural review, NOT a guarantee of good poetry.
    return errors


def gemini_text(prompt):
    model=os.getenv('GEMINI_MODEL','gemini-3.5-flash-lite').strip()
    url=f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'
    payload={
       'contents':[{'parts':[{'text':prompt}]}],
       'generationConfig':{'responseMimeType':'application/json','temperature':.78},
    }
    last='unknown'
    for attempt in range(4):
        try:
            res=requests.post(url,headers={'x-goog-api-key':required('GEMINI_API_KEY')},json=payload,timeout=90)
            if res.status_code in (429,500,502,503,504):
                last=f'Gemini temporary HTTP {res.status_code}'
                if attempt < 3:
                    seconds=(10,22,42)[attempt]
                    print(f'{last}; retrying after {seconds} seconds')
                    time.sleep(seconds)
                    continue
            body=api_json(res)
            txt=''.join(part.get('text','') for part in body['candidates'][0]['content']['parts'])
            return json.loads(txt)
        except (requests.RequestException,ValueError,KeyError,IndexError) as err:
            last=type(err).__name__
            if attempt < 3:
                time.sleep((10,22,42)[attempt]); continue
    raise RuntimeError('Text generation failed after retries: '+last)


def generate_content(topic):
    feedback=''
    for i in range(3):
        obj=gemini_text(writing_prompt(topic,feedback))
        problems=validate(obj)
        if not problems:
            return {key:str(obj[key]).strip() for key in ('heading','quote','caption')}
        feedback='Fix the following issues by rewriting the quote COMPLETELY: '+ '; '.join(problems)
        print(f'Editorial validation rejected draft {i+1}: '+ '; '.join(problems))
    raise RuntimeError('Three attempts failed editorial structure check. No post published.')


def optionally_generate_paid_background(topic):
    """Not invoked by default. Requires both controls to avoid surprise charges."""
    enabled=os.getenv('IMAGE_PROVIDER','free').strip().lower() == 'gemini_paid'
    explicitly_allowed=os.getenv('ALLOW_PAID_IMAGE_API','false').strip().lower() == 'true'
    if not enabled: return None
    if not explicitly_allowed:
        raise RuntimeError('Paid image provider requested, but ALLOW_PAID_IMAGE_API is not true; no charge attempted.')
    model=os.getenv('PAID_IMAGE_MODEL','gemini-3.1-flash-lite-image')
    prompt=(f'Original vertical cinematic illustrated dreamy environment, theme: {THEMES[topic]}. '
            'Atmospheric sunset, flowering vines, nostalgic city by a river, luminous painterly textures, '
            'attractive wistful anime-inspired girl seen from behind on RIGHT THIRD, elegant illustration, '
            'soft depth of field, gentle golden sparkles, high-end editorial artwork. '
            'Keep the LEFT TWO THIRDS softly atmospheric so a cream paper panel can be overlaid. '
            'ABSOLUTELY NO TEXT, NO LETTERS, NO WATERMARK, NO LOGOS. 4:5 portrait.')
    url=f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'
    payload={'contents':[{'parts':[{'text':prompt}]}],
             'generationConfig':{'responseModalities':['TEXT','IMAGE'],
                                 'imageConfig':{'aspectRatio':'4:5','imageSize':'1K'}}}
    res=requests.post(url,headers={'x-goog-api-key':required('GEMINI_API_KEY')},json=payload,timeout=150)
    body=api_json(res)
    try:
        parts=body['candidates'][0]['content']['parts']
        part=next(p for p in parts if 'inlineData' in p)
        raw=base64.b64decode(part['inlineData']['data'])
        img=Image.open(BytesIO(raw)).convert('RGB')
    except (KeyError,StopIteration,ValueError) as err:
        raise RuntimeError('Paid image model did not return an image') from err
    folder=OUT/'generated_backgrounds'; folder.mkdir(exist_ok=True)
    fp=folder/f'{topic}.jpg'; img.save(fp,'JPEG',quality=94)
    print('Generated paid AI background by explicit opt-in. Check Gemini billing dashboard.')
    return folder


def render_post(content,topic,kind='image',suffix=''):
    bgdir=optionally_generate_paid_background(topic)
    if bgdir is None:
        bgdir=ROOT/'assets'/'backgrounds'
    filename='post'+('_'+suffix if suffix else '')+'.jpg'
    fp=render_content(content,topic,OUT/filename,backgrounds_dir=bgdir)
    if kind=='reel':
        reel_fp=OUT/('reel'+('_'+suffix if suffix else '')+'.mp4')
        reel_cover=OUT/('reel_cover'+('_'+suffix if suffix else '')+'.jpg')
        render_content(content,topic,reel_cover,1080,1920,backgrounds_dir=bgdir)
        make_reel(reel_cover,reel_fp)
        return fp,reel_fp
    return fp,fp


def make_reel(image_path, target):
    """Vertical MP4 with slow zoom and original royalty-free-in-context ambient composition."""
    music_dir=ROOT/'assets'/'music'
    candidates=sorted([p for p in music_dir.glob('*') if p.suffix.lower() in ('.mp3','.wav','.m4a')])
    bgm=candidates[0] if candidates else make_original_ambient(OUT/'original_ambient.wav',12)
    # The music provided by a user must be owned/licensed for Instagram use.
    filter_video="scale=1160:2062,crop=1080:1920:(in_w-out_w)/2:(in_h-out_h)/2,format=yuv420p"
    subprocess.run([
        'ffmpeg','-hide_banner','-loglevel','error','-y',
        '-loop','1','-framerate','30','-i',str(image_path),
        '-stream_loop','-1','-i',str(bgm),'-t','12',
        '-vf',filter_video,'-r','30','-c:v','libx264','-preset','veryfast','-crf','23',
        '-c:a','aac','-b:a','128k','-shortest','-movflags','+faststart',str(target)
    ],check=True)
    return target


def ig(method,route,data=None):
    host=os.getenv('IG_API_HOST','graph.facebook.com')
    version=os.getenv('IG_GRAPH_VERSION','v25.0')
    headers={'Authorization':'Bearer '+required('IG_ACCESS_TOKEN')}
    url=f'https://{host}/{version}/{route}'
    if method=='GET':
        return api_json(requests.get(url,params=data,headers=headers,timeout=45))
    return api_json(requests.post(url,data=data,headers=headers,timeout=45))


def verify_connection():
    uid=required('IG_USER_ID')
    if not uid.isdigit(): raise ValueError('IG_USER_ID must contain the numeric Instagram account ID')
    user=ig('GET',uid,{'fields':'id,username'})
    username=str(user.get('username','')).lower().lstrip('@')
    if username != EXPECTED_USERNAME or str(user.get('id')) != uid:
        raise RuntimeError(f'Instagram account mismatch! Got @{username} expected @{EXPECTED_USERNAME}.')
    print('Instagram connection verified for @'+username+ ', ID suffix ...'+uid[-4:])
    print('Note: identity check does not prove publication permission.')


def cloudinary_upload(path,kind):
    cloud=required('CLOUDINARY_CLOUD_NAME')
    key=required('CLOUDINARY_API_KEY')
    secret=required('CLOUDINARY_API_SECRET')
    timestamp=str(int(time.time()))
    public_id=f'chapteroflife/{TODAY}-{int(time.time())}-{kind}'
    args={'public_id':public_id,'timestamp':timestamp,'overwrite':'false'}
    sig='&'.join(f'{k}={v}' for k,v in sorted(args.items()))+secret
    signature=hashlib.sha1(sig.encode()).hexdigest()
    with Path(path).open('rb') as file:
        resp=requests.post(f'https://api.cloudinary.com/v1_1/{cloud}/{kind}/upload',
           data={**args,'api_key':key,'signature':signature},files={'file':file},timeout=180)
    return api_json(resp)['secure_url']


def publish(media_url, caption):
    uid=required('IG_USER_ID')
    params={'caption':caption}
    if FORMAT=='reel':
        params.update({'media_type':'REELS','video_url':media_url,'share_to_feed':'true'})
    else: params['image_url']=media_url
    creation_id=ig('POST',f'{uid}/media',params)['id']
    for _ in range(30):
        time.sleep(10 if FORMAT=='reel' else 4)
        status=ig('GET',str(creation_id),{'fields':'status_code'})['status_code']
        if status=='FINISHED': break
        if status in ('ERROR','EXPIRED'): raise RuntimeError('Meta rejected media container: '+status)
    else: raise TimeoutError('Media container not ready. Did not publish.')
    return ig('POST',f'{uid}/media_publish',{'creation_id':creation_id})['id']


def topics_to_generate():
    if TOPIC_OVERRIDE=='all':
        if MODE=='publish': raise ValueError('TOPIC_OVERRIDE=all is preview-only')
        return ['self_respect','love','overthinking']
    if TOPIC_OVERRIDE=='auto': return [DAY_THEMES[DOW]]
    if TOPIC_OVERRIDE not in THEMES: raise ValueError('Unknown topic: '+TOPIC_OVERRIDE)
    return [TOPIC_OVERRIDE]


def process_one(topic,demo=False):
    if demo:
        samples={
            'self_respect':{'heading':'ख़ुद को भी चुनो','quote':'हर बार समझाना ज़रूरी नहीं,\nकभी अपनी ख़ामोशी भी सुनो।\nसबको अपना बना लेना आसान है,\nख़ुद का साथ निभाना सीखो।', 'caption':'Self respect begins when you stop treating your needs as an afterthought. Kindness and boundaries can exist together. You can care for others and still protect your peace. Relationships become healthier when your voice matters too. This is a reminder to honour your emotional space without guilt. Which boundary helped you grow? #SelfRespect #HealthyBoundaries #LifeLessons #InnerPeace #ChapterOfLife'},
            'love':{'heading':'प्यार की पहचान','quote':'तुम्हारे साथ हँसना अच्छा है,\nपर मेरी उदासी भी सुन लेना।\nप्यार ख़ुशी में साथ भर नहीं,\nमुश्किल दिनों में भी ठहरना है।', 'caption':'A meaningful relationship is not made from perfect photographs. It grows through listening, patience, everyday kindness and emotional trust. Real love allows two people to be honest even when life is difficult. It is about feeling safe while being fully yourself. Real care is found in little ordinary moments, not just celebrations. What makes you feel understood in a relationship? #LoveAndRelationships #EmotionalConnection #Trust #RealLove #ChapterOfLife'},
            'overthinking':{'heading':'रात के ख़याल','quote':'रात में सब सवाल लौटते हैं,\nजो दिन भर हँसी में छिपाए।\nपर हर जवाब आज नहीं मिलता,\nकुछ सुकून सुबह भी लाती है।', 'caption':'Late night overthinking can make every thought feel urgent. Sometimes the kinder choice is to rest rather than solve your entire life at midnight. Emotional wellbeing also means allowing yourself space to pause. Not every worry deserves an answer tonight. Giving yourself permission to pause is a small act of compassion. What helps you feel calm after a long day? #Overthinking #LateNightThoughts #MentalWellbeing #QuietMoments #ChapterOfLife'},
        }
        return samples.get(topic,samples['love'])
    return generate_content(topic)


def main():
    demo='--demo' in sys.argv
    if not demo: verify_connection()
    if MODE=='verify' and not demo:
        print('VERIFY ONLY - nothing generated, uploaded or published')
        return
    if MODE=='publish':
        if not (os.getenv('PUBLISH_CONFIRMATION','').strip().upper()=='YES' or
                os.getenv('AUTOPUBLISH_ENABLED','').strip().lower()=='true'):
            raise RuntimeError('Live publishing requires explicit confirmation or AUTOPUBLISH_ENABLED=true')
        if MARKER.exists():
            print('Already published today, skipping duplicate.'); return
    topics=topics_to_generate() if not demo else ['self_respect','love','overthinking']
    for topic in topics:
        content=process_one(topic,demo=demo)
        suffix=topic if len(topics)>1 else ''
        fn='_'+suffix if suffix else ''
        (OUT/f'content{fn}.json').write_text(json.dumps(content,ensure_ascii=False,indent=2),encoding='utf-8')
        (OUT/f'caption{fn}.txt').write_text(content['caption']+'\n',encoding='utf-8')
        image_path,media_path=render_post(content,topic,kind=FORMAT,suffix=suffix)
        print('Built premium scenic preview:',image_path.name, 'theme:',topic)
        if MODE=='preview' or demo: continue
        if MODE=='publish':
            asset_type='video' if FORMAT=='reel' else 'image'
            url=cloudinary_upload(media_path,asset_type)
            media_id=publish(url,content['caption'])
            MARKER.parent.mkdir(exist_ok=True)
            MARKER.write_text(json.dumps({'date':TODAY,'format':FORMAT,'media_id':media_id,
                'theme':topic,'quote':content['quote'],'heading':content['heading']},ensure_ascii=False,indent=2),encoding='utf-8')
            print('Published successfully, media ID suffix:',str(media_id)[-5:])
    if MODE=='preview' or demo:
        print('PREVIEW ONLY — no Cloudinary upload or Instagram publish performed.')


if __name__=='__main__': main()
