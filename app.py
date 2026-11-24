# -*- coding: utf-8 -*-
"""시아애비 블로그 자동작성기: Windows 전용, 사용자 확인 후 네이버 임시저장 시도."""
import os, re, io, json, time, threading, queue, webbrowser, html, urllib.request, urllib.error, hashlib, tempfile, subprocess, sys, shutil
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

APP_VERSION = 'v18.18'
RELEASES_API = 'https://api.github.com/repos/jungcheehyun/siaaebi-blog-writer/releases/latest'
UPDATE_ASSET = 'siaaebi-update.zip'
CHECKSUM_ASSET = 'siaaebi-update.zip.sha256'
ROOT = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent

def apply_app_icon(root):
    """Use the same pencil-baby icon for the application window and taskbar.

    PyInstaller packs these files under sys._MEIPASS; the .exe itself also embeds
    this .ico via --icon, so updates change the taskbar/Explorer icon too.
    """
    resource_root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
    png = resource_root / 'siaaebi_icon.png'
    ico = resource_root / 'siaaebi_icon.ico'
    if png.is_file():
        try:
            root._siaaebi_icon = tk.PhotoImage(file=str(png))
            root.iconphoto(True, root._siaaebi_icon)
        except tk.TclError:
            pass
    if ico.is_file() and os.name == 'nt':
        try:
            root.iconbitmap(str(ico))
        except tk.TclError:
            pass


def version_parts(value):
    raw = str(value).strip().lower().lstrip('v')
    if not re.fullmatch(r'\d+(?:\.\d+){0,3}', raw):
        raise ValueError('버전 번호 형식이 올바르지 않습니다: ' + str(value))
    return tuple(int(v) for v in raw.split('.')) + (0,) * (4-len(raw.split('.')))

def github_get(url, timeout=15):
    request = urllib.request.Request(url, headers={
        'User-Agent': 'SiaAebiBlogWriter-Updater/1.0',
        'Accept': 'application/vnd.github+json' if url == RELEASES_API else 'application/octet-stream'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()

def latest_release():
    release = json.loads(github_get(RELEASES_API).decode('utf-8'))
    tag = release.get('tag_name', '')
    version_parts(tag)
    assets = {a.get('name'): a.get('browser_download_url') for a in release.get('assets', [])}
    return tag, assets

def prepare_update(assets):
    if not assets.get(UPDATE_ASSET) or not assets.get(CHECKSUM_ASSET):
        raise ValueError('업데이트 ZIP 또는 SHA256 파일이 없습니다.')
    expected = github_get(assets[CHECKSUM_ASSET]).decode('utf-8').strip().split()[0].lower()
    if not re.fullmatch(r'[0-9a-f]{64}', expected):
        raise ValueError('SHA256 파일 형식이 잘못되었습니다.')
    payload = github_get(assets[UPDATE_ASSET], timeout=120)
    if len(payload) > 300_000_000:
        raise ValueError('업데이트 ZIP이 너무 큽니다.')
    if hashlib.sha256(payload).hexdigest() != expected:
        raise ValueError('다운로드 파일의 SHA256 값이 일치하지 않습니다.')
    import zipfile
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        names = z.namelist()
        if not 'SiaAebiBlogWriter.exe' in names:
            raise ValueError('Windows EXE 배포 파일이 아닙니다.')
        if any(n.startswith('/') or '..' in Path(n).parts or '\\\\' in n for n in names):
            raise ValueError('안전하지 않은 ZIP 경로입니다.')
    folder = Path(tempfile.mkdtemp(prefix='siaaebi_exe_update_'))
    archive = folder / UPDATE_ASSET
    archive.write_bytes(payload)
    return archive

OUTPUT = ROOT / '작성결과'
OUTPUT.mkdir(exist_ok=True)
# Shared across versions, so saved screen positions survive extracting a new ZIP.
CONFIG_DIR = Path(os.getenv('LOCALAPPDATA') or (Path.home() / 'AppData' / 'Local')) / 'SiaAebiBlogWriter'
CONFIG_PATH = CONFIG_DIR / 'editor_positions.json'
POSITION_FIELDS = ('photo_button', 'body_point', 'quote_button',
                   'subtitle_quote_style', 'question_quote_style', 'final_quote_style')

STYLE_SAMPLE_PATH = CONFIG_DIR / 'style_sample.txt'

def load_style_sample():
    try:
        return STYLE_SAMPLE_PATH.read_text(encoding='utf-8')[:4500]
    except OSError:
        return ''

def save_style_sample(value):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    STYLE_SAMPLE_PATH.write_text(value[:4500], encoding='utf-8')

def load_editor_positions():
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
        result = {}
        for key in POSITION_FIELDS:
            point = data.get(key)
            if isinstance(point, list) and len(point) == 2 and all(isinstance(v, int) and v >= 0 for v in point):
                result[key] = tuple(point)
        offset = data.get('quote_exit_offset', 500)
        result['quote_exit_offset'] = offset if isinstance(offset, int) and 100 <= offset <= 1500 else 500
        result['body_anchor_verified'] = data.get('body_anchor_verified') is True
        return result
    except (OSError, ValueError, TypeError):
        return {'quote_exit_offset': 500, 'body_anchor_verified': False}

def save_editor_positions(values):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    payload = {key: list(getattr(values, key)) if getattr(values, key) else None
               for key in POSITION_FIELDS}
    payload['quote_exit_offset'] = int(values.quote_exit_offset.get())
    payload['body_anchor_verified'] = bool(getattr(values,'body_anchor_verified',False))
    tmp = CONFIG_PATH.with_suffix('.tmp')
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(CONFIG_PATH)

EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}


def natural_photo_key(path):
    """Sort like Windows Explorer: 1, 2, ..., 9, 10, 11 rather than 1, 10, 11, 2."""
    return tuple((0, int(part)) if part.isdigit() else (1, part.casefold())
                 for part in re.split(r'(\d+)', Path(path).name))


def sorted_photos(folder):
    return sorted((p for p in Path(folder).iterdir() if p.is_file() and p.suffix.lower() in EXTS),
                  key=natural_photo_key)


def photo_topic(path, index):
    """Filename is a weak hint only; never infer the image contents from a number."""
    stem=Path(path).stem
    stem=re.sub(r'(?i)^(img|dsc|photo|kakaotalk)[_\- ]*', '', stem)
    stem=re.sub(r'[0-9_\- ]+', ' ', stem).strip()
    return stem if len(stem)>=2 and re.search(r'[가-힣]',stem) else ''


def _safe_question(subject, position, menu):
    """Fallback does not pretend to know what an unanalysed photo shows."""
    if subject:
        return f'{subject} 이야기도 궁금하시죠?'
    options=[f'{menu}를 고른 이유가 궁금하시죠?',
             '매장에 들어서면 어떤 느낌일까요?',
             '주문하면서 눈여겨볼 점은 뭘까요?',
             f'{menu}와 함께 즐길 만한 건 뭘까요?',
             '방문 전에 알아두면 좋은 점은요?',
             '이번 방문에서 기억에 남는 부분은요?']
    return options[position % len(options)]


def compose(shop, menu, notes, photos, sections=None, title=None, target_chars=1500, must_include="", keywords="", ai_intro=None, ai_closing=None):
    """Preserve photo order; ground claims in user notes or AI image interpretation."""
    shop=shop.strip() or '오늘의 맛집'
    menu=menu.strip() or '대표 메뉴'
    intro=(f'안녕하세요 여러분\n\n일상과 맛집을 공유하는 시아애비예요\n\n'
           f'오늘은 {shop} 이야기를 들려드리려고 해요\n\n'
           f'{menu}를 중심으로 어떤 곳이었는지 함께 살펴볼게요')
    if ai_intro and str(ai_intro).strip():
        intro=str(ai_intro).strip()
    elif notes.strip():
        intro+='\n\n'+notes.strip()
    subtitle=make_subtitle(shop, menu, keywords)
    blocks=[{'type':'hero_quote','value':subtitle},{'type':'text','value':intro}]
    valid=[]
    for section in (sections or []):
        if isinstance(section,dict) and isinstance(section.get('q'),str) and isinstance(section.get('a'),str):
            valid.append(section)
    for i,photo in enumerate(photos):
        if i<len(valid):
            q=re.sub(r'^Q\.?\s*','',valid[i]['q'],flags=re.I).strip()
            a=re.sub(r'^A\.?\s*','',valid[i]['a'],flags=re.I).strip()
        else:
            raise ValueError('사진에 맞는 질문과 답변을 생성하지 못했습니다. AI 원고를 다시 생성해 주세요.')
        if not q or re.search(r'방문\s*사진\s*\d+|사진\s*\d+|\bIMG[_ ]?\d+',q,re.I):
            q=_safe_question('',i,menu)
        if not a: raise ValueError('답변이 비어 있습니다. AI 원고를 다시 생성해 주세요.')
        blocks.extend([{'type':'question','value':'Q. '+q},
                       {'type':'image','path':str(photo),'caption':''},
                       {'type':'answer_label','value':'A.'},
                       {'type':'text','value':a}])
    phrases=[line.strip() for line in must_include.splitlines() if line.strip()]
    # User-authored words are not fabricated. Place them in the natural wrap-up,
    # rather than generating an artificial extra Q&A section.
    closing=(f'오늘은 {shop} 이야기를 전해드렸는데요\n\n'
             f'{menu}가 궁금했던 분들께 조금이나마 도움이 되었으면 좋겠어요')
    if ai_closing and str(ai_closing).strip(): closing=str(ai_closing).strip()
    if phrases: closing+='\n\n'+'\n'.join(phrases)
    closing+='\n\n다음에도 재미있는 이야기로 찾아올게요\n\n지금까지 시아애비였습니다! ❤️'
    blocks.extend([{'type':'final_quote','value':'마무리한마디'},
                   {'type':'text','value':closing},
                   {'type':'text','value':' '.join('#'+re.sub(r'\s+','',w) for w in [shop,menu,'맛집후기','시아애비'] if w.strip())}])
    return {'title':make_hook_title(shop,menu,title),'blocks':blocks}


def make_subtitle(shop, menu, keywords=""):
    """Keep the business name and user-provided search keywords in the quote."""
    shop=re.sub(r'\s+', ' ', str(shop or '').strip())
    menu=re.sub(r'\s+', ' ', str(menu or '').strip())
    keywords=re.sub(r'[,;/]+', ' ', str(keywords or '').strip())
    keywords=re.sub(r'\s+', ' ', keywords)
    bits=[]
    for value in (shop, menu, keywords):
        if value and value not in ' '.join(bits):
            bits.append(value)
    if not bits:
        raise ValueError('상호명 또는 부제목을 입력하세요.')
    return ' '.join(bits)


def make_hook_title(shop, menu, suggestion=None):
    """Curiosity-first title; business name belongs in the subtitle quote only."""
    shop=str(shop or '').strip()
    menu=str(menu or '맛집').strip()
    area='의정부' if '의정부' in shop else (shop.split()[0] if shop else '여기')
    names=[shop]
    if ' ' in shop:
        names.append(shop.split()[-1])
    if suggestion:
        title=re.sub(r'\s+', ' ',str(suggestion).strip())
        if 5 <= len(title) <= 34 and not any(name and name in title for name in names):
            return title
    proposals=[
        f'{area}에 이런 {menu}집이 있었다고?',
        f'{area}에서 찾은 뜻밖의 {menu} 맛집!',
        f'{menu} 좋아하면 여긴 궁금할걸?',
    ]
    for title in proposals:
        if len(title)<=32 and not any(name and name in title for name in names):
            return title
    return '이런 맛집이 있었다고?'

KOREAN_NUMBERS = {
    '1000':'천', '2000':'이천', '3000':'삼천', '4000':'사천', '5000':'오천',
    '6000':'육천', '7000':'칠천', '8000':'팔천', '9000':'구천',
    '10000':'만원', '11000':'만 천원', '12000':'만 이천원',
    '13000':'만 삼천원', '14000':'만 사천원', '15000':'만 오천원',
    '16000':'만 육천원', '17000':'만 칠천원', '18000':'만 팔천원',
    '19000':'만 구천원', '20000':'이만원', '700':'칠백', '500':'오백'
}
def clean_blog_text(value):
    value=str(value).replace('\r','')
    value=re.sub(r'(?<!\d)\.(?!\d)', '', value) # 소수점은 보존
    value=re.sub(r'블로그에서는[^\n]*GIF[^\n]*', '', value)
    def money(m):
        n=m.group(1).replace(',','')
        word=KOREAN_NUMBERS.get(n)
        return (word if word.endswith('원') else word+'원') if word else m.group(0)
    value=re.sub(r'(?<!\d)(\d{1,3}(?:,\d{3})+|\d+)\s*원',money,value)
    # Q. / A. 표기는 사용자 지정 형식이므로 유지
    value=re.sub(r'(?m)^(Q|A)\s*$',r'\1.',value)
    value=re.sub(r'(?m)^(Q|A)\s+(?=\S)',r'\1. ',value)
    return value

def clean_data(data):
    shop=next((b['value'] for b in data['blocks'] if b['type']=='hero_quote'),'오늘의 맛집')
    data['title']=str(data.get('title','')).strip() or make_hook_title(shop,'맛집')
    for b in data['blocks']:
        if 'value' in b:
            v=clean_blog_text(b['value'])
            if b['type']=='question':v='Q. '+re.sub(r'^Q\.?\s*','',v)
            if b['type']=='final_quote':v=re.sub(r'^Q\.?\s*','',v).strip()
            if b['type']=='answer_label':v='A.'
            if b['type']=='text':
                v=re.sub(r'\n{2,}','\n',v)
            b['value']=v
    return data


PHOTO_MARKER=re.compile(r'^\s*(?:📸|📷|🖼️?)?\s*\[사진(?:\s+(\d+)(?:\s*[—–-]\s*[^\]]*)?)?\]\s*(.*?)\s*$',re.I)
SUBTITLE_MARKER = re.compile(r'^(?:\[부제목\]\s*|부제목\s*[:：]\s*)(.+)$', re.I)
FINAL_MARKER = re.compile(r'^(?:\[마무리\]|\[총평\]|마무리\s*[:：]|총평\s*[:：])\s*(.*)$',re.I)
PHOTO_MARKER_NATURAL = re.compile(r'^\s*(?:📸|📷|🖼️?)?\s*사진\s*([0-9]+)(?:\s*[—–:-]\s*.*)?\s*$', re.I)

def strip_draft_markdown(value):
    """Remove copy/pasted Markdown styling from standalone lines."""
    line = str(value).strip()
    if line.startswith('**') and line.endswith('**') and len(line) > 4:
        line = line[2:-2].strip()
    if line.startswith('__') and line.endswith('__') and len(line) > 4:
        line = line[2:-2].strip()
    return line

def parse_pasted_draft(raw,photos,default_subtitle=None):
    files={p.name.casefold():p for p in photos}
    blocks=[];buf=[];used=set();title='';in_final=False
    def flush():
        nonlocal in_final
        if buf:
            value='\n'.join(buf).strip()
            buf.clear()
            if value:
                if in_final:
                    blocks.append({'type':'final_quote','value':'마무리한마디'})
                    blocks.append({'type':'text','value':value})
                else:
                    blocks.append({'type':'text','value':value})
        in_final=False
    for original in raw.replace('\r','').split('\n'):
        line=strip_draft_markdown(original)
        if not line or line=='---':
            continue
        fm=FINAL_MARKER.fullmatch(line)
        if fm:
            flush()
            in_final=True
            if fm.group(1).strip():buf.append(fm.group(1).strip())
            continue
        match=PHOTO_MARKER.fullmatch(line)
        natural=PHOTO_MARKER_NATURAL.fullmatch(line) if not match else None
        if match or natural:
            flush()
            number,filename=match.groups() if match else (natural.group(1),'')
            if filename.strip():
                photo=files.get(Path(filename.strip()).name.casefold())
                if photo is None:raise ValueError('사진 파일 없음: '+filename)
                if number and (int(number)<1 or int(number)>len(photos) or photos[int(number)-1]!=photo):raise ValueError('사진 번호와 파일명이 다릅니다: '+line)
            elif number:
                index=int(number)-1
                if index<0 or index>=len(photos):raise ValueError('사진 번호 오류: '+number)
                photo=photos[index]
            else:raise ValueError('사진 번호 또는 파일명 필요: '+line)
            if str(photo) in used:raise ValueError('중복 사진: '+photo.name)
            used.add(str(photo))
            blocks.append({'type':'image','path':str(photo),'caption':''})
            continue
        subtitle_match=SUBTITLE_MARKER.fullmatch(line)
        markdown_subtitle=re.match(r'^#{2,4}\s+(.+)$',line) if title and not blocks and not buf else None
        quote_subtitle=re.match(r'^>\s*(.+)$',line) if title and not blocks and not buf else None
        if subtitle_match or markdown_subtitle or quote_subtitle:
            flush()
            if any(b['type']=='hero_quote' for b in blocks):
                raise ValueError('부제목 인용구는 하나만 사용할 수 있습니다.')
            value=(subtitle_match or markdown_subtitle or quote_subtitle).group(1).strip()
            if not value: raise ValueError('부제목 내용을 입력하세요.')
            blocks.append({'type':'hero_quote','value':value})
            continue
        # A hashtag is NOT a Markdown heading. Keep the leading # intact.
        if line.startswith('#') and not re.match(r'^#{1,6}\s+',line):
            flush()
            blocks.append({'type':'text','value':line})
            continue
        heading=re.sub(r'^#{1,6}\s+','',line)
        if not title and not blocks and not buf:title=heading
        elif re.match(r'^Q\.\s*',heading,re.I):
            flush()
            if re.search(r'총평|마무리|한마디|전체\s*평가',heading):
                in_final=True
            else:
                blocks.append({'type':'question','value':heading})
        elif re.fullmatch(r'A\.',heading,re.I):
            if not in_final:
                flush()
                blocks.append({'type':'answer_label','value':'A.'})
        else:buf.append(heading if line.startswith('#') else line)
    flush()
    if not any(b['type']=='hero_quote' for b in blocks):
        if default_subtitle and str(default_subtitle).strip():
            blocks.insert(0,{'type':'hero_quote','value':str(default_subtitle).strip()})
    unresolved=[b['value'] for b in blocks if b['type']=='text'
                and re.search(r'(?m)^\s*(?:📸|📷|🖼️?)?\s*사진\s*\d+\b',b['value'])]
    if unresolved:
        raise ValueError('인식할 수 없는 사진 표시가 있습니다. [사진 1] 또는 📸 사진 1 — 설명 형식을 사용하세요.')
    if not blocks:raise ValueError('원고를 입력하세요.')
    return clean_data({'title':title or '시아애비 방문 후기','blocks':blocks})

def default_draft(shop, menu, notes, photos, must_include="", keywords=""):
    """Without image analysis, don't fabricate photo-specific Q&A or repeat filler."""
    shop=shop.strip() or '방문한 곳'
    menu=menu.strip() or '메뉴'
    blocks=[{'type':'hero_quote','value':make_subtitle(shop, menu, keywords)}]
    if notes.strip():
        blocks.append({'type':'text','value':notes.strip()})
    else:
        blocks.append({'type':'text','value':'방문 후기를 작성하려면 실제 방문 메모를 적어 주세요'})
    for photo in photos:
        blocks.append({'type':'image','path':str(photo),'caption':''})
    if must_include.strip():
        blocks.append({'type':'text','value':must_include.strip()})
    blocks.append({'type':'text','value':'지금까지 시아애비였습니다! ❤️'})
    return {'title':make_hook_title(shop,menu),'blocks':blocks}


def ai_draft(api_key, shop, menu, notes, photos, must_include="", keywords="", style_sample=""):
    """OpenAI API calls do not have access to this ChatGPT conversation."""
    from openai import OpenAI
    from PIL import Image
    import base64

    client = OpenAI(api_key=api_key, timeout=180)
    instruction = (
        "당신은 자연스러운 한국어 맛집 블로그의 전문 공동 작가입니다. 필명은 시아애비입니다. "
        "사진의 순서를 유지하면서 실제 사람이 방문해 소개하는 것처럼 유기적으로 이어지는 후기를 써 주세요. "
        "글은 독자가 편하게 읽을 수 있는 친근한 존댓말이고, 말끝은 ~했어요, ~더라고요, ㅎㅎ 등을 지나치지 않게 섞으세요. "
        "사진마다 Q&A를 만들되 사진 자체에 대한 의미 없는 질문은 절대 금지합니다. "
        "금지 예: 방문 사진 1, 사진으로 보시죠, 사진에는 무엇이 있을까요, 다음 사진은, 이번 사진에서 보이는 것은, 이 장면, 이 장면도, 남겨둔 기록, 사진에 담긴 구체적인 내용은 직접 확인해 주세요. "
        "독자가 해당 방문 장소에 대해 실제로 궁금해할 질문을 사진에 드러난 구체적인 내용과 앞뒤 맥락에서 고르세요. "
        "반복되는 문장 시작, 뻔한 광고 표현, 과한 느낌표, 로봇처럼 나열하는 문체를 제거하세요. "
        "한 질문에 대한 답변은 2~4문장으로 리듬감 있게 쓰되 사진 설명만 나열하지 말고 방문 이야기가 자연스럽게 이어지도록 하세요. "
        "사진으로 알 수 없는 맛, 가격, 주문 경험, 주차, 서비스, 감정, 가족 구성은 임의로 만들어내면 안 됩니다. "
        "방문 메모는 사용자가 직접 확인한 사실로 존중하지만 필요하다면 문장만 자연스럽게 다듬으세요. "
        "글투 참고 예시는 문체만 참고하고 그 글에 담긴 가게 정보나 경험을 현재 방문기로 옮기지 마세요. "
        "도입문(intro)은 2~4문장 정도의 자연스러운 인사와 장소 소개로 직접 작성하세요. "
        "마무리(closing)는 이 방문에서 확인한 사항을 정리하며 읽는 이에게 도움이 되는 자연스러운 소감으로 쓰세요. "
        "상호명은 적절히 사용하되 자꾸 반복하지 마세요. 제목은 모바일에서 읽기 좋은 짧은 형태로 작성하세요. "
        "문장 끝 마침표는 생략하고 친근한 존댓말을 유지하세요. "
        "필수 문구는 프로그램에서 원문 그대로 삽입하므로 AI는 중복해서 쓰지 마세요. "
        "사진 수와 sections 개수는 반드시 같아야 하며 사진 순서를 절대 바꾸면 안 됩니다. "
        "JSON 객체만 반환하세요. 필드: title(문자열), intro(문자열), sections(순서대로 q,a 쌍), closing(문자열).\n"
        f"상호명: {shop}\n주문/대표 메뉴: {menu}\n직접 방문 메모: {notes}\n"
        f"필수 문구: {must_include}\n강조 키워드: {keywords}\n사진 수: {len(photos)}\n"
        f"문체 참고 예시(사실로 사용 금지):\n{style_sample[:4500]}"
    )
    content = [{"type": "text", "text": instruction}]
    for i, p in enumerate(photos):
        with Image.open(p) as im:
            im.seek(0)
            im = im.convert("RGB")
            im.thumbnail((1100, 1100))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=82)
        content.append({"type": "text", "text": f"{i+1}번 사진, 이 순서로 질문과 답변을 작성하세요. 파일명은 사진 내용의 근거가 아닙니다."})
        content.append({"type": "image_url", "image_url": {
            "url": "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode(), "detail": "high"}})
    result = client.chat.completions.create(
        model="gpt-4.1",
        messages=[{"role": "user", "content": content}],
        response_format={"type": "json_object"}
    )
    raw = result.choices[0].message.content
    if not raw:
        raise ValueError("AI에서 원고를 받지 못했습니다. 다시 원고 생성을 눌러 주세요.")
    obj = json.loads(raw)
    sections = obj.get("sections", [])
    if not isinstance(sections, list) or len(sections) != len(photos):
        raise ValueError(f"사진은 {len(photos)}장인데 생성된 문단이 {len(sections) if isinstance(sections,list) else 0}개입니다. 다시 원고 생성을 눌러 주세요.")
    return compose(shop, menu, notes, photos, sections, obj.get("title"),
                   must_include=must_include, keywords=keywords,
                   ai_intro=obj.get("intro"), ai_closing=obj.get("closing"))


def save_preview(data):
    (OUTPUT/'원고.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    pieces=[]
    for block in data['blocks']:
        typ=block['type']
        if typ=='hero_quote':
            pieces.append('<div class="heroquote"><span>❝</span><em>'+html.escape(block['value'])+'</em><span>❞</span></div>')
        elif typ=='question':
            pieces.append('<blockquote class="question"><span class="quote-mark">❝</span><span class="quote-text">'+html.escape(block['value'])+'</span><span class="quote-underline"></span></blockquote>')
        elif typ=='final_quote':
            pieces.append('<blockquote class="final-frame">'+html.escape(block['value'])+'</blockquote>')
        elif typ=='answer_label':
            pieces.append('<p class="answer-label">A.</p>')
        elif typ=='text':
            for para in block['value'].split('\n'):
                if para.strip():pieces.append('<p>'+html.escape(para)+'</p>')
        elif typ=='image':
            uri=Path(block['path']).resolve().as_uri()
            pieces.append('<figure><img src="'+uri+'"><figcaption>'+html.escape(block.get('caption',''))+'</figcaption></figure>')
    # 모바일 본문 폭을 기준으로 미리보기. 텍스트는 모두 왼쪽, 사진만 가운데.
    style = """
    *{box-sizing:border-box}
    body{font-family:"Malgun Gothic",Arial,sans-serif;max-width:390px;
         margin:18px auto;padding:16px;color:#666;line-height:1.85;font-size:15px;
         text-align:left;overflow-wrap:break-word}
    h1{font-size:24px;font-weight:400;color:#333;line-height:1.5;
       margin:0 0 24px;text-align:left;white-space:nowrap;font-size:clamp(13px,4.4vw,20px)}
    p{margin:0 0 14px;white-space:pre-wrap;text-align:left}
    .heroquote{display:flex;align-items:flex-start;flex-direction:column;gap:7px;
       margin:14px 0 25px;text-align:left;color:#888;font-family:Georgia,serif;font-size:18px}
    .heroquote span{font-size:26px;color:#bbb;line-height:1}
    .heroquote em{font-size:clamp(11px,3.5vw,15px);text-align:left;white-space:nowrap}
    .question{margin:36px 0 22px;padding:8px 0;border:0;background:none;
       font-weight:500;color:#555;font-size:17px;display:flex;flex-direction:column;
       align-items:flex-start;gap:7px;text-align:left}
    .quote-mark{color:#999;font-family:Georgia,serif;font-size:25px;line-height:1}
    .quote-text{font-size:17px;text-align:left}
    .quote-underline{height:2px;background:#888;width:105px;display:block}
    figure{margin:18px auto 26px;text-align:center;width:100%}
    figure img{display:block;max-width:100%;width:auto;max-height:620px;
       height:auto;object-fit:contain;margin:0 auto}
    figcaption{color:#888;font-size:12px;text-align:center;margin-top:6px}
    .answer-label{margin:18px 0 12px!important;text-align:left}
    .final-frame{margin:30px 0 15px;border:2px solid #999;padding:14px 18px;
       font-size:17px;font-weight:600;display:block;text-align:left}
    @media(max-width:420px){body{max-width:100%;margin:0 auto;padding:14px}}
    """
    doc='<!doctype html><html lang="ko"><meta charset="utf-8"><title>'+html.escape(data['title'])+'</title><style>'+style+'</style><h1>'+html.escape(data['title'])+'</h1>'+''.join(pieces)+'</html>'
    out=OUTPUT/'블로그_미리보기.html';out.write_text(doc,encoding='utf-8');return out


def clipboard_image(path):
    import win32clipboard  # pywin32 (requirements 참조)
    from PIL import Image
    with Image.open(path) as im:
        im.seek(0)
        output = io.BytesIO()
        im.convert('RGB').save(output, 'BMP')
    dib = output.getvalue()[14:]
    for attempt in range(5):
        try:
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardData(win32clipboard.CF_DIB, dib)
            finally:
                win32clipboard.CloseClipboard()
            return
        except Exception:
            time.sleep(.3)
    raise RuntimeError('이미지 클립보드 복사 실패')


def tidy_text(value):
    """Remove blank lines while retaining intentional single line breaks."""
    lines=[re.sub(r'[ \t]+', ' ', line).strip() for line in str(value).replace('\r','').split('\n')]
    return '\n'.join(line for line in lines if line)


class InputCancelled(Exception):
    pass

def check_control(pause_event=None, stop_event=None):
    if stop_event is not None and stop_event.is_set():
        raise InputCancelled('F9로 자동 입력을 중지했습니다')
    if pause_event is not None:
        while not pause_event.wait(.1):
            if stop_event is not None and stop_event.is_set():
                raise InputCancelled('F9로 자동 입력을 중지했습니다')
    if stop_event is not None and stop_event.is_set():
        raise InputCancelled('F9로 자동 입력을 중지했습니다')

def safe_naver_typing_text(value):
    """Avoid replacement diamonds from unsupported astral emoji/variation selectors."""
    result = []
    for ch in str(value):
        cp = ord(ch)
        if ch == '\ufffd' or cp > 0xFFFF or cp in (0x200D, 0x20E3) or 0xFE00 <= cp <= 0xFE0F:
            continue
        result.append(ch)
    return ''.join(result)

def type_unicode_text(value, chars_per_minute=850, pause_event=None, stop_event=None):
    """Windows Unicode SendInput: key events, not clipboard paste.
    500 characters/minute is only an approximation of Korean 500 타/minute.
    """
    import ctypes
    from ctypes import wintypes
    import pyautogui
    user32=ctypes.windll.user32
    INPUT_KEYBOARD=1; KEYEVENTF_UNICODE=0x0004; KEYEVENTF_KEYUP=0x0002
    ULONG_PTR=ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p)==8 else ctypes.c_ulong
    class KEYBDINPUT(ctypes.Structure):
        _fields_=[('wVk',wintypes.WORD),('wScan',wintypes.WORD),('dwFlags',wintypes.DWORD),('time',wintypes.DWORD),('dwExtraInfo',ULONG_PTR)]
    class _INPUT_UNION(ctypes.Union):
        _fields_=[('ki',KEYBDINPUT),('padding',ctypes.c_byte*32)]
    class INPUT(ctypes.Structure):
        _fields_=[('type',wintypes.DWORD),('union',_INPUT_UNION)]
    delay=60.0/max(1,chars_per_minute)
    for char in tidy_text(safe_naver_typing_text(value)):
        check_control(pause_event,stop_event)
        if char=='\n':
            pyautogui.press('enter')
        else:
            # Windows SendInput with UTF-16 units supports Hangul and emoji.
            units=char.encode('utf-16-le')
            for off in range(0,len(units),2):
                unit=int.from_bytes(units[off:off+2],'little')
                for flags in (KEYEVENTF_UNICODE,KEYEVENTF_UNICODE|KEYEVENTF_KEYUP):
                    ev=INPUT();ev.type=INPUT_KEYBOARD
                    ev.union.ki=KEYBDINPUT(0,unit,flags,0,0)
                    if user32.SendInput(1,ctypes.byref(ev),ctypes.sizeof(INPUT))!=1:
                        raise RuntimeError('Windows 키보드 입력에 실패했습니다.')
        time.sleep(delay)


def _wait_for_native_file_dialog(timeout=8.0):
    """Return true only when the foreground Windows file picker is active."""
    import win32gui
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        try:
            hwnd=win32gui.GetForegroundWindow()
            if hwnd and win32gui.GetClassName(hwnd)=='#32770':
                return True
        except Exception:
            pass
        time.sleep(.2)
    return False


def upload_via_naver_button(path, photo_button, notify):
    """Fail closed when Windows file picker is missing; never type path into blog."""
    import pyautogui, pyperclip
    if not photo_button:
        raise RuntimeError('네이버 사진 첨부 버튼 위치가 지정되지 않았습니다.')
    path=Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f'사진 파일이 존재하지 않습니다: {path}\n원고 생성 후 사진 폴더를 옮겼다면 원고를 다시 생성하세요.')
    if not _wait_for_native_file_dialog(timeout=.3):
        # Naver SmartEditor toolbar: click the green '사진' icon itself,
        # not the media menu or the editor body.
        x, y = photo_button
        width, height = pyautogui.size()
        if not (0 <= x < width and 0 <= y < height):
            raise RuntimeError(f'저장된 사진 버튼 좌표 {(x, y)}가 현재 화면 범위를 벗어났습니다. 위치를 다시 지정하세요.')
        notify(f'상단 초록색 [사진] 버튼 클릭: ({x}, {y})')
        pyautogui.moveTo(x, y, duration=.3)
        pyautogui.click(x=x, y=y)
    if not _wait_for_native_file_dialog(timeout=8.0):
        raise RuntimeError(
            '상단 [사진] 버튼 클릭 후 Windows 파일 선택 창을 확인하지 못했습니다.\n'
            '네이버 글쓰기 창을 최대화하고 [네이버 사진 버튼 위치 지정 (5초)]으로 '
            '초록색 [사진] 아이콘의 위치를 다시 저장하세요.\n'
            '잘못된 위치에 파일 경로를 입력하지 않고 안전하게 중지했습니다.')
    # Prefer the actual Windows native File name control over keyboard shortcuts.
    # On some Windows 11/OneDrive dialogs Alt+N/Ctrl+V targets a different field.
    import ctypes
    import win32gui
    from ctypes import wintypes
    dialog = win32gui.GetForegroundWindow()
    if not dialog or win32gui.GetClassName(dialog) != '#32770':
        raise RuntimeError('Windows 파일 선택 창이 활성화되어 있지 않습니다. 다시 시도해 주세요.')

    def dialog_closed():
        return not win32gui.IsWindow(dialog)

    def fill_native_filename():
        """Write and verify the Edit child of the File name combo by HWND."""
        controls = []
        name_combo = win32gui.GetDlgItem(dialog, 1148)
        def collect(child, _):
            if win32gui.GetClassName(child) == 'Edit' and win32gui.IsWindowVisible(child):
                rect = win32gui.GetWindowRect(child)
                if rect[2] - rect[0] > 70 and rect[3] - rect[1] > 10:
                    controls.append((rect[1], child))
        if name_combo:
            if win32gui.GetClassName(name_combo) == 'Edit':
                collect(name_combo, None)
            win32gui.EnumChildWindows(name_combo, collect, None)
        if not controls:
            # Fallback for a file picker whose filename edit has another ID.
            dlg_rect = win32gui.GetWindowRect(dialog)
            win32gui.EnumChildWindows(dialog, collect, None)
            controls = [item for item in controls
                        if item[0] > dlg_rect[1] + (dlg_rect[3] - dlg_rect[1]) * .55]
        if not controls:
            return False
        # File name is below the file grid, while Search and Address are above it.
        edit = sorted(controls, reverse=True)[0][1]
        user32 = ctypes.WinDLL('user32', use_last_error=True)
        user32.SendMessageTimeoutW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
                                               wintypes.LPARAM, wintypes.UINT, wintypes.UINT,
                                               ctypes.POINTER(ctypes.c_size_t))
        user32.SendMessageTimeoutW.restype = wintypes.LPARAM
        def send(msg, arg, timeout_ms=2500):
            result = ctypes.c_size_t()
            ok = user32.SendMessageTimeoutW(edit, msg, 0, arg, 2, timeout_ms, ctypes.byref(result))
            return bool(ok)
        full_name = str(path)
        value = ctypes.create_unicode_buffer(full_name)
        if not send(0x000C, ctypes.addressof(value)):  # WM_SETTEXT
            return False
        check = ctypes.create_unicode_buffer(max(32768, len(full_name) + 1))
        if not send(0x000D, ctypes.addressof(check)):  # WM_GETTEXT
            return False
        return os.path.normcase(check.value.strip().strip('"')) == os.path.normcase(full_name)

    try:
        opened = fill_native_filename()
    except Exception as e:
        notify('Windows 기본 파일명 입력 확인 실패, 대체 방식으로 전환: ' + str(e))
        opened = False
    if opened:
        notify('Windows 사진 파일 이름 칸에 전체 경로 입력 확인: ' + path.name)
        # Clicking the actual Open button commits the combo box value.
        try:
            open_button = win32gui.GetDlgItem(dialog, 1)  # IDOK
            if open_button and win32gui.IsWindowVisible(open_button):
                left, top, right, bottom = win32gui.GetWindowRect(open_button)
                pyautogui.click((left + right) // 2, (top + bottom) // 2)
            else:
                pyautogui.press('enter')
        except Exception:
            pyautogui.press('enter')
        for _ in range(28):
            if dialog_closed():
                break
            time.sleep(.25)

    if not dialog_closed():
        # Fallback 1: use the localized File name shortcut.
        notify('사진 선택 창이 열려 있어 Alt+N 방식으로 다시 시도합니다')
        pyautogui.hotkey('alt', 'n')
        time.sleep(.3)
        pyperclip.copy(str(path))
        pyautogui.hotkey('ctrl', 'a')
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(.35)
        pyautogui.press('enter')
        for _ in range(20):
            if dialog_closed():
                break
            time.sleep(.25)

    # Do NOT use Ctrl+L with a full image path. When focus changes unexpectedly
    # it may open the image in a browser/viewer rather than upload to Naver.
    if not dialog_closed():
        raise RuntimeError(
            '사진 파일 선택 창이 그대로 열려 있어 자동입력을 중단했습니다: '
            + path.name + '. 파일 이름 칸에 정확한 경로가 들어갔는지 확인하세요.')
    # File dialog closing does NOT guarantee that Naver has received the image.
    # If a photo viewer or Explorer has focus, stop before typing A. into it.
    time.sleep(.65)
    active_hwnd = win32gui.GetForegroundWindow()
    active_class = win32gui.GetClassName(active_hwnd) if active_hwnd else ''
    active_title = win32gui.GetWindowText(active_hwnd) if active_hwnd else ''
    if active_class not in ('Chrome_WidgetWin_1', 'MozillaWindowClass'):
        raise RuntimeError(
            '사진 선택 후 네이버 브라우저가 활성화되지 않았습니다. '
            '사진이 뷰어로 열렸거나 다른 창에 포커스가 있을 수 있습니다. '
            '자동입력을 중단했습니다: ' + path.name + ' / 활성 창: ' + active_title[:70])
    notify('사진 선택 창 닫힘 · 네이버 화면 복귀 확인: ' + path.name)
    # Allow slower OneDrive/synced images to finish loading before A. is entered.
    time.sleep(6.0 if path.suffix.lower() != '.gif' else 7.5)
    notify('사진 처리 대기 완료: ' + path.name + ' (실제 게시글 이미지 표시 여부는 화면에서 확인)')


def apply_quote(quote_button, quote_style, notify):
    """Use actual SmartEditor quotation menu; both positions captured by user."""
    import pyautogui
    if not quote_button or not quote_style:
        raise RuntimeError('네이버 인용구 버튼과 따옴표 스타일 위치를 모두 지정해야 합니다')
    pyautogui.click(*quote_button)
    time.sleep(.45)
    pyautogui.click(*quote_style)
    time.sleep(.5)
    notify('네이버 실제 인용구 메뉴 선택 완료 — 화면에서 서식 적용 여부를 확인하세요')


def exit_final_quote(notify):
    """Exit final quotation at the CURRENT end of the document, not a stale screen point.

    SmartEditor often needs two Enter presses at the end of a quotation.
    The final Q is deliberately short; we avoid moving the caret by a fixed pixel
    distance, which previously landed in an old question/hashtag paragraph.
    """
    import pyautogui
    pyautogui.press('end')
    pyautogui.press('enter', presses=2, interval=.2)
    time.sleep(.45)
    notify('마무리한마디 프레임 종료: 다음 줄부터 일반 본문 입력')


def click_below_intro_quote(body_point, offset_px, notify):
    """Leave the first quotation by clicking in the ordinary body area below it.

    Naver SmartEditor can leave a caret *inside* a quote after Enter. Use an
    explicit click instead. The offset is screen pixels relative to the
    user-captured first-body position (adjustable for browser zoom/DPI).
    """
    import pyautogui
    if not body_point:
        raise RuntimeError('본문 시작 위치가 지정되지 않았습니다')
    screen_w, screen_h = pyautogui.size()
    x = max(8, min(int(body_point[0]), screen_w - 9))
    y = max(8, min(int(body_point[1]) + int(offset_px), screen_h - 45))
    pyautogui.click(x, y)
    time.sleep(.4)
    notify(f'인용구 밖 본문 클릭: ({x}, {y}) · 글이 인용구 밖에 입력되는지 확인하세요')


def automate_naver(data, notify, wait_for_focus, photo_button, body_point,
                   quote_button, subtitle_quote_style, question_quote_style, final_quote_style,
                   quote_exit_offset, pause_event, stop_event):
    """Foreground keyboard entry; never publishes or saves."""
    import pyautogui
    pyautogui.PAUSE=.08
    # Do not open another Naver tab on Input Start / F7.
    # The user has already prepared an existing SmartEditor tab.
    notify('이미 열어둔 네이버 글쓰기 화면을 사용합니다. 제목 칸을 클릭해 두세요')
    if not wait_for_focus():return
    for _ in range(50):
        check_control(pause_event,stop_event)
        time.sleep(.1)
    missing=[b['path'] for b in data['blocks'] if b['type']=='image' and not Path(b['path']).is_file()]
    if missing:
        raise FileNotFoundError('사진이 이동되거나 삭제되었습니다. 사진 폴더를 다시 선택하고 원고를 새로 생성하세요: '+str(missing[0]))
    type_unicode_text(data['title'],pause_event=pause_event,stop_event=stop_event)
    # Naver SmartEditor: Enter from the title transitions to the first body paragraph.
    # A previously saved body_point may now hit the title, concatenating the intro.
    # Do not click the old coordinate here; keep it for quote-exit only.
    if not body_point:
        raise RuntimeError('인용구 아래 본문 좌표가 지정되지 않았습니다')
    check_control(pause_event,stop_event)
    pyautogui.press('enter')
    time.sleep(.5)
    if body_point[1] <= quote_button[1] + 90:
        raise RuntimeError('본문 좌표가 상단 도구막대에 너무 가깝습니다. 네이버 글쓰기 본문 첫 줄을 다시 지정하세요.')
    pyautogui.click(*body_point)
    time.sleep(.55)
    notify(f'제목과 본문 분리: 본문 좌표 {body_point} 클릭 완료')
    previous=None
    blocks=data['blocks']
    for i,b in enumerate(blocks):
        check_control(pause_event,stop_event)
        kind=b['type']
        next_kind=blocks[i+1]['type'] if i+1<len(blocks) else None
        if kind=='image':
            notify('사진 ' + str(sum(1 for prev in blocks[:i+1] if prev['type']=='image'))
                   + '/' + str(sum(1 for item in blocks if item['type']=='image'))
                   + ' 첨부 시도: ' + Path(b['path']).name)
            upload_via_naver_button(b['path'],photo_button,notify)
            check_control(pause_event,stop_event)
            # The user specifically wants A. immediately after the photo.
            # NEVER synthesize an Enter after the photo: it creates a blank
            # paragraph in their editor. Move to the end only, then type A.
            # The editor must expose its normal post-image text caret.
            pyautogui.press('end')
        elif kind in ('hero_quote','question','final_quote'):
            if kind == 'final_quote':
                pyautogui.hotkey('ctrl','end')
                time.sleep(.25)
            if previous not in (None,'image'):
                pyautogui.press('enter')
            selected_style = (subtitle_quote_style if kind == 'hero_quote' else
                              final_quote_style if kind == 'final_quote' else question_quote_style)
            apply_quote(quote_button,selected_style,notify)
            type_unicode_text(b['value'],pause_event=pause_event,stop_event=stop_event)
            # For the *first* subtitle quotation only, explicitly leave the
            # quote by clicking below it. The question quote path is unchanged
            # since the user confirmed Q's line-and-quotation worked.
            # If the next block is a photo, keep the current behavior.
            # Otherwise click below the quotation so prose/A. is not typed
            # inside the quotation frame.
            if kind == 'hero_quote' and next_kind != 'image':
                check_control(pause_event,stop_event)
                click_below_intro_quote(body_point,quote_exit_offset,notify)
            elif kind == 'final_quote':
                check_control(pause_event,stop_event)
                if next_kind is not None: exit_final_quote(notify)
            elif kind == 'question' and next_kind != 'image':
                check_control(pause_event,stop_event)
                pyautogui.press('end')
                pyautogui.press('enter', presses=2, interval=.2)
        else:
            # The first prose block starts at the clicked location outside the
            # quotation; inserting Enter here could return to the quote.
            if previous not in (None,'image','hero_quote','question','final_quote','answer_label'):
                pyautogui.press('enter')
            type_unicode_text(b['value'],pause_event=pause_event,stop_event=stop_event)
            if kind == 'answer_label':
                pyautogui.press('enter')  # Keep A. on its own line.
        previous=kind
        notify(f'입력 중: {i+1}/{len(data["blocks"])}')
    notify('입력 완료 — 인용구 뒤 본문 분리, 마지막 프레임, 사진 다음 A. 위치를 확인하세요. 임시저장은 직접 눌러 주세요')

class App:
    @staticmethod
    def configure_modern_style(root):
        # Native ttk theme, no third-party UI runtime dependency.
        style=ttk.Style(root)
        if 'clam' in style.theme_names():
            style.theme_use('clam')
        bg='#F5F7FB'; surface='#FFFFFF'; ink='#1E293B'
        root.configure(bg=bg)
        style.configure('.', font=('맑은 고딕', 10), background=bg, foreground=ink)
        style.configure('TFrame', background=bg)
        style.configure('TLabel', background=bg, foreground=ink, padding=(0,2))
        style.configure('TLabelframe', background=bg, bordercolor='#DDE3ED', relief='solid')
        style.configure('TLabelframe.Label', background=bg, foreground='#334155', font=('맑은 고딕',10,'bold'))
        style.configure('TEntry', padding=(10,8), fieldbackground=surface, bordercolor='#CBD5E1')
        style.configure('TButton', padding=(12,9), background=surface, foreground=ink,
                        bordercolor='#D4DBE7', relief='flat')
        style.map('TButton', background=[('active','#E8EDF7'),('pressed','#DCE5F5')])
        style.configure('Accent.TButton', background='#2563EB', foreground='#FFFFFF',
                        bordercolor='#2563EB', font=('맑은 고딕',10,'bold'), padding=(14,10))
        style.map('Accent.TButton', background=[('active','#1D4ED8'),('pressed','#1E40AF')])
        style.configure('TCheckbutton', background=bg, foreground=ink)
        style.configure('TSpinbox', padding=(5,4))
    def __init__(self,root):
        self.root=root;root.title(f'시아애비 블로그 자동작성기 {APP_VERSION}');root.geometry('1040x810')
        self.configure_modern_style(root)
        self.folder=tk.StringVar(value=str(ROOT/'예제사진'))
        self.shop=tk.StringVar(value='')
        self.menu=tk.StringVar(value='')
        self.api=tk.StringVar(value=os.getenv('OPENAI_API_KEY',''))
        self.use_ai=tk.BooleanVar(value=False)
        self.data=None;self.event=threading.Event();self.pause_event=threading.Event();self.pause_event.set();self.running=False;self.cancel=False;self.stop_event=threading.Event();self.photo_button=None;self.body_point=None;self.quote_button=None;self.subtitle_quote_style=None;self.question_quote_style=None
        main=ttk.Frame(root,padding=15);main.pack(fill='both',expand=True)
        ttk.Label(main,text='시아애비 블로그 자동작성기',font=('맑은 고딕',21,'bold')).pack(anchor='w',pady=(0,3))
        ttk.Label(main,text='원고 작성부터 사진 첨부까지  ·  '+APP_VERSION,
                  foreground='#64748B').pack(anchor='w',pady=(0,8))
        self.status_saved=tk.StringVar(value='좌표 읽는 중')
        ttk.Label(main,textvariable=self.status_saved,foreground='#175b80',
                  wraplength=980,font=('맑은 고딕',10,'bold')).pack(anchor='w',pady=(0,10))
        for title,var in [('사진 폴더',self.folder),('상호명',self.shop),('대표 메뉴',self.menu)]:
            row=ttk.Frame(main);row.pack(fill='x',pady=4)
            ttk.Label(row,text=title,width=12).pack(side='left')
            ttk.Entry(row,textvariable=var).pack(side='left',fill='x',expand=True)
            if title=='사진 폴더':ttk.Button(row,text='찾아보기',command=self.choose).pack(side='left',padx=4)
        self.notes=tk.Text(main,height=1)
        advanced=ttk.LabelFrame(main,text='AI 원고 설정')
        self.advanced_open=tk.BooleanVar(value=False)
        def toggle_advanced():
            if self.advanced_open.get():advanced.pack(fill='x',after=advanced_toggle)
            else:advanced.pack_forget()
        advanced_toggle=ttk.Checkbutton(main,text='AI 원고 설정 펼치기',variable=self.advanced_open,command=toggle_advanced)
        advanced_toggle.pack(anchor='w')
        ttk.Label(advanced,text='꼭 넣고 싶은 문장 (한 줄에 한 문장 · 원문 그대로 반영)',padding=(0,8,0,2)).pack(anchor='w')
        self.must_include=tk.Text(advanced,height=2);self.must_include.pack(fill='x')
        ttk.Label(advanced,text='강조할 이야기·키워드 (쉼표로 구분 · 예: 가족 외식, 좌석, 재방문)',padding=(0,8,0,2)).pack(anchor='w')
        self.keywords=tk.Text(advanced,height=2);self.keywords.pack(fill='x')
        ttk.Label(advanced,text='시아애비 말투 참고 글 (선택 · 내가 마음에 든 예전 원고 일부를 붙여넣기)',padding=(0,8,0,2)).pack(anchor='w')
        self.style_sample=tk.Text(advanced,height=2);self.style_sample.pack(fill='x')
        self.style_sample.insert('1.0', load_style_sample())
        ttk.Button(advanced,text='말투 예시 저장',command=self.save_style_sample).pack(anchor='e',pady=(2,3))
        ttk.Checkbutton(advanced,text='AI가 사진을 보고 시아애비 스타일 원고 생성 (GPT-4.1 API · 별도 비용)',variable=self.use_ai).pack(anchor='w',pady=(12,4))
        ttk.Label(advanced,text='※ 사진에 맞는 자연스러운 Q&A는 위 AI 옵션을 켜야 생성됩니다. 미사용 시 임시 질문으로 작성됩니다.',foreground='#8a5312').pack(anchor='w')
        row=ttk.Frame(advanced);row.pack(fill='x')
        ttk.Label(row,text='API 키',width=12).pack(side='left')
        ttk.Entry(row,textvariable=self.api,show='*').pack(side='left',fill='x',expand=True)
        ttk.Label(advanced,text='키는 이 프로그램에서 서버에 저장하지 않습니다. API 사용 시 사진이 OpenAI로 전송됩니다.',foreground='#666').pack(anchor='w',pady=5)
        buttons=ttk.Frame(main);buttons.pack(fill='x',pady=12)
        ttk.Button(buttons,text='① 원고 생성',command=self.generate).pack(side='left',padx=3)
        ttk.Button(buttons,text='② 사진 포함 미리보기',command=self.preview).pack(side='left',padx=3)
        ttk.Button(buttons,text='③ 네이버 글쓰기 열기',command=self.open_naver).pack(side='left',padx=3)
        ttk.Button(buttons,text='원고 적용',command=self.apply_pasted_draft).pack(side='left',padx=3)
        self.go=ttk.Button(buttons,text='원고 적용 후 바로 입력 시작 (F7)',style='Accent.TButton',command=self.begin);self.go.pack(side='left',padx=3)
        self.pause_button=ttk.Button(buttons,text='일시정지',command=self.toggle_pause,state='disabled');self.pause_button.pack(side='left',padx=3)
        self.stop_button=ttk.Button(buttons,text='중지 (F9)',command=self.stop_input,state='disabled');self.stop_button.pack(side='left',padx=3)
        saved_positions = load_editor_positions()
        for field in POSITION_FIELDS:
            setattr(self, field, saved_positions.get(field))
        self.body_anchor_verified=saved_positions.get('body_anchor_verified',False)
        self.quote_exit_offset=tk.IntVar(value=saved_positions.get('quote_exit_offset',500))
        self.quote_exit_offset.trace_add('write', self.save_positions_if_valid)
        ttk.Label(main,text='전역 단축키: F7 입력 시작 · F8 일시정지/이어쓰기 · F9 중지',foreground='#175b80').pack(anchor='w')
        positions_panel=ttk.LabelFrame(main,text='네이버 위치 설정')
        self.positions_open=tk.BooleanVar(value=False)
        def toggle_positions():
            if self.positions_open.get():positions_panel.pack(fill='x',after=positions_toggle)
            else:positions_panel.pack_forget()
        positions_toggle=ttk.Checkbutton(main,text='네이버 위치 설정 펼치기',variable=self.positions_open,command=toggle_positions)
        positions_toggle.pack(anchor='w')
        ttk.Button(positions_panel,text='네이버 사진 버튼 위치 지정 (5초)',command=self.capture_photo_button).pack(anchor='w',pady=(0,5))
        ttk.Button(positions_panel,text='본문 첫 줄 다시 지정 (필수 · 5초)',command=lambda:self.capture_point('body_point','제목 아래 흰색 본문 첫 줄 (제목 칸 아님!)')).pack(anchor='w')
        ttk.Button(positions_panel,text='인용구 메뉴 버튼 지정 (5초)',command=lambda:self.capture_point('quote_button','네이버 인용구 메뉴 버튼')).pack(anchor='w')
        ttk.Button(positions_panel,text='부제목용 따옴표 스타일 지정 (5초)',command=lambda:self.capture_point('subtitle_quote_style','펼쳐진 인용구 메뉴의 따옴표 스타일')).pack(anchor='w')
        ttk.Button(positions_panel,text='Q용 라인&따옴표 스타일 지정 (5초)',command=lambda:self.capture_point('question_quote_style','펼쳐진 인용구 메뉴의 네 번째 라인&따옴표 스타일')).pack(anchor='w')
        ttk.Button(positions_panel,text='마지막 Q용 프레임 스타일 지정 (5초)',command=lambda:self.capture_point('final_quote_style','펼쳐진 인용구 메뉴의 프레임 스타일')).pack(anchor='w')
        exit_row=ttk.Frame(positions_panel);exit_row.pack(fill='x',pady=(5,0))
        ttk.Label(exit_row,text='인용구 아래 클릭 거리 (px)').pack(side='left')
        ttk.Spinbox(exit_row,from_=100,to=1500,increment=25,width=7,textvariable=self.quote_exit_offset).pack(side='left',padx=(8,6))
        ttk.Label(exit_row,text='기본 500 · 본문 첫 줄 좌표 기준 · 화면 배율이 바뀌면 재조정',foreground='#5d6870').pack(side='left')

        positions_row=ttk.Frame(positions_panel);positions_row.pack(fill='x',pady=(4,4))
        ttk.Label(positions_row,text='위치 설정은 자동 저장되며 다음 실행과 새 버전에서도 불러옵니다',foreground='#175b80').pack(side='left')
        ttk.Button(positions_row,text='위치 설정 초기화',command=self.reset_positions).pack(side='right')
        self.set_saved_positions_status()

        ttk.Button(main,text='업데이트 확인',style='Accent.TButton',command=self.update_info).pack(anchor='e',pady=(0,4))
        ttk.Label(main,text='모바일 폭 미리보기 (글 왼쪽 / 사진 가운데 / Q → 사진 → A. → 답변)',font=('맑은 고딕',10,'bold')).pack(anchor='w')
        self.view=tk.Text(main,height=24,wrap='word');self.view.pack(fill='both',expand=True,pady=6)
        self.status=tk.StringVar(value='원고를 붙여넣고 미리보기 또는 입력을 누르세요.')
        ttk.Label(main,textvariable=self.status,wraplength=700,foreground='#175b80').pack(anchor='w',pady=7)
        ttk.Label(main,text='주의: Windows 네이버 에디터에서만 테스트하세요. 네이버 상단 초록색 [사진] 버튼 위치를 먼저 지정해야 합니다. 실제 인용구 메뉴 위치를 지정해 클릭합니다. 네이버 UI 변경 시 실패할 수 있습니다.\n본문은 약 850자/분 Unicode 키 입력, 사진/GIF는 네이버 첨부 버튼으로 시도합니다. 사진이 바로 뒤따르지 않는 인용구 뒤에는 기본 500px 아래를 클릭하고, 사진 뒤에는 Enter를 누르지 않습니다. F7은 입력 시작, F8은 일시정지/이어쓰기, F9는 중지입니다. 사진 첨부 중에는 완료 후 적용될 수 있습니다. 임시저장은 수동입니다. 입력 중 키보드/마우스를 건드리지 마세요.',foreground='#9a4d12',wraplength=700).pack(anchor='w')
        threading.Thread(target=self.start_hotkeys,daemon=True).start()
    def set_saved_positions_status(self):
        count = sum(getattr(self, field) is not None for field in POSITION_FIELDS)
        names = [('사진', 'photo_button'), ('본문', 'body_point'), ('인용구', 'quote_button'),
                 ('부제목', 'subtitle_quote_style'), ('질문', 'question_quote_style'),
                 ('마무리', 'final_quote_style')]
        positions='  |  '.join(f'{name}: {getattr(self, field) or "미설정"}' for name,field in names)
        body_flag='본문 재지정 필요' if not self.body_anchor_verified else '본문 확인됨'
        self.status_saved.set(f'저장 좌표 {count}/6 · {body_flag}\n{positions}')

    def save_positions_if_valid(self,*_):
        try:
            offset=int(self.quote_exit_offset.get())
            if not 100 <= offset <= 1500:return
            save_editor_positions(self)
        except (ValueError, tk.TclError, OSError):
            pass

    def reset_positions(self):
        if not messagebox.askyesno('위치 초기화','저장된 사진/본문/인용구 버튼 위치를 모두 초기화할까요?'):return
        for field in POSITION_FIELDS:setattr(self,field,None)
        self.body_anchor_verified=False
        self.quote_exit_offset.set(500)
        self.save_positions_if_valid()
        self.set_saved_positions_status()
        self.setstatus('위치 설정 초기화 완료 — 다음 입력 전 다시 위치를 지정해 주세요')

    def capture_point(self,field,description):
        messagebox.showinfo('위치 지정',f'확인을 누른 후 5초 안에 마우스를 [{description}] 위에 올려두세요\\n클릭하지 마세요\\n인용구 스타일 지정 시에는 먼저 네이버에서 인용구 메뉴를 펼쳐 두세요')
        self.setstatus('5초 뒤 '+description+' 위치를 저장합니다')
        def work():
            import pyautogui
            time.sleep(5)
            pos=pyautogui.position()
            setattr(self,field,(pos.x,pos.y))
            if field == 'body_point': self.body_anchor_verified=True
            self.save_positions_if_valid()
            self.root.after(0,self.set_saved_positions_status)
            self.setstatus(description+f' 위치 저장: {(pos.x,pos.y)}')
        threading.Thread(target=work,daemon=True).start()

    def capture_photo_button(self):
        messagebox.showinfo('사진 버튼 위치 지정','확인을 누른 뒤 5초 안에 네이버 글쓰기 화면의 상단 [사진] 첨부 버튼 위로 마우스를 이동하고 그대로 두세요. 클릭하지 마세요.')
        self.setstatus('5초 뒤 마우스 위치를 사진 첨부 버튼으로 저장합니다.')
        def capture():
            import pyautogui
            time.sleep(5)
            pos=pyautogui.position()
            self.photo_button=(pos.x,pos.y)
            self.save_positions_if_valid()
            self.root.after(0,self.set_saved_positions_status)
            self.setstatus(f'사진 첨부 버튼 위치 저장: {self.photo_button}. 브라우저 창 위치/크기를 바꾸지 마세요.')
        threading.Thread(target=capture,daemon=True).start()
    def update_info(self):
        if self.running:
            messagebox.showwarning('업데이트', '네이버 자동 입력이 끝난 뒤 업데이트해 주세요.')
            return
        self.setstatus('GitHub 최신 버전 확인 중...')
        def work():
            try:
                tag, assets = latest_release()
                if version_parts(tag) <= version_parts(APP_VERSION):
                    self.root.after(0, lambda: messagebox.showinfo('업데이트 확인',
                        f'현재 버전 {APP_VERSION}이 최신입니다.\\nGitHub 최신 배포: {tag}'))
                    self.setstatus('최신 버전 사용 중')
                    return
                def confirm():
                    if not messagebox.askyesno('업데이트 확인',
                            f'현재 {APP_VERSION} → 최신 {tag}\n\n다운로드하고 프로그램을 재시작할까요?\n저장된 좌표는 유지됩니다.'):
                        self.setstatus('업데이트 취소')
                        return
                    self.setstatus('업데이트 다운로드 및 검증 중...')
                    threading.Thread(target=download_and_start, args=(assets,), daemon=True).start()
                self.root.after(0, confirm)
            except urllib.error.HTTPError as e:
                msg = ('아직 GitHub Releases에 배포된 버전이 없습니다.\n'
                       '저장소의 Releases에서 첫 배포를 등록해야 합니다.') if e.code == 404 else str(e)
                self.root.after(0, lambda m=msg: messagebox.showerror('업데이트 확인 실패', m))
                self.setstatus('업데이트 확인 실패')
            except Exception as e:
                msg = str(e)
                self.root.after(0, lambda m=msg: messagebox.showerror('업데이트 확인 실패', m))
                self.setstatus('업데이트 확인 실패')
        def download_and_start(assets):
            try:
                archive = prepare_update(assets)
                if not getattr(sys, 'frozen', False):
                    raise RuntimeError('이 버전의 업데이트는 EXE로 실행할 때 지원됩니다.')
                # Copy the updater OUTSIDE the folder it needs to replace,
                # so Windows can release/rename the entire app folder.
                updater_source = ROOT / 'SiaAebiUpdater.exe'
                if not updater_source.is_file():
                    updater_source = ROOT.parent / 'SiaAebiUpdater.exe'  # legacy installations
                if not updater_source.is_file():
                    raise FileNotFoundError('업데이트 실행 파일이 없습니다. GitHub 설치 패키지의 SiaAebiUpdater.exe가 필요합니다.')
                updater_dir = Path(tempfile.mkdtemp(prefix='siaaebi_updater_'))
                updater = updater_dir / 'SiaAebiUpdater.exe'
                shutil.copy2(updater_source, updater)
                subprocess.Popen([str(updater), '--archive', str(archive),
                                  '--folder', str(ROOT), '--pid', str(os.getpid())],
                                 cwd=str(ROOT.parent), creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                self.root.after(0, self.root.destroy)
            except Exception as e:
                msg=str(e)
                self.root.after(0, lambda m=msg: messagebox.showerror('업데이트 설치 실패', m))
                self.setstatus('업데이트 설치 실패 — 기존 버전 유지')
        threading.Thread(target=work, daemon=True).start()
    def save_style_sample(self):
        try:
            save_style_sample(self.style_sample.get('1.0','end').strip())
            self.setstatus('시아애비 말투 예시 저장 완료 (내 PC에만 저장)')
        except Exception as e:
            messagebox.showerror('말투 저장 오류',str(e))
    def choose(self):
        p=filedialog.askdirectory(initialdir=self.folder.get());
        if p:self.folder.set(p)
    def setstatus(self,s):self.root.after(0,lambda:self.status.set(s))
    def generate(self):
        try:
            photos=sorted_photos(self.folder.get())
            if not photos:raise ValueError('선택한 폴더에 사진이 없습니다.')
            if self.use_ai.get() and not self.api.get().strip():raise ValueError('API 키를 입력하세요.')
            self.setstatus('원고 작성 중...')
            args=(self.shop.get(),self.menu.get(),self.notes.get('1.0','end').strip(),photos,self.must_include.get('1.0','end').strip(),self.keywords.get('1.0','end').strip())
            style_sample=self.style_sample.get('1.0','end').strip()
            ai=self.use_ai.get();key=self.api.get().strip()
            def work():
                try:
                    data=clean_data(ai_draft(key,*args,style_sample=style_sample) if ai else default_draft(*args))
                    out=save_preview(data)
                    def done():
                        self.data=data;self.view.delete('1.0','end');self.view.insert('end',data['title']+'\n')
                        for b in data['blocks']:
                            if b['type']=='hero_quote':
                                rendered='[부제목] '+b['value']
                            elif b['type']=='final_quote':
                                rendered='[마무리]\n'+b['value']
                            elif b['type']=='image':
                                rendered='[사진] '+Path(b['path']).name
                            else:
                                rendered=b['value']
                            self.view.insert('end',rendered+'\n')
                        self.status.set('원고 생성 완료. 미리보기 파일: '+str(out))
                    self.root.after(0,done)
                except Exception as e:self.setstatus('오류: '+str(e))
            threading.Thread(target=work,daemon=True).start()
        except Exception as e:messagebox.showerror('확인',str(e))
    def current_draft(self):
        raw=self.view.get('1.0','end').strip()
        if not raw:raise ValueError('원고를 붙여넣어 주세요.')
        explicit_subtitle=bool(re.search(r'(?m)^\s*(?:\[부제목\]|부제목\s*[:：]|#{2,4}\s+|>\s*\S)',raw))
        if not explicit_subtitle and not self.shop.get().strip():
            raise ValueError('부제목 인용구에 넣을 상호명이 없습니다. 상호명을 입력하거나 원고 둘째 줄에 [부제목] 양촌리 돼지갈비 맛집 형식으로 추가하세요.')
        fallback=make_subtitle(self.shop.get(),self.menu.get(),self.keywords.get('1.0','end').strip()) if not explicit_subtitle else None
        return parse_pasted_draft(raw,sorted_photos(self.folder.get()),default_subtitle=fallback)
    def apply_pasted_draft(self):
        try:
            self.data=self.current_draft()
            self.setstatus('원고 적용 완료 · 이제 [입력 시작 (F7)]만 누르면 됩니다 (네이버 입력 시작 단계 불필요)')
        except Exception as e:
            messagebox.showerror('원고 확인',str(e))
    def preview(self):
        try:
            self.data=self.current_draft()
            webbrowser.open(save_preview(self.data).as_uri())
        except Exception as e:messagebox.showerror('미리보기 실패',str(e))
    def open_naver(self):
        webbrowser.open('https://blog.naver.com/')
        self.setstatus('네이버 글쓰기 화면을 열고 제목 칸을 클릭하세요. 이후 [입력 시작 (F7)]을 누르면 됩니다')

    def naver(self):
        try:self.data=self.current_draft()
        except Exception as e:return messagebox.showerror('원고 확인',str(e))
        if not all(getattr(self, field) for field in POSITION_FIELDS):
            return messagebox.showwarning('확인','사진/본문/인용구 위치가 일부 비어 있습니다. 빠진 위치만 지정하세요')
        if not self.body_anchor_verified:
            return messagebox.showwarning('본문 위치 재설정 필요',
                '제목에 부제목이 붙는 문제를 방지하려면 [네이버 위치 설정 펼치기] → '
                '[본문 첫 줄 다시 지정 (필수 · 5초)]을 눌러 제목 아래 실제 본문 칸에 마우스를 올려 저장해 주세요.')
        if self.body_point[1] <= self.quote_button[1]+90:
            return messagebox.showwarning('본문 위치 확인',
                '저장된 본문 좌표가 도구막대 또는 제목 칸일 수 있습니다. '
                '네이버 글쓰기 화면의 제목 아래 본문 첫 줄을 다시 지정하세요.')
        if not messagebox.askyesno('중요','이미 열어둔 네이버 글쓰기 창을 사용하며 새 네이버 창은 열리지 않습니다.\n확인을 누른 뒤 기존 글쓰기 화면의 제목 칸을 클릭하세요.\n네이버 상단 초록색 [사진] 버튼 위치를 미리 지정하세요. 파일 선택 창이 열리지 않으면 안전하게 중지합니다.\n입력 중 마우스/키보드를 사용하지 마세요.\n임시저장은 직접 눌러야 합니다. 계속할까요?'):return
        self.event.clear();self.pause_event.set();self.stop_event.clear();self.running=True;self.cancel=False;self.go.config(state='normal');self.pause_button.config(state='normal',text='일시정지');self.stop_button.config(state='normal')
        threading.Thread(target=self.worker,daemon=True).start()
    def begin(self):
        if not self.running:
            self.naver()
            if not self.running:return
        if self.event.is_set():return
        self.go.config(state='disabled');self.event.set()
    def toggle_pause(self):
        if not self.running:return
        if self.pause_event.is_set():
            self.pause_event.clear()
            self.pause_button.config(text='이어쓰기')
            self.setstatus('일시정지됨 — 이어쓰기를 누르면 중단한 글자부터 계속 입력합니다')
        else:
            self.pause_event.set()
            self.pause_button.config(text='일시정지')
            self.setstatus('입력 재개')
    def stop_input(self):
        if not self.running:return
        self.stop_event.set()
        self.pause_event.set()
        self.setstatus('중지 요청됨 — 사진 첨부 작업 중이면 완료 후 멈춥니다')

    def start_hotkeys(self):
        """Windows 전역 F7/F8/F9. 등록 실패 시 버튼으로 조작."""
        import ctypes
        from ctypes import wintypes
        user32=ctypes.windll.user32
        registered=[]
        try:
            for hotkey_id,vk in ((800,0x76),(801,0x77),(802,0x78)):
                if user32.RegisterHotKey(None,hotkey_id,0x4000,vk):
                    registered.append(hotkey_id)
                else:
                    self.setstatus(f'F{7 if hotkey_id==800 else (8 if hotkey_id==801 else 9)} 등록 실패 — 다른 앱에서 사용 중일 수 있습니다')
            msg=wintypes.MSG()
            while True:
                if user32.PeekMessageW(ctypes.byref(msg),None,0,0,1) and msg.message==0x0312:
                    if msg.wParam==800:self.root.after(0,self.begin)
                    elif msg.wParam==801 and self.running:self.root.after(0,self.toggle_pause)
                    elif msg.wParam==802 and self.running:self.root.after(0,self.stop_input)
                time.sleep(.035)
        finally:
            for hotkey_id in registered:user32.UnregisterHotKey(None,hotkey_id)

    def worker(self):
        def wait():return self.event.wait(300)
        try:automate_naver(self.data,self.setstatus,wait,self.photo_button,self.body_point,self.quote_button,self.subtitle_quote_style,self.question_quote_style,self.final_quote_style,self.quote_exit_offset.get(),self.pause_event,self.stop_event)
        except InputCancelled as e:self.setstatus(str(e))
        except Exception as e:self.setstatus('자동 입력 실패: '+str(e)+' / 미리보기에서 수동 복사해 주세요.')
        finally:
            self.running=False;self.pause_event.set()
            self.root.after(0,lambda:(self.go.config(state='normal'),self.pause_button.config(state='disabled',text='일시정지'),self.stop_button.config(state='disabled')))

if __name__=='__main__':
    root=tk.Tk();apply_app_icon(root);App(root);root.mainloop()