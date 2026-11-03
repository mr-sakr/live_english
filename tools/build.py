"""Builds the whole site from the content/ folder.

    python tools/build.py              images + audio + pages
    python tools/build.py --pages      pages only (no network)

Media that already exists is never downloaded again, so re-running is cheap.
Audio needs the edge-tts package (see tools/requirements.txt). The finished
site needs nothing: open index.html directly from the folder.
"""
import asyncio
import json
import os
import posixpath
import re
import sys
import urllib.request
import zlib
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import svg_images
from mp3_frames import FRAME_SECONDS, TICKS_PER_SECOND, silence, speak_frames

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"
TOPICS_OUT = ROOT / "topics"
WORD_GOAL = 6000
TWEMOJI = "https://cdn.jsdelivr.net/npm/@twemoji/svg@15.0.0/{}.svg"
EMOJI_CACHE = Path(__file__).resolve().parent / "emoji-cache"
VOICES = {"us": "en-US-AriaNeural", "uk": "en-GB-SoniaNeural",
          "sentences": "en-US-AriaNeural", "paragraphs": "en-US-AriaNeural",
          "a": "en-US-JennyNeural", "b": "en-US-GuyNeural"}
MP3_BYTES_PER_SECOND = 6000
CONVERSATION_LINE_PAUSE = 0.5
POS = {"n": "اسم", "v": "فعل", "adj": "صفة", "adv": "ظرف", "prep": "حرف جر", "conj": "أداة ربط", "phr": "عبارة"}
PLANNED = ["الجسم", "الصحة", "البنوك والمال", "العمل", "السفر", "الطعام", "البيت", "العائلة"]


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def hashed_slug(text):
    return f"{slug(text)[:40].strip('-')}-{zlib.crc32(text.encode()):08x}"


# ---------- Reading the content files ----------

def rows(path):
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def split_row(line, count, path):
    parts = [part.strip() for part in line.split("|")]
    if len(parts) != count:
        raise ValueError(f"{path}: expected {count} columns, found {len(parts)}: {line}")
    return parts


def read_words(path):
    keys = ("text", "ipa", "pos", "ar", "img", "ex", "ex_ar")
    return [dict(zip(keys, split_row(line, 7, path))) for line in rows(path)]


def read_expressions(path):
    keys = ("text", "ar", "img", "ex", "ex_ar")
    return [dict(zip(keys, split_row(line, 5, path))) for line in rows(path)]


def read_sentences(path):
    groups = []
    for line in rows(path):
        if line.startswith("## "):
            groups.append({"title": line[3:], "items": []})
        else:
            en, ar = split_row(line, 2, path)
            groups[-1]["items"].append({"en": en, "ar": ar})
    return groups


def read_dialogues(path):
    dialogues = []
    for line in rows(path):
        if line.startswith("## "):
            en, ar = split_row(line[3:], 2, path)
            dialogues.append({"en": en, "ar": ar, "lines": []})
        else:
            who, en, ar = split_row(line, 3, path)
            dialogues[-1]["lines"].append({"who": who.lower(), "en": en, "ar": ar})
    return dialogues


def read_story(path):
    """A page's own conversation and paragraph, which must use all its words."""
    story = {"lines": [], "paragraph": None}
    part = None
    for line in rows(path):
        if line.startswith("## "):
            part = line[3:]
        elif part == "conversation":
            who, en, ar = split_row(line, 3, path)
            story["lines"].append({"who": who.lower(), "en": en, "ar": ar})
        else:
            en, ar = split_row(line, 2, path)
            story["paragraph"] = {"en": en, "ar": ar}
    return story


def term_regex(text):
    """Matches an entry as a whole word; names like Monday or May keep their capital."""
    core = text.rstrip(".?!")
    keep_case = core == text and core != core.lower()
    body = re.escape(core)
    return rf"(?<![\w-])({body})(?![\w-])" if keep_case else rf"(?<![\w-])((?i:{body}))(?![\w-])"


def check_story(section):
    """Returns the page's words that its conversation or paragraph leaves out."""
    story = section["story"]
    conversation = " ".join(line["en"] for line in story["lines"])
    missing = []
    for item in section["data"]:
        if not re.search(term_regex(item["text"]), conversation):
            missing.append(f"conversation: {item['text']}")
        if not re.search(term_regex(item["text"]), story["paragraph"]["en"]):
            missing.append(f"paragraph: {item['text']}")
    return missing


READERS = {"words": read_words, "expressions": read_expressions,
           "sentences": read_sentences, "dialogues": read_dialogues}


def load_topic(folder):
    topic = json.loads((folder / "topic.json").read_text(encoding="utf-8"))
    problems = []
    for group in topic["groups"]:
        for section in group["sections"]:
            source = folder / group["id"] / f"{section['id']}.txt"
            section["data"] = READERS[section["type"]](source)
            section["path"] = f"{group['id']}/{section['id']}"
            if section["type"] in ("words", "expressions"):
                section["story"] = read_story(folder / group["id"] / f"{section['id']}.story.txt")
                problems.extend(f"{section['id']} {line}" for line in check_story(section))
    if problems:
        print("Words missing from page stories:")
        print("\n".join(f"  {line}" for line in problems))
        sys.exit(1)
    check_pictures_unique(topic)
    return topic


def check_pictures_unique(topic):
    """Every entry needs its own picture, so two words can never be confused."""
    owners = {}
    for section in all_sections(topic):
        if section["type"] in ("words", "expressions"):
            for item in section["data"]:
                owners.setdefault(item["img"], []).append(f"{section['id']}: {item['text']}")
    repeats = {spec: names for spec, names in owners.items() if len(names) > 1}
    if repeats:
        sys.stdout.reconfigure(encoding="utf-8")
        print("Pictures used more than once:")
        for spec, names in repeats.items():
            print(f"  {spec} -> {', '.join(names)}")
        sys.exit(1)


def all_sections(topic):
    return [section for group in topic["groups"] for section in group["sections"]]


# ---------- Images ----------

def is_drawn(spec):
    return spec.split(":")[0] in svg_images.DRAWN_KINDS


def image_name(spec):
    if is_drawn(spec):
        return f"{hashed_slug(spec).strip('-')}.svg"
    return f"e-{emoji_code(spec)}.svg"


def load_emoji(char):
    """Returns a Twemoji SVG, downloading it into tools/emoji-cache the first time."""
    cached = EMOJI_CACHE / f"{emoji_code(char)}.svg"
    if not cached.exists():
        EMOJI_CACHE.mkdir(exist_ok=True)
        with urllib.request.urlopen(TWEMOJI.format(emoji_code(char)), timeout=30) as response:
            cached.write_bytes(response.read())
    return cached.read_text(encoding="utf-8")


def emoji_code(char):
    points = [f"{ord(c):x}" for c in char]
    if "200d" not in points:
        points = [p for p in points if p != "fe0f"]
    return "-".join(points)


def section_images(section):
    if section["type"] in ("words", "expressions"):
        return [item["img"] for item in section["data"]]
    return []


def build_images(topic):
    folder = TOPICS_OUT / topic["id"] / "media" / "images"
    folder.mkdir(parents=True, exist_ok=True)
    specs = {topic["emoji"]}
    for section in all_sections(topic):
        specs.update(section_images(section))
    failed = []
    for spec in sorted(specs):
        target = folder / image_name(spec)
        try:
            svg = svg_images.draw(spec, load_emoji) if is_drawn(spec) else load_emoji(spec)
            target.write_text(svg, encoding="utf-8")
        except Exception as error:
            failed.append(f"{spec}: {error}")
    needed = {image_name(spec) for spec in specs}
    for leftover in folder.glob("*.svg"):
        if leftover.name not in needed:
            leftover.unlink()
    print(f"images: {len(specs)} in use, {len(failed)} failed")
    for line in failed:
        print("  FAILED", line)
    return not failed


# ---------- Audio ----------

def audio_rel(kind, text):
    if kind in ("us", "uk"):
        return f"media/audio/{kind}/{slug(text)}.mp3"
    return f"media/audio/{kind}/{hashed_slug(text)}.mp3"


def conversation_rel(lines):
    joined = "\n".join(f"{line['who']}:{line['en']}" for line in lines)
    return f"media/audio/conversations/{hashed_slug(joined)}.mp3"


def all_conversations(topic):
    conversations = []
    for section in all_sections(topic):
        if section["type"] in ("words", "expressions"):
            conversations.append(section["story"]["lines"])
        elif section["type"] == "dialogues":
            conversations.extend(dialogue["lines"] for dialogue in section["data"])
    return conversations


def audio_jobs(topic):
    jobs = {}

    def add(kind, text):
        jobs[audio_rel(kind, text)] = (VOICES[kind], text)

    for section in all_sections(topic):
        if section["type"] in ("words", "expressions"):
            for item in section["data"]:
                add("us", item["text"])
                add("uk", item["text"])
                add("sentences", item["ex"])
            add("paragraphs", section["story"]["paragraph"]["en"])
        elif section["type"] == "sentences":
            for group in section["data"]:
                for item in group["items"]:
                    add("sentences", item["en"])
    return jobs


async def save_with_timings(text, voice, audio_path, timings_path):
    """Saves the audio plus when each word starts, which drives the live highlight."""
    import edge_tts

    words = []
    with open(audio_path, "wb") as audio:
        async for chunk in edge_tts.Communicate(text, voice, boundary="WordBoundary").stream():
            if chunk["type"] == "audio":
                audio.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                words.append({"text": chunk["text"], "start": round(chunk["offset"] / TICKS_PER_SECOND, 3),
                              "end": round((chunk["offset"] + chunk["duration"]) / TICKS_PER_SECOND, 3)})
    timings_path.write_text(json.dumps(words, ensure_ascii=False), encoding="utf-8")


async def speak(limit, voice, text, target):
    import edge_tts

    async with limit:
        for attempt in range(4):
            try:
                partial = target.with_suffix(".part")
                if target.parent.name == "paragraphs":
                    await save_with_timings(text, voice, partial, target.with_suffix(".json"))
                else:
                    await edge_tts.Communicate(text, voice).save(str(partial))
                partial.replace(target)
                return None
            except Exception as error:
                await asyncio.sleep(1 + attempt * 2)
                last_error = error
        return f"{text}: {last_error}"


async def save_conversation(limit, lines, target):
    """Joins a conversation's lines into one file, with when each word starts."""
    async with limit:
        try:
            frames, timeline = [], []
            for line in lines:
                line_frames, words = await speak_frames(line["en"], VOICES[line["who"]])
                offset = len(frames) * FRAME_SECONDS
                timeline.append([{"text": word["text"], "start": round(word["start"] + offset, 3),
                                  "end": round(word["end"] + offset, 3)} for word in words])
                frames += line_frames + silence(CONVERSATION_LINE_PAUSE)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"".join(frames))
            target.with_suffix(".json").write_text(json.dumps(timeline, ensure_ascii=False), encoding="utf-8")
            return None
        except Exception as error:
            return f"{lines[0]['en']}: {error}"


async def build_audio(topic):
    base = TOPICS_OUT / topic["id"]
    limit = asyncio.Semaphore(6)
    tasks = []
    jobs = audio_jobs(topic)
    for rel, (voice, text) in jobs.items():
        target = base / rel
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            tasks.append(speak(limit, voice, text, target))
    conversations = all_conversations(topic)
    for lines in conversations:
        target = base / conversation_rel(lines)
        if not target.exists():
            tasks.append(save_conversation(limit, lines, target))
    results = await asyncio.gather(*tasks)
    failed = [result for result in results if result]
    print(f"audio: {len(jobs) + len(conversations)} files, {len(tasks) - len(failed)} new, {len(failed)} failed")
    for line in failed:
        print("  FAILED", line)
    return not failed


# ---------- Pages ----------

def rel(page_dir, target):
    return posixpath.relpath(target, page_dir or ".")


def ltr(text, tag="span", cls=""):
    attr = f" class='{cls}'" if cls else ""
    return f"<{tag} lang='en' dir='ltr'{attr}>{escape(text)}</{tag}>"


def marked(text, terms):
    """Escapes text and highlights every occurrence of the page's words, longest first."""
    pattern = "|".join(term_regex(term) for term in sorted(terms, key=len, reverse=True))
    html, position = "", 0
    for match in re.finditer(pattern, text):
        html += escape(text[position:match.start()]) + f"<mark>{escape(match.group())}</mark>"
        position = match.end()
    return html + escape(text[position:])


def locate_words(text, timings):
    """Finds each spoken word in the text, in order: (start, end, seconds)."""
    spans, cursor = [], 0
    for word in timings:
        start = text.find(word["text"], cursor)
        if start < 0:
            raise ValueError(f"Spoken word not found in paragraph: {word['text']}")
        cursor = start + len(word["text"])
        spans.append((start, cursor, word["start"]))
    return spans


def timed_paragraph(text, timings, terms):
    """The paragraph with one clickable span per spoken word, inside the page-word highlights."""
    spans = locate_words(text, timings)
    pattern = "|".join(term_regex(term) for term in sorted(terms, key=len, reverse=True))
    ranges = []
    for match in re.finditer(pattern, text) if terms else ():
        start, end = match.span()
        # A highlight always contains whole spoken words, so the tags can never cross.
        for word_start, word_end, _ in spans:
            if word_start < end and start < word_end:
                start, end = min(start, word_start), max(end, word_end)
        if ranges and start < ranges[-1][1]:
            ranges[-1] = (ranges[-1][0], max(end, ranges[-1][1]))
        else:
            ranges.append((start, end))

    def render(first, last):
        html, position = "", first
        for word_start, word_end, seconds in spans:
            if first <= word_start and word_end <= last:
                html += escape(text[position:word_start])
                html += f"<span class='pw' data-t='{seconds}'>{escape(text[word_start:word_end])}</span>"
                position = word_end
        return html + escape(text[position:last])

    html, position = "", 0
    for start, end in ranges:
        html += render(position, start) + f"<mark>{render(start, end)}</mark>"
        position = end
    return html + render(position, len(text))


def speaker(src, label, size="", text=""):
    cls = f"spk {size}".strip()
    return f"<button type='button' class='{cls}' data-src='{escape(src)}' aria-label='{escape(label)}' title='{escape(label)}'>{text}</button>"


def page(page_dir, title, crumbs, body, scripts=()):
    css = rel(page_dir, "assets/css/main.css")
    js = rel(page_dir, "assets/js/app.js")
    extra_scripts = "".join(f'<script src="{rel(page_dir, f"assets/js/{name}")}"></script>\n' for name in scripts)
    home = rel(page_dir, "index.html")
    trail = f"<a href='{home}'>الرئيسية</a>"
    for label, href in crumbs:
        trail += " <span aria-hidden='true'>‹</span> "
        trail += f"<a href='{href}'>{escape(label)}</a>" if href else f"<span>{escape(label)}</span>"
    return f"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<link rel="stylesheet" href="{css}">
</head>
<body>
<header class="top"><a class="brand" href="{home}">Live English</a><nav class="crumbs" aria-label="مسار الصفحة">{trail}</nav></header>
<main class="wrap">
{body}
</main>
<div class="toast" role="status" hidden></div>
<script src="{js}"></script>
{extra_scripts}</body>
</html>
"""


def word_card(item, media):
    us = speaker(f"{media}/{audio_rel('us', item['text'])}", f"انطق: {item['text']} (أمريكي)", "big")
    uk = speaker(f"{media}/{audio_rel('uk', item['text'])}", f"انطق: {item['text']} (بريطاني)", "small", "UK")
    ex = speaker(f"{media}/{audio_rel('sentences', item['ex'])}", "استمع إلى الجملة", "small")
    ipa = ltr(item["ipa"], cls="ipa") if item.get("ipa") else ""
    pos = f"<span class='pos'>{POS[item['pos']]}</span>" if item.get("pos") else ""
    return f"""<article class="card">
<img src="{media}/media/images/{image_name(item['img'])}" alt="" width="104" height="104" loading="lazy">
<div class="card-body">
<div class="head">{us}{ltr(item['text'], 'h2')}{uk}</div>
<div class="meta">{ipa}{pos}</div>
<p class="meaning">{escape(item['ar'])}</p>
<div class="example">{ex}<div>{ltr(item['ex'], 'p')}<p class="tr">{escape(item['ex_ar'])}</p></div></div>
</div>
</article>"""


def sentence_row(item, media):
    button = speaker(f"{media}/{audio_rel('sentences', item['en'])}", "استمع إلى الجملة")
    return f"<li class='line'>{button}<div>{ltr(item['en'], 'p', 'en')}<p class='tr'>{escape(item['ar'])}</p></div></li>"


def dialogue_block(dialogue, media, topic_dir, terms=()):
    audio = conversation_rel(dialogue["lines"])
    timeline = json.loads((ROOT / topic_dir / audio).with_suffix(".json").read_text(encoding="utf-8"))
    lines = ""
    for line, timings in zip(dialogue["lines"], timeline):
        english = timed_paragraph(line["en"], timings, terms)
        lines += f"<li class='bubble {line['who']}'><div><p lang='en' dir='ltr' class='en'>{english}</p><p class='tr'>{escape(line['ar'])}</p></div></li>"
    return f"""<section class="block dialogue timed">
<div class="block-head"><h2>{ltr(dialogue['en'])} <small>{escape(dialogue['ar'])}</small></h2></div>
{player_bar(f"{media}/{audio}", timeline[-1][-1]["end"])}
<ol class="bubbles timed-text">{lines}</ol>
</section>"""


def clock_text(seconds):
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


def player_bar(audio_src, duration, playlist=False):
    speeds = "".join(
        f"<button type='button' data-speed='{speed}' aria-pressed='{'true' if speed == '1' else 'false'}'>{speed}x</button>"
        for speed in ("0.5", "1", "1.5", "2"))
    source = "" if playlist else f' src="{escape(audio_src)}"'
    previous_button = next_button = ""
    repeat_button = '<button type="button" class="p-loop" aria-pressed="false" aria-label="تكرار دائم" title="تكرار دائم"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M17 2l4 4-4 4V7H7v4H5V5h12zM7 22l-4-4 4-4v3h10v-4h2v6H7z"/></svg></button>'
    if playlist:
        previous_button = '<button type="button" class="p-previous" aria-label="الملف السابق" title="الملف السابق"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 5h2v14H6zM20 5v14L9 12z"/></svg></button>'
        next_button = '<button type="button" class="p-next" aria-label="الملف التالي" title="الملف التالي"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M16 5h2v14h-2zM4 5v14l11-7z"/></svg></button>'
        repeat_button = ('<button type="button" class="p-shuffle" aria-pressed="false" aria-label="تشغيل عشوائي" title="تشغيل عشوائي"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M17 4l4 3.5-4 3.5V9h-2.2L7.5 18H3v-2h3.5l7.3-9H17zM3 6h4.5l2.6 3.2-1.3 1.6L6.5 8H3zm11.1 8.8l.7.9H17v-2l4 3.5-4 3.5v-2h-3.2l-1-1.3z"/></svg></button>'
                         '<button type="button" class="p-repeat" data-mode="off" aria-label="التكرار: بدون" title="التكرار: بدون"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M17 2l4 4-4 4V7H7v4H5V5h12zM7 22l-4-4 4-4v3h10v-4h2v6H7z"/></svg><span class="p-repeat-one">1</span></button>')
    return f"""<div class="player" dir="ltr">
<audio{source} preload="none"></audio>
<div class="player-buttons">
{previous_button}<button type="button" class="p-back" aria-label="رجوع 5 ثوان" title="رجوع 5 ثوان">« 5</button>
<button type="button" class="p-play" aria-label="تشغيل أو إيقاف مؤقت" title="تشغيل / إيقاف مؤقت"><svg class="i-play" viewBox="0 0 24 24" aria-hidden="true"><path d="M7 4v16l13-8z"/></svg><svg class="i-pause" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 4h4v16H6zM14 4h4v16h-4z"/></svg></button>
<button type="button" class="p-forward" aria-label="تقديم 5 ثوان" title="تقديم 5 ثوان">5 »</button>
{next_button}<button type="button" class="p-stop" aria-label="إيقاف" title="إيقاف"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6h12v12H6z"/></svg></button>
{repeat_button}
</div>
<div class="player-seek"><span class="p-time">0:00</span><input class="p-seek" type="range" min="0" max="{duration}" step="0.05" value="0" aria-label="موضع الصوت"><span class="p-total">{clock_text(duration)}</span></div>
<div class="player-speeds" role="group" aria-label="سرعة الصوت">{speeds}</div>
</div>"""


def story_panels(section, media, topic_dir):
    terms = [item["text"] for item in section["data"]]
    story = section["story"]
    conversation = dialogue_block({"en": section["en"], "ar": "محادثة بكل كلمات الصفحة", "lines": story["lines"]}, media, topic_dir, terms)
    paragraph = story["paragraph"]
    audio = audio_rel("paragraphs", paragraph["en"])
    timings = json.loads((ROOT / topic_dir / audio).with_suffix(".json").read_text(encoding="utf-8"))
    bar = player_bar(f"{media}/{audio}", timings[-1]["end"])
    note = "<p class='hint'>الكلمات المميزة هي كلمات هذه الصفحة. اضغط على أي كلمة ليبدأ الصوت منها ويكمل ما بعدها.</p>"
    return f"""<section class="panel" data-panel="quiz" hidden><div class="quiz"><p class="quiz-intro">ستسمع كلمة من كلمات الصفحة، فاضغط على الصورة التي تعبر عنها.</p><button type="button" class="quiz-go">ابدأ الاختبار</button></div></section>
<section class="panel" data-panel="conversation" hidden>{note}{conversation}</section>
<section class="panel" data-panel="paragraph" hidden>{note}<article class="paragraph timed">{bar}<p class="paragraph-en timed-text" lang="en" dir="ltr">{timed_paragraph(paragraph['en'], timings, terms)}</p><p class="tr">{escape(paragraph['ar'])}</p></article></section>"""


TABS = (("words", "الكلمات"), ("quiz", "الاختبار"), ("conversation", "المحادثة"), ("paragraph", "الفقرة"))


def tab_bar():
    buttons = "".join(f"<button type='button' role='tab' data-tab='{name}'>{label}</button>" for name, label in TABS)
    return f"<div class='tabs' role='tablist'>{buttons}</div>"


def section_body(section, media, topic_dir):
    kind, data = section["type"], section["data"]
    if kind in ("words", "expressions"):
        return "<div class='cards'>" + "".join(word_card(item, media) for item in data) + "</div>"
    if kind == "sentences":
        html = ""
        for group in data:
            rows_html = "".join(sentence_row(item, media) for item in group["items"])
            html += f"<section class='block'><h2>{escape(group['title'])}</h2><ul class='lines'>{rows_html}</ul></section>"
        return html
    return "".join(dialogue_block(dialogue, media, topic_dir) for dialogue in data)


def item_count(section):
    if section["type"] in ("words", "expressions"):
        return len(section["data"])
    if section["type"] == "sentences":
        return sum(len(group["items"]) for group in section["data"])
    return len(section["data"])


COUNT_LABEL = {"words": "كلمة", "expressions": "تعبير", "sentences": "جملة", "dialogues": "محادثات"}


def section_thumb(section):
    images = section_images(section)
    return images[0] if images else "💬"


def write_page(page_dir, html):
    target = ROOT / page_dir / "index.html" if page_dir else ROOT / "index.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(html, encoding="utf-8")


def build_section_pages(topic):
    sections = all_sections(topic)
    topic_dir = f"topics/{topic['id']}"
    for index, section in enumerate(sections):
        page_dir = f"{topic_dir}/{section['path']}"
        media = rel(page_dir, topic_dir)
        pager = ""
        if index > 0:
            prev = sections[index - 1]
            pager += f"<a class='prev' href='{rel(page_dir, f'{topic_dir}/{prev['path']}/index.html')}'>→ {escape(prev['ar'])}</a>"
        if index < len(sections) - 1:
            nxt = sections[index + 1]
            pager += f"<a class='next' href='{rel(page_dir, f'{topic_dir}/{nxt['path']}/index.html')}'>{escape(nxt['ar'])} ←</a>"
        title_html = f"""<div class="page-title"><h1>{escape(section['ar'])}</h1>{ltr(section['en'], 'p', 'sub')}</div>"""
        has_story = section["type"] in ("words", "expressions")
        if has_story:
            main = f"""{tab_bar()}
<section class="panel" data-panel="words">
<p class="hint">مرّر الماوس على السماعة أو اضغط عليها لتسمع النطق. السماعة الكبيرة نطق أمريكي (وهو المكتوب بالرموز)، وزر UK نطق بريطاني.</p>
{section_body(section, media, topic_dir)}
</section>
{story_panels(section, media, topic_dir)}"""
        elif section["type"] == "dialogues":
            main = f"""<p class="hint">اضغط على أي كلمة ليبدأ الصوت منها ويكمل ما بعدها.</p>
{section_body(section, media, topic_dir)}"""
        else:
            main = f"""<p class="hint">مرّر الماوس على السماعة أو اضغط عليها لتسمع النطق.</p>
{section_body(section, media, topic_dir)}"""
        body = f"""{title_html}
{main}
<nav class="pager" aria-label="التنقل بين الأقسام">{pager}</nav>"""
        crumbs = [(topic["ar"], rel(page_dir, f"{topic_dir}/index.html")), (section["ar"], None)]
        write_page(page_dir, page(page_dir, f"{section['en']} - {topic['en']}", crumbs, body,
                                  ("quiz.js", "player.js") if has_story else ("player.js",) if section["type"] == "dialogues" else ()))


def build_topic_page(topic, stats):
    page_dir = f"topics/{topic['id']}"
    body = f"""<div class="page-title"><h1>{escape(topic['ar'])}</h1>{ltr(topic['en'], 'p', 'sub')}</div>
<p class="stats">{stats['words']} كلمة · {stats['phrases']} مصطلح وتعبير · {stats['sentences']} جملة · {stats['dialogues']} محادثات</p>"""
    for group in topic["groups"]:
        cards = ""
        for section in group["sections"]:
            href = f"{section['path']}/index.html"
            image = f"media/images/{image_name(section_thumb(section))}" if section_images(section) else ""
            thumb = f"<img src='{image}' alt='' width='56' height='56' loading='lazy'>" if image else "<span class='thumb-emoji' aria-hidden='true'>💬</span>"
            cards += (f"<a class='tile' href='{href}'>{thumb}<span><strong>{escape(section['ar'])}</strong>"
                      f"{ltr(section['en'], 'em')}<small>{item_count(section)} {COUNT_LABEL[section['type']]}</small></span></a>")
        body += f"<section class='block'><h2>{escape(group['ar'])}</h2><div class='tiles'>{cards}</div></section>"
    body += ("<section class='block'><h2>الاستماع</h2><div class='tiles'><a class='tile' href='audio/index.html'>"
             "<span class='thumb-emoji' aria-hidden='true'>🎧</span><span><strong>الدروس الصوتية</strong>"
             f"{ltr('Audio Lessons', 'em')}<small>للموبايل والمشي والسواقة</small></span></a></div></section>")
    write_page(page_dir, page(page_dir, topic["en"], [(topic["ar"], None)], body))


LESSON_TYPES = (("1-recall.mp3", "افتكر الكلمة", "المعنى بالعربي، ثم وقفة تقول فيها الكلمة، ثم تسمعها بالإنجليزي"),
                ("2-repeat.mp3", "ردّد الجملة", "جملة، ثم وقفة تعيدها فيها بصوتك"),
                ("3-conversation.mp3", "المحادثة", "المحادثة كاملة، ثم مرة تانية تقول فيها جمل الشخص التاني"))


def lesson_row(page_dir, path, title, note, group_title):
    # Lessons are 48 kbps, so the size gives the length until the browser reads the file.
    duration = round((ROOT / path).stat().st_size / MP3_BYTES_PER_SECOND, 1)
    src = escape(rel(page_dir, path))
    kind = path.rsplit("/", 1)[-1].removesuffix(".mp3")
    pick = (f"<input type='checkbox' class='lesson-pick' data-src='{src}' data-kind='{kind}' data-seconds='{duration}' "
            f"data-title='{escape(group_title)} - {escape(title)}' aria-label='أضف {escape(title)} إلى قائمة التشغيل'>")
    return (f"<li class='lesson'><label class='lesson-head'>{pick}<span><strong>{escape(title)}</strong>"
            f"<span class='tr'>{escape(note)}</span></span></label>{player_bar(src, duration)}</li>")


def playlist_panel():
    picks = "".join(f"<button type='button' data-pick='{pick}'>{label}</button>" for pick, label in (
        ("all", "الكل"), ("1-recall", "كل افتكر الكلمة"), ("2-repeat", "كل ردّد الجملة"),
        ("3-conversation", "كل المحادثات"), ("none", "مسح التحديد")))
    return f"""<section class="playlist" aria-label="قائمة التشغيل">
<div class="playlist-head"><h2>قائمة التشغيل</h2><span class="playlist-summary" role="status"></span></div>
<div class="playlist-picks">{picks}</div>
{player_bar("", 0, playlist=True)}
<p class="playlist-now" role="status"></p>
</section>"""


def build_audio_page(topic):
    """Lists the phone lessons that exist in mobile-audio/ so they can be played from the site."""
    page_dir = f"topics/{topic['id']}/audio"
    base = f"mobile-audio/{topic['id']}"
    body = f"""<div class="page-title"><h1>الدروس الصوتية</h1>{ltr('Audio Lessons', 'p', 'sub')}</div>
<p class="hint">ملفات MP3 بوقفات تقول فيها الكلمات بصوتك. علّم على الملفات اللي عايزها وشغلها كقائمة، أو انقل مجلد <span lang="en" dir="ltr">mobile-audio</span> من مجلد البرنامج إلى موبايلك.</p>
{playlist_panel()}"""
    studied = [section for section in all_sections(topic) if section["type"] in ("words", "expressions")]
    missing = 0
    all_paragraphs = f"{base}/all-paragraphs.mp3"
    if (ROOT / all_paragraphs).exists():
        row = lesson_row(page_dir, all_paragraphs, "كل الفقرات", "الفقرات ورا بعض للسماع المتواصل", topic["ar"])
        body += f"<section class='block lesson-group'><h2>{escape(topic['ar'])}</h2><ul class='lessons'>{row}</ul></section>"
    for number, section in enumerate(studied, 1):
        folder = f"{base}/{number:02d}-{re.sub(r'^[0-9]+-', '', section['id'])}"
        if not (ROOT / folder).exists():
            missing += 1
            continue
        rows = "".join(lesson_row(page_dir, f"{folder}/{name}", title, note, section["ar"]) for name, title, note in LESSON_TYPES)
        body += (f"<section class='block lesson-group'><div class='block-head'><h2>{escape(section['ar'])} {ltr(section['en'], 'small')}</h2>"
                 f"<button type='button' class='pick-section'>تحديد القسم</button></div><ul class='lessons'>{rows}</ul></section>")
    if missing:
        body += f"<p class='hint'>باقي {missing} قسم لم تُجهَّز دروسهم بعد.</p>"
    crumbs = [(topic["ar"], rel(page_dir, f"topics/{topic['id']}/index.html")), ("الدروس الصوتية", None)]
    write_page(page_dir, page(page_dir, f"Audio Lessons - {topic['en']}", crumbs, body, ("player.js", "playlist.js")))


def topic_stats(topic):
    words, phrases = set(), set()
    sentences = dialogues = 0
    for section in all_sections(topic):
        if section["type"] == "words":
            for item in section["data"]:
                (phrases if " " in item["text"] else words).add(item["text"].lower())
        elif section["type"] == "expressions":
            phrases.update(item["text"].lower() for item in section["data"])
        elif section["type"] == "sentences":
            sentences += item_count(section)
        else:
            dialogues += len(section["data"])
    return {"words": len(words), "phrases": len(phrases), "sentences": sentences,
            "dialogues": dialogues, "word_set": words}


def build_home(topics):
    words = set()
    cards = ""
    for topic, stats in topics:
        words |= stats["word_set"]
        icon = f"topics/{topic['id']}/media/images/{image_name(topic['emoji'])}"
        cards += (f"<a class='tile' href='topics/{topic['id']}/index.html'><img src='{icon}' alt='' width='56' height='56'>"
                  f"<span><strong>{escape(topic['ar'])}</strong>{ltr(topic['en'], 'em')}<small>{stats['words']} كلمة</small></span></a>")
    for name in PLANNED:
        cards += f"<div class='tile soon'><span><strong>{escape(name)}</strong><small>قريبًا</small></span></div>"
    audio_links = "".join(f"<a href='topics/{topic['id']}/audio/index.html'>🎧 الدروس الصوتية: {escape(topic['ar'])}</a> · "
                          for topic, _ in topics)
    percent = len(words) * 100 / WORD_GOAL
    body = f"""<div class="page-title"><h1>رحلتك نحو احتراف الإنجليزية</h1></div>
<section class="goal">
<div class="goal-num"><strong>{len(words)}</strong> من {WORD_GOAL} كلمة أضيفت إلى البرنامج حتى الآن</div>
<div class="bar"><span style="width:{percent:.1f}%"></span></div>
</section>
<section class="block"><h2>المواضيع</h2><div class="tiles">{cards}</div></section>
<p class="foot">{audio_links}<a href="credits.html">مصادر الصور والأصوات</a></p>"""
    write_page("", page("", "Live English", [], body))


def build_credits():
    body = """<div class="page-title"><h1>المصادر</h1></div>
<section class="block prose">
<p>الرموز التعبيرية: <span lang="en" dir="ltr">Twemoji</span> من مشروع jdecked، بترخيص <span lang="en" dir="ltr">CC BY 4.0</span>.</p>
<p>رسومات الساعات والتقاويم والخطوط الزمنية: مولَّدة ضمن هذا البرنامج.</p>
<p>الأصوات: مولَّدة بأصوات <span lang="en" dir="ltr">Microsoft Edge Neural</span> عبر أداة <span lang="en" dir="ltr">edge-tts</span>.</p>
</section>"""
    (ROOT / "credits.html").write_text(page("", "Credits", [("المصادر", None)], body), encoding="utf-8")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    pages_only = "--pages" in sys.argv
    topics = [load_topic(folder) for folder in sorted(CONTENT.iterdir()) if (folder / "topic.json").exists()]
    ok = True
    summary = []
    for topic in topics:
        if not pages_only:
            ok = build_images(topic) and ok
            ok = asyncio.run(build_audio(topic)) and ok
        stats = topic_stats(topic)
        build_section_pages(topic)
        build_topic_page(topic, stats)
        build_audio_page(topic)
        summary.append((topic, stats))
        print(f"{topic['en']}: {stats['words']} words, {stats['phrases']} phrases, "
              f"{stats['sentences']} sentences, {stats['dialogues']} dialogues")
    build_home(summary)
    build_credits()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
