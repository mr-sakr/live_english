"""Builds hands-free MP3 lessons for the phone into mobile-audio/.

    python tools/audio_lessons.py              every section
    python tools/audio_lessons.py clocks days  only these sections

Each section gets three files, and the topic gets one file of all its paragraphs.
All clips share one MP3 format, so lessons are made by joining their frames,
with no audio tools needed. Clips are cached in tools/lesson-clips.
"""
import asyncio
import re
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import build
from mp3_frames import FRAME_SECONDS, silence, speak_frames, split_frames

OUTPUT = build.ROOT / "mobile-audio"
CACHE = Path(__file__).resolve().parent / "lesson-clips"
ARABIC = "ar-EG-SalmaNeural"
ENGLISH = "en-US-AriaNeural"
SPEAKERS = {"a": "en-US-JennyNeural", "b": "en-US-GuyNeural"}

RECALL_PAUSE = 3.0
REPEAT_EXTRA = 1.0
SHORT_PAUSE = 1.0
ITEM_PAUSE = 1.5
SECTION_PAUSE = 2.0


def spoken_arabic(text):
    """Dictionary punctuation becomes a pause when read aloud."""
    return re.sub(r"\s*[/()]\s*", "، ", text).strip("، ")


def clip_path(voice, text):
    return CACHE / f"{voice}-{zlib.crc32(text.encode()):08x}.mp3"


async def make_clip(limit, voice, text):
    """Saves one spoken clip."""
    target = clip_path(voice, text)
    if target.exists():
        return None
    async with limit:
        try:
            frames, _ = await speak_frames(text, voice)
            target.write_bytes(b"".join(frames))
            return None
        except Exception as error:
            return f"{text}: {error}"


def clip_seconds(voice, text):
    return len(split_frames(clip_path(voice, text).read_bytes())) * FRAME_SECONDS


# ---------- Lesson plans: lists of ("say", voice, text), ("gap", seconds), ("gap_like", voice, text) ----------

def recall_plan(section):
    plan = []
    for item in section["data"]:
        plan += [("say", ARABIC, spoken_arabic(item["ar"])), ("gap", RECALL_PAUSE),
                 ("say", ENGLISH, item["text"]), ("gap", SHORT_PAUSE),
                 ("say", ENGLISH, item["text"]), ("gap", ITEM_PAUSE)]
    return plan


def repeat_plan(section):
    plan = []
    for item in section["data"]:
        plan += [("say", ENGLISH, item["ex"]), ("gap_like", ENGLISH, item["ex"])]
    return plan


def conversation_plan(section):
    lines = section["story"]["lines"]
    plan = []
    for line in lines:
        plan += [("say", SPEAKERS[line["who"]], line["en"]), ("gap", 0.5)]
    plan += [("gap", SECTION_PAUSE)]
    for line in lines:
        if line["who"] == "a":
            plan += [("say", SPEAKERS["a"], line["en"]), ("gap", 0.5)]
        else:
            plan += [("gap_like", SPEAKERS["b"], line["en"])]
    return plan


def plan_clips(plan):
    return {(step[1], step[2]) for step in plan if step[0] in ("say", "gap_like")}


def render(plan):
    """Joins a plan into frames, and records what each stretch of time should contain."""
    frames, timeline = [], []

    def add(kind, new_frames):
        timeline.append({"kind": kind, "start": len(frames) * FRAME_SECONDS, "seconds": len(new_frames) * FRAME_SECONDS})
        frames.extend(new_frames)

    for step in plan:
        if step[0] == "say":
            add("speech", split_frames(clip_path(step[1], step[2]).read_bytes()))
        elif step[0] == "gap":
            add("pause", silence(step[1]))
        elif step[0] == "gap_like":
            add("pause", silence(clip_seconds(step[1], step[2]) + REPEAT_EXTRA))
        else:
            add("speech", split_frames(Path(step[1]).read_bytes()))
    return frames, timeline


def id3_tag(title, album):
    """Players show these names, since every section's files are named alike."""
    def text_frame(name, value):
        payload = b"\x01" + value.encode("utf-16")
        return name + struct.pack(">I", len(payload)) + b"\x00\x00" + payload

    body = text_frame(b"TIT2", title) + text_frame(b"TALB", album)
    size = len(body)
    return b"ID3\x03\x00\x00" + bytes([size >> 21 & 127, size >> 14 & 127, size >> 7 & 127, size & 127]) + body


def write_lesson(path, plan, title, album):
    frames, timeline = render(plan)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(id3_tag(title, album) + b"".join(frames))
    minutes = len(frames) * FRAME_SECONDS / 60
    print(f"  {path.relative_to(OUTPUT)}: {minutes:.1f} min, {path.stat().st_size / 1_000_000:.1f} MB")
    return timeline


def section_folder(topic, section):
    studied = [s for s in build.all_sections(topic) if s["type"] in ("words", "expressions")]
    name = re.sub(r"^\d+-", "", section["id"])
    return OUTPUT / topic["id"] / f"{studied.index(section) + 1:02d}-{name}"


def lessons_for(topic, wanted):
    """Every file to write: (path, plan, title)."""
    lessons = []
    paragraphs = []
    for section in build.all_sections(topic):
        if section["type"] not in ("words", "expressions"):
            continue
        name = re.sub(r"^\d+-", "", section["id"])
        audio = build.TOPICS_OUT / topic["id"] / build.audio_rel("paragraphs", section["story"]["paragraph"]["en"])
        paragraphs += [("file", str(audio)), ("gap", SECTION_PAUSE)]
        if wanted and name not in wanted:
            continue
        folder = section_folder(topic, section)
        lessons += [(folder / "1-recall.mp3", recall_plan(section), f"{section['en']} - Recall"),
                    (folder / "2-repeat.mp3", repeat_plan(section), f"{section['en']} - Repeat"),
                    (folder / "3-conversation.mp3", conversation_plan(section), f"{section['en']} - Conversation")]
    lessons.append((OUTPUT / topic["id"] / "all-paragraphs.mp3", paragraphs, "All paragraphs"))
    return lessons


async def make_clips(clips):
    limit = asyncio.Semaphore(6)
    results = await asyncio.gather(*(make_clip(limit, voice, text) for voice, text in sorted(clips)))
    return [result for result in results if result]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    CACHE.mkdir(exist_ok=True)
    wanted = set(sys.argv[1:])
    timelines = {}
    for folder in sorted(build.CONTENT.iterdir()):
        if not (folder / "topic.json").exists():
            continue
        topic = build.load_topic(folder)
        lessons = lessons_for(topic, wanted)
        clips = set().union(*(plan_clips(plan) for _, plan, _ in lessons))
        failed = asyncio.run(make_clips(clips))
        if failed:
            print("Clips that failed:")
            print("\n".join(f"  {line}" for line in failed))
            return 1
        for path, plan, title in lessons:
            timelines[path] = write_lesson(path, plan, title, f"Live English - {topic['en']}")
        build.build_audio_page(topic)
    return 0 if timelines else 1


if __name__ == "__main__":
    sys.exit(main())
