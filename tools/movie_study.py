"""Builds private scene-by-scene study pages from your own copy of a film.

    python tools/movie_study.py

Each film lives in movies/<name>/ with movie.mp4, movie.srt, film.json (its title) and
scenes*.txt. Everything in movies/ stays on this computer: .gitignore keeps the film,
its script and these pages out of GitHub.

A scene starts with a header, then one key word per line in the content-file format:

    # id | English title | Arabic title | first-last subtitle | A=Chris,B=Son | default speaker | overrides
    word|ipa|pos|arabic|image|example|example_arabic

Overrides give a subtitle's speakers: "12:AB" (one letter per dash) or "20-25:N" for a range.
A subtitle with dashes must always be listed, since its speakers can't be assumed.

Subtitles only say when a whole line is on screen, so the word highlight is an estimate:
each word's time is worked out from its position within the line.
"""
import asyncio
import json
import re
import sys
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import build
import svg_images

MOVIES = build.ROOT / "movies"
LEAD_IN = 1.0
TAIL = 0.7
TIME = re.compile(r"(\d+):(\d+):(\d+),(\d+) --> (\d+):(\d+):(\d+),(\d+)")
AD = re.compile(r"opensubtitles", re.I)
ARABIC = re.compile(r"[؀-ۿ]")
WORD_KEYS = ("text", "ipa", "pos", "ar", "img", "ex", "ex_ar")


def seconds(hours, minutes, secs, millis):
    return int(hours) * 3600 + int(minutes) * 60 + int(secs) + int(millis) / 1000


def split_parts(lines, translation=False):
    """A cue with dashes holds several speakers, one per dash; otherwise it is one speaker."""
    lines = [re.sub(r"</?[a-z][^>]*>", "", line, flags=re.I).strip() for line in lines]
    if translation:
        lines = [line for line in lines if line]
    else:
        # Some files mix in Arabic lines: keep only the English before them.
        lines = [line[:match.start()].strip() if (match := ARABIC.search(line)) else line for line in lines]
        lines = [line for line in lines if re.search("[A-Za-z0-9]", line)]
    if not lines:
        return []
    if not any(line.startswith("-") for line in lines):
        return [" ".join(lines)]
    parts = []
    for line in lines:
        if line.startswith("-") or not parts:
            parts.append(line.lstrip("- ").strip())
        else:
            parts[-1] += " " + line
    return parts


def read_cues(path):
    """Subtitle number -> start, end and the spoken parts."""
    cues = {}
    text = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    text = text.replace("r�sum�", "résumé").replace("�", "'")
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = block.split("\n")
        match = TIME.match(lines[1]) if len(lines) > 1 else None
        if not match or AD.search(block):
            continue
        parts = split_parts(lines[2:])
        if parts:
            groups = match.groups()
            cues[int(lines[0].strip())] = {"start": seconds(*groups[:4]), "end": seconds(*groups[4:]), "parts": parts}
    return cues


def read_translation(path):
    """The translation's lines in time order; its numbering need not match the English file."""
    lines = []
    text = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    for block in re.split(r"\n\s*\n", text.strip()):
        rows = block.split("\n")
        match = TIME.match(rows[1]) if len(rows) > 1 else None
        if match:
            groups = match.groups()
            lines.append({"start": seconds(*groups[:4]), "end": seconds(*groups[4:]),
                          "parts": split_parts(rows[2:], translation=True), "used": False})
    return lines


def attach_translation(cues, translation):
    """Gives each English part its translation, matching subtitles by when they appear on screen."""
    for cue in cues.values():
        cue["translated"] = [""] * len(cue["parts"])
        matches = [line for line in translation
                   if min(cue["end"], line["end"]) - max(cue["start"], line["start"]) > 0.5 * min(cue["end"] - cue["start"], line["end"] - line["start"])]
        for line in matches:
            line["used"] = True
        if len(matches) == 1 and len(matches[0]["parts"]) == len(cue["parts"]):
            cue["translated"] = matches[0]["parts"]
        elif matches:
            # The two files split this line differently: keep it all together under its first part.
            cue["translated"][0] = " ".join(part for line in matches for part in line["parts"])
    missing = sum(1 for cue in cues.values() if not any(cue["translated"]))
    unused = sum(1 for line in translation if not line["used"])
    print(f"translation: {len(translation)} lines; {missing} English subtitles without one; {unused} translated lines unused")


def read_scenes(folder):
    """Reads scenes*.txt in order."""
    scenes = []
    for path in sorted(folder.glob("scenes*.txt")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                fields = [field.strip() for field in line[2:].split("|")]
                first, last = fields[3].split("-")
                overrides = {}
                for token in fields[6].split():
                    span, who = token.split(":")
                    low, _, high = span.partition("-")
                    for number in range(int(low), int(high or low) + 1):
                        overrides[number] = who
                scenes.append({"id": fields[0], "en": fields[1], "ar": fields[2], "first_cue": int(first), "last_cue": int(last),
                               "names": dict(pair.split("=") for pair in fields[4].split(",")),
                               "default": fields[5], "overrides": overrides, "words": []})
            elif line.strip():
                scenes[-1]["words"].append(dict(zip(WORD_KEYS, line.split("|"))))
    return scenes


def check_scenes(scenes, cues):
    """Stops on anything that would mislabel or lose a line, listing every problem at once."""
    problems, owners, covered = [], {}, set()
    for scene in scenes:
        numbers = [number for number in cues if scene["first_cue"] <= number <= scene["last_cue"]]
        covered.update(numbers)
        for number, who in scene["overrides"].items():
            if number not in numbers:
                problems.append(f"{scene['id']}: override for subtitle {number} is outside the scene or has no text")
            elif len(who) != 1 and len(who) != len(cues[number]["parts"]):
                problems.append(f"{scene['id']}: subtitle {number} has {len(cues[number]['parts'])} parts but speakers '{who}'")
            if number in cues and set(who) - set(scene["names"]):
                problems.append(f"{scene['id']}: unknown speaker in '{who}'")
        for number in numbers:
            if len(cues[number]["parts"]) > 1 and number not in scene["overrides"]:
                problems.append(f"{scene['id']}: subtitle {number} has dashes and needs speakers: {' // '.join(cues[number]['parts'])[:50]}")
        for item in scene["words"]:
            if len(item) != len(WORD_KEYS):
                problems.append(f"{scene['id']}: bad word line: {item.get('text')}")
            else:
                owners.setdefault(item["img"], []).append(f"{scene['id']}: {item['text']}")
    problems += [f"picture {spec} used by {', '.join(names)}" for spec, names in owners.items() if len(names) > 1]
    missing = sorted(set(cues) - covered)
    if missing:
        print("Subtitles in no scene (first 40):", missing[:40])
    if problems:
        print(f"{len(problems)} problems:")
        print("\n".join(f"  {line}" for line in problems))
        raise SystemExit(1)


def timed_words(text, start, end):
    """Wraps each word with its estimated start time, from its position in the line."""
    html, position = "", 0
    for match in re.finditer(r"\S+", text):
        moment = start + (end - start) * match.start() / max(len(text), 1)
        html += escape(text[position:match.start()])
        html += f"<span class='pw' data-t='{moment:.2f}'>{escape(match.group())}</span>"
        position = match.end()
    return html + escape(text[position:])


def scene_lines(scene, cues):
    """The scene's spoken lines in order, each with its speaker and time."""
    numbers = [number for number in sorted(cues) if scene["first_cue"] <= number <= scene["last_cue"]]
    lines = []
    for number in numbers:
        cue = cues[number]
        speakers = scene["overrides"].get(number, scene["default"])
        if len(speakers) == 1:
            speakers = speakers * len(cue["parts"])
        total = sum(len(part) for part in cue["parts"]) or 1
        used = 0
        translated = cue.get("translated", [""] * len(cue["parts"]))
        for part, who, arabic in zip(cue["parts"], speakers, translated):
            start = cue["start"] + (cue["end"] - cue["start"]) * used / total
            used += len(part)
            end = cue["start"] + (cue["end"] - cue["start"]) * used / total
            lines.append({"text": part, "start": start, "end": end, "who": who, "arabic": arabic})
    return lines


def script_html(scene, lines):
    html = ""
    for line in lines:
        name = escape(scene["names"][line["who"]])
        arabic = f"<p class='tr'>{escape(line['arabic'])}</p>" if line["arabic"] else ""
        html += (f"<li class='bubble {line['who'].lower()}' data-start='{line['start']:.2f}' data-end='{line['end']:.2f}'>"
                 "<button type='button' class='line-repeat' aria-pressed='false' aria-label='كرر هذه الجملة' title='كرر هذه الجملة'>↻</button>"
                 f"<div><p class='speaker'>{name}</p><p lang='en' dir='ltr' class='en'>{timed_words(line['text'], line['start'], line['end'])}</p>{arabic}</div></li>")
    return html


def scene_page(film_dir, film, scene, cues):
    page_dir = f"movies/{film_dir}/scenes/{scene['id']}"
    media = build.rel(page_dir, f"movies/{film_dir}")
    lines = scene_lines(scene, cues)
    start = max(0, lines[0]["start"] - LEAD_IN)
    end = lines[-1]["end"] + TAIL
    tabs = "".join(f"<button type='button' role='tab' data-tab='{name}'>{label}</button>"
                   for name, label in (("scene", "المشهد"), ("words", "الكلمات"), ("quiz", "الاختبار")))
    cards = "".join(build.word_card(item, media) for item in scene["words"])
    bar = build.player_bar("", round(end - start, 1), media_element=False)
    body = f"""<div class="page-title"><h1>{escape(scene['ar'])}</h1>{build.ltr(scene['en'], 'p', 'sub')}</div>
<div class="tabs" role="tablist">{tabs}</div>
<section class="panel" data-panel="scene">
<p class="hint">اضغط على أي كلمة لينتقل الفيلم إليها، أو على ↻ لتكرار الجملة. تظليل الكلمة تقريبي، لأن الترجمة تحدد توقيت الجملة فقط.</p>
<div class="scene-grid" data-start="{start:.2f}" data-end="{end:.2f}">
<div class="scene-media">
<video src="{media}/movie.mp4#t={start:.2f}" preload="metadata" playsinline></video>
{bar}
<label class="script-toggle"><input type="checkbox" class="skip-silence" checked> تخطي الأجزاء اللي مفيهاش كلام</label>
<label class="script-toggle"><input type="checkbox" class="show-translation" checked> إظهار الترجمة بالعربي المصري</label>
<label class="script-toggle"><input type="checkbox" class="hide-script"> إخفاء السكريبت لاختبار السمع</label>
</div>
<ol class="bubbles scene-script timed-text">{script_html(scene, lines)}</ol>
</div>
</section>
<section class="panel" data-panel="words" hidden>
<p class="hint">مرّر الماوس على السماعة أو اضغط عليها لتسمع النطق. الأمثلة مكتوبة لهذا الدرس، وليست من الفيلم.</p>
<div class="cards">{cards}</div>
</section>
<section class="panel" data-panel="quiz" hidden><div class="quiz"><p class="quiz-intro">ستسمع كلمة من كلمات المشهد، فاضغط على الصورة التي تعبر عنها.</p><button type="button" class="quiz-go">ابدأ الاختبار</button></div></section>"""
    crumbs = [(film["ar"], build.rel(page_dir, f"movies/{film_dir}/index.html")), (scene["ar"], None)]
    build.write_page(page_dir, build.page(page_dir, f"{scene['en']} - {film['en']}", crumbs, body, ("quiz.js", "scene.js")))


def film_page(film_dir, film, cues):
    page_dir = f"movies/{film_dir}"
    tiles = ""
    for number, scene in enumerate(film["scenes"], 1):
        # Each scene sits with its neighbours in the film page.
        lines = scene_lines(scene, cues)
        minutes = int(lines[0]["start"] // 60)
        tiles += (f"<a class='tile' href='scenes/{scene['id']}/index.html'><span class='thumb-emoji' aria-hidden='true'>🎬</span><span>"
                  f"<strong>{number}. {escape(scene['ar'])}</strong>{build.ltr(scene['en'], 'em')}<small>من الدقيقة {minutes} · {len(lines)} جملة</small></span></a>")
    body = f"""<div class="page-title"><h1>{escape(film['ar'])}</h1>{build.ltr(film['en'], 'p', 'sub')}</div>
<p class="hint">دراسة مشهد مشهد من نسختك. هذا القسم على جهازك فقط ولا يُرفع إلى GitHub.</p>
<section class="block"><h2>المشاهد</h2><div class="tiles">{tiles}</div></section>"""
    build.write_page(page_dir, build.page(page_dir, film["en"], [(film["ar"], None)], body))


def make_media(folder, film):
    """Saves pictures and pronunciation audio for each scene's key words."""
    images = folder / "media" / "images"
    images.mkdir(parents=True, exist_ok=True)
    jobs = {}
    for scene in film["scenes"]:
        for item in scene["words"]:
            svg = svg_images.draw(item["img"], build.load_emoji) if build.is_drawn(item["img"]) else build.load_emoji(item["img"])
            (images / build.image_name(item["img"])).write_text(svg, encoding="utf-8")
            for kind, text in (("us", item["text"]), ("uk", item["text"]), ("sentences", item["ex"])):
                jobs[build.audio_rel(kind, text)] = (build.VOICES[kind], text)

    async def run():
        limit = asyncio.Semaphore(6)
        tasks = []
        for rel, (voice, text) in jobs.items():
            target = folder / rel
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                tasks.append(build.speak(limit, voice, text, target))
        return [result for result in await asyncio.gather(*tasks) if result]

    failed = asyncio.run(run())
    if failed:
        raise SystemExit("Audio failed:\n" + "\n".join(failed))


def write_home_links(films):
    """Shows the films on the home page of this computer only, since movies/ is never uploaded."""
    tiles = "".join(
        f"<a class='tile' href='movies/{name}/index.html'><span class='thumb-emoji' aria-hidden='true'>🎬</span>"
        f"<span><strong>{escape(film['ar'])}</strong>{build.ltr(film['en'], 'em')}<small>{len(film['scenes'])} مشهد</small></span></a>"
        for name, film in films)
    script = ("var films = document.getElementById('films');\n"
              f"films.querySelector('.tiles').innerHTML = {json.dumps(tiles, ensure_ascii=False)};\n"
              "films.hidden = false;\n")
    (MOVIES / "films.js").write_text(script, encoding="utf-8")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    films = []
    for folder in sorted(path for path in MOVIES.iterdir() if path.is_dir()):
        if not (folder / "film.json").exists():
            continue
        film = json.loads((folder / "film.json").read_text(encoding="utf-8"))
        cues = read_cues(folder / "movie.srt")
        if (folder / "movie.ar.srt").exists():
            attach_translation(cues, read_translation(folder / "movie.ar.srt"))
        film["scenes"] = read_scenes(folder)
        check_scenes(film["scenes"], cues)
        make_media(folder, film)
        for scene in film["scenes"]:
            scene_page(folder.name, film, scene, cues)
        film_page(folder.name, film, cues)
        films.append((folder.name, film))
        last = cues[max(cues)]["end"]
        print(f"{film['en']}: {len(film['scenes'])} scene(s), {len(cues)} subtitle lines up to {int(last // 60)} min")
    write_home_links(films)


if __name__ == "__main__":
    main()
