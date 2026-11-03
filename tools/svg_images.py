"""Draws the small explanatory pictures (clocks, calendars, timelines...) as SVG.

Every function returns a complete SVG document drawn on a 120 x 120 canvas.
draw(spec) turns a picture spec from the content files, such as "clock:3:15",
into its SVG.
"""
import math
import re
from html import escape

INK = "#26323f"
MUTED = "#a9b4bf"
ACCENT = "#d9483b"
TEAL = "#14808a"
FONT = "font-family='Segoe UI,Arial,sans-serif'"
MONTHS = "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split()
DAYS = "MON TUE WED THU FRI SAT SUN".split()
SEASON_COLORS = {12: "#3b82c4", 1: "#3b82c4", 2: "#3b82c4",
                 3: "#3f9d58", 4: "#3f9d58", 5: "#3f9d58",
                 6: "#e89a1c", 7: "#e89a1c", 8: "#e89a1c",
                 9: "#b4602a", 10: "#b4602a", 11: "#b4602a"}


def _svg(body):
    return f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 120 120'>{body}</svg>"


def _hand(angle, length, color, width):
    rad = math.radians(angle - 90)
    x, y = 60 + length * math.cos(rad), 60 + length * math.sin(rad)
    return (f"<line x1='60' y1='60' x2='{x:.1f}' y2='{y:.1f}' stroke='{color}' "
            f"stroke-width='{width}' stroke-linecap='round'/>")


def clock(hour, minute, highlight=""):
    body = f"<circle cx='60' cy='60' r='54' fill='#fff' stroke='{INK}' stroke-width='5'/>"
    for tick in range(12):
        a = math.radians(tick * 30)
        inner = 44 if tick % 3 == 0 else 47
        body += (f"<line x1='{60 + inner * math.sin(a):.1f}' y1='{60 - inner * math.cos(a):.1f}' "
                 f"x2='{60 + 50 * math.sin(a):.1f}' y2='{60 - 50 * math.cos(a):.1f}' "
                 f"stroke='{INK}' stroke-width='{3 if tick % 3 == 0 else 1.5}'/>")
    body += _hand((hour % 12 + minute / 60) * 30, 25, ACCENT if highlight == "h" else INK, 6)
    body += _hand(minute * 6, 38, ACCENT if highlight == "m" else INK, 4)
    if highlight == "s":
        body += _hand(130, 44, ACCENT, 2.5)
    body += f"<circle cx='60' cy='60' r='4' fill='{INK}'/>"
    # Numbers go on top with a white edge, so a hand passing under them never hides them.
    for num, x, y in ((12, 60, 36), (3, 88, 66), (6, 60, 95), (9, 32, 66)):
        body += (f"<text x='{x}' y='{y}' text-anchor='middle' font-size='14' font-weight='600' fill='{INK}' "
                 f"stroke='#fff' stroke-width='3' paint-order='stroke' {FONT}>{num}</text>")
    return _svg(body)


def digital(hour, minute):
    suffix = "AM" if hour < 12 else "PM"
    shown = hour % 12 or 12
    return _svg(
        f"<rect x='6' y='28' width='108' height='64' rx='12' fill='{INK}'/>"
        f"<text x='60' y='68' text-anchor='middle' font-size='30' font-weight='700' fill='#5ef2c4' {FONT}>{shown}:{minute:02d}</text>"
        f"<text x='60' y='84' text-anchor='middle' font-size='12' font-weight='600' fill='#5ef2c4' {FONT}>{suffix}</text>")


def month(number):
    color = SEASON_COLORS[number]
    return _svg(
        f"<rect x='14' y='18' width='92' height='90' rx='9' fill='#fff' stroke='{color}' stroke-width='4'/>"
        f"<path d='M14 27a9 9 0 0 1 9-9h74a9 9 0 0 1 9 9v21H14z' fill='{color}'/>"
        f"<rect x='36' y='10' width='6' height='16' rx='3' fill='{INK}'/><rect x='78' y='10' width='6' height='16' rx='3' fill='{INK}'/>"
        f"<text x='60' y='43' text-anchor='middle' font-size='17' font-weight='700' fill='#fff' {FONT}>{MONTHS[number - 1]}</text>"
        f"<text x='60' y='92' text-anchor='middle' font-size='36' font-weight='700' fill='{INK}' {FONT}>{number}</text>")


def day(first, last=None):
    last = last or first
    body = ""
    for i in range(7):
        on = first <= i + 1 <= last
        body += (f"<rect x='{5 + i * 16}' y='72' width='14' height='30' rx='4' fill='{ACCENT if on else '#e4e9ee'}'/>"
                 f"<text x='{12 + i * 16}' y='91' text-anchor='middle' font-size='9' font-weight='700' fill='{'#fff' if on else '#7a8794'}' {FONT}>{'MTWTFSS'[i]}</text>")
    title = DAYS[first - 1] if first == last else f"{DAYS[first - 1]}–{DAYS[last - 1]}"
    size = 32 if first == last else 21
    body += f"<text x='60' y='52' text-anchor='middle' font-size='{size}' font-weight='700' fill='{INK}' {FONT}>{title}</text>"
    return _svg(body)


SKIES = {
    # name: (top color, bottom color, sun x, sun y, sun color)
    "dawn": ("#2c3e6b", "#f5a08a", None, None, None),
    "sunrise": ("#7fb6e0", "#fbc77a", 24, 84, "#f7812b"),
    "morning": ("#8ccbf2", "#d7f0fb", 36, 46, "#fbc02d"),
    "noon": ("#4faee8", "#b8e3f8", 60, 20, "#fdd835"),
    "afternoon": ("#6dbbec", "#f6e3b4", 86, 42, "#fbb02d"),
    "sunset": ("#6a5a9c", "#f6854b", 96, 84, "#e8421f"),
    "evening": ("#27346b", "#c0617c", None, None, None),
    "dusk": ("#1d2650", "#6a4a86", None, None, None),
    "twilight": ("#1f3a78", "#f2b68c", None, None, None),
    "night": ("#0c1533", "#1f2a55", None, None, None),
}


def sky(name):
    top, bottom, sun_x, sun_y, sun = SKIES[name]
    grad = f"s{name}"
    body = (f"<defs><linearGradient id='{grad}' x1='0' y1='0' x2='0' y2='1'>"
            f"<stop offset='0' stop-color='{top}'/><stop offset='1' stop-color='{bottom}'/></linearGradient></defs>"
            f"<rect x='4' y='4' width='112' height='112' rx='14' fill='url(#{grad})'/>")
    if sun:
        body += f"<circle cx='{sun_x}' cy='{sun_y}' r='13' fill='{sun}'/>"
    if name in ("night", "dusk", "evening"):
        body += "<path d='M86 22a15 15 0 1 0 12 25 13 13 0 1 1-12-25z' fill='#f6e7a8'/>"
    if name in ("night", "dusk"):
        for x, y in ((22, 22), (40, 40), (60, 18), (28, 62), (70, 54), (94, 66)):
            body += f"<circle cx='{x}' cy='{y}' r='1.6' fill='#fff'/>"
    body += "<path d='M4 90h112v12a14 14 0 0 1-14 14H18A14 14 0 0 1 4 102z' fill='#26323f'/>"
    return _svg(body)


def face():
    """A clock face with no hands, so the numbers are the subject."""
    body = f"<circle cx='60' cy='60' r='54' fill='#fff' stroke='{INK}' stroke-width='5'/>"
    for hour in range(1, 13):
        a = math.radians(hour * 30)
        x, y = 60 + 41 * math.sin(a), 60 - 41 * math.cos(a) + 5
        body += f"<text x='{x:.1f}' y='{y:.1f}' text-anchor='middle' font-size='14' font-weight='700' fill='{INK}' {FONT}>{hour}</text>"
    return _svg(body)


def wrist():
    return _svg(
        "<rect x='-6' y='42' width='132' height='38' rx='16' fill='#e8b48c' transform='rotate(-24 60 60)'/>"
        "<rect x='46' y='24' width='28' height='72' rx='5' fill='#3d4752' transform='rotate(-24 60 60)'/>"
        "<circle cx='60' cy='60' r='21' fill='#cdd6dd'/><circle cx='60' cy='60' r='16' fill='#fff'/>"
        f"<line x1='60' y1='60' x2='60' y2='49' stroke='{INK}' stroke-width='3' stroke-linecap='round'/>"
        f"<line x1='60' y1='60' x2='68' y2='64' stroke='{INK}' stroke-width='3' stroke-linecap='round'/>")


def sundial():
    return _svg(
        "<circle cx='98' cy='20' r='13' fill='#fbc02d'/>"
        "<ellipse cx='56' cy='88' rx='50' ry='22' fill='#d8cdb8' stroke='#8f8571' stroke-width='3'/>"
        "<path d='M56 88V46l26 42z' fill='#6e7a86'/>"
        "<path d='M56 88L18 96l6 6z' fill='#3d4752' opacity='.55'/>"
        + "".join(f"<line x1='{56 + 40 * math.cos(math.radians(a)):.1f}' y1='{88 + 17 * math.sin(math.radians(a)):.1f}' "
                  f"x2='{56 + 46 * math.cos(math.radians(a)):.1f}' y2='{88 + 20 * math.sin(math.radians(a)):.1f}' stroke='#6b6250' stroke-width='2'/>"
                  for a in range(0, 360, 30)))


def timetable():
    """A departures board: times next to bars."""
    body = f"<rect x='8' y='14' width='104' height='92' rx='8' fill='{INK}'/>"
    for i, stamp in enumerate(("08:15", "09:40", "11:05", "13:30")):
        y = 36 + i * 21
        body += (f"<text x='17' y='{y}' font-size='13' font-weight='700' fill='#ffd54f' {FONT}>{stamp}</text>"
                 f"<rect x='60' y='{y - 10}' width='44' height='9' rx='2' fill='#8fa3b5'/>")
    return _svg(body)


def days_strip(offset):
    """Five days around today, with one marked: -1 is yesterday, 0 today, +1 tomorrow."""
    body = ""
    for i in range(5):
        day_offset = i - 2
        on = day_offset == offset
        x = 4 + i * 23
        body += f"<rect x='{x}' y='36' width='20' height='48' rx='4' fill='{ACCENT if on else '#e4e9ee'}'/>"
        label = "0" if day_offset == 0 else f"{day_offset:+d}"
        body += f"<text x='{x + 10}' y='66' text-anchor='middle' font-size='14' font-weight='700' fill='{'#fff' if on else '#6a7783'}' {FONT}>{label}</text>"
    body += f"<text x='60' y='106' text-anchor='middle' font-size='15' font-weight='600' fill='{INK}' {FONT}>0 = today</text>"
    return _svg(body)


def blue_moon():
    body = "<rect x='4' y='4' width='112' height='112' rx='14' fill='#0c1533'/><circle cx='60' cy='60' r='36' fill='#5aa9ee'/>"
    body += "<circle cx='48' cy='50' r='7' fill='#3f8ad0'/><circle cx='72' cy='68' r='9' fill='#3f8ad0'/><circle cx='68' cy='42' r='4' fill='#3f8ad0'/>"
    for x, y in ((18, 20), (100, 24), (20, 96), (102, 92), (30, 58)):
        body += f"<circle cx='{x}' cy='{y}' r='1.8' fill='#fff'/>"
    return _svg(body)


# ---------- Scenes built from emoji and the drawings above ----------

def _inner(svg):
    return re.sub(r"^<svg[^>]*>|</svg>\s*$", "", svg.strip())


def _split(spec, separator):
    """Splits on a separator, ignoring anything inside [brackets]."""
    parts, depth, current = [], 0, ""
    for char in spec:
        depth += (char == "[") - (char == "]")
        if char == separator and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += char
    return parts + [current]


def _place(item, x, y, size, load_emoji):
    """One scene element in a square box: an emoji, or a [drawn:spec] in brackets."""
    if item.startswith("["):
        return (f"<svg x='{x}' y='{y}' width='{size}' height='{size}' viewBox='0 0 120 120'>"
                f"{_inner(draw(item[1:-1], load_emoji))}</svg>")
    return (f"<svg x='{x}' y='{y}' width='{size}' height='{size}' viewBox='0 0 36 36'>"
            f"{_inner(load_emoji(item))}</svg>")


def _arrow(x, y):
    return f"<path d='M{x} {y}h9v-5l9 8-9 8v-5h-9z' fill='{TEAL}'/>"


def _text(text, y, size=None, color=INK):
    if size is None:
        size = 19 if len(text) <= 10 else 15 if len(text) <= 14 else 12
    return f"<text x='60' y='{y}' text-anchor='middle' font-size='{size}' font-weight='700' fill='{color}' {FONT}>{escape(text)}</text>"


def pair(spec, load_emoji):
    """Things in order: A>B or A>B>C. In A>B, a leading ! rings the part the word is about."""
    items = _split(spec, ">")
    if len(items) == 2:
        body = ""
        for i, centre in ((0, 27), (1, 93)):
            if items[i].startswith("!"):
                items[i] = items[i][1:]
                body += f"<circle cx='{centre}' cy='61' r='25' fill='#fff2c4' stroke='{ACCENT}' stroke-width='3'/>"
            body += _place(items[i], centre - 18, 43, 36, load_emoji)
        return _svg(body + _arrow(51, 53))
    return _svg(_place(items[0], 0, 8, 44, load_emoji) + _arrow(45, 22) + _place(items[1], 76, 8, 44, load_emoji)
                + _arrow(70, 66).replace("M70 66", "M62 58") + _place(items[2], 38, 72, 44, load_emoji))


def together(spec, load_emoji):
    """Two things happening together: A+B."""
    first, second = _split(spec, "+")
    return _svg(_place(first, 2, 30, 58, load_emoji) + _place(second, 60, 30, 58, load_emoji))


def badge(spec, load_emoji):
    """A subject with a smaller detail on its corner: A/B."""
    base, detail = _split(spec, "/")
    return _svg(_place(base, 4, 2, 90, load_emoji)
                + "<circle cx='88' cy='88' r='30' fill='#fff' stroke='#d7dde3' stroke-width='2'/>"
                + _place(detail, 66, 66, 44, load_emoji))


def forbidden(item, load_emoji):
    return _svg(_place(item, 22, 22, 76, load_emoji)
                + f"<circle cx='60' cy='60' r='50' fill='none' stroke='{ACCENT}' stroke-width='8'/>"
                  f"<line x1='25' y1='25' x2='95' y2='95' stroke='{ACCENT}' stroke-width='8'/>")


def repeated(spec, load_emoji):
    """The same thing again and again: A*3."""
    item, count = spec.rsplit("*", 1)
    count = int(count)
    size = 38 if count == 3 else 46 if count <= 4 else 34
    columns = 2 if count <= 4 else 3
    body = ""
    for i in range(count):
        row = i // columns
        x = 10 + (i % columns) * (size + 8)
        y = 10 + row * (size + 8) if count > 3 else 37
        if count == 3:
            x = 1 + i * 40
        body += _place(item, x, y, size, load_emoji)
    return _svg(body)


def grid(spec, load_emoji):
    a, b, c, d = spec.split(",")
    return _svg(_place(a, 6, 6, 50, load_emoji) + _place(b, 64, 6, 50, load_emoji)
                + _place(c, 6, 64, 50, load_emoji) + _place(d, 64, 64, 50, load_emoji))


def caption(spec, load_emoji):
    """A picture with a few words under it: A~text."""
    item, text = _split(spec, "~")
    return _svg(_place(item, 22, 2, 76, load_emoji) + _text(text, 104))


def timeline(spec, load_emoji):
    """A time arrow with "now" fixed at 50, then an optional picture and caption.

    Position is one point (30), a span (20-50), or several points (10,35,65,90).
    """
    position, *rest = _split(spec, "~")
    picture = rest[0] if rest else ""
    words = rest[1] if len(rest) > 1 else ""
    y = 70

    def x_of(value):
        return 10 + float(value)

    body = (f"<line x1='6' y1='{y}' x2='114' y2='{y}' stroke='{INK}' stroke-width='3'/>"
            f"<path d='M116 {y}l-9-5v10z' fill='{INK}'/>"
            f"<line x1='60' y1='{y - 8}' x2='60' y2='{y + 8}' stroke='{INK}' stroke-width='3'/>"
            f"<text x='60' y='{y + 20}' text-anchor='middle' font-size='11' font-weight='600' fill='#5d6b78' {FONT}>now</text>")
    if "-" in position:
        start, end = position.split("-")
        body += f"<line x1='{x_of(start)}' y1='{y}' x2='{x_of(end)}' y2='{y}' stroke='{ACCENT}' stroke-width='9' stroke-linecap='round'/>"
        centre = (x_of(start) + x_of(end)) / 2
    else:
        points = position.split(",")
        for point in points:
            body += f"<circle cx='{x_of(point)}' cy='{y}' r='7' fill='{ACCENT}' stroke='#fff' stroke-width='2'/>"
        centre = x_of(points[0]) if len(points) == 1 else 60
    if picture:
        size = 46
        body += _place(picture, max(0, min(120 - size, centre - size / 2)), 8, size, load_emoji)
    if words:
        body += _text(words, 112, 13)
    return _svg(body)


def frequency(filled, item, load_emoji):
    """How often: a picture of the activity over ten dots, one per occasion."""
    body = _place(item, 32, 0, 56, load_emoji)
    for i in range(10):
        x, y = 24 + (i % 5) * 18, 72 + (i // 5) * 19
        body += f"<circle cx='{x}' cy='{y}' r='7.5' fill='{TEAL if i < filled else '#dfe5ea'}'/>"
    return _svg(body)


def tile(text):
    head, _, tail = text.partition(" ")
    size = 42 if len(head) <= 3 else 32 if len(head) == 4 else 26
    return _svg(
        f"<rect x='6' y='6' width='108' height='108' rx='16' fill='{TEAL}'/>"
        f"<text x='60' y='64' text-anchor='middle' font-size='{size}' font-weight='700' fill='#fff' {FONT}>{escape(head)}</text>"
        f"<text x='60' y='90' text-anchor='middle' font-size='17' font-weight='600' fill='#d8f3f4' {FONT}>{escape(tail)}</text>")


def draw(spec, load_emoji):
    kind, _, rest = spec.partition(":")
    args = rest.split(":")
    if kind == "face":
        return face()
    if kind == "wrist":
        return wrist()
    if kind == "sundial":
        return sundial()
    if kind == "timetable":
        return timetable()
    if kind == "bluemoon":
        return blue_moon()
    if kind == "days":
        return days_strip(int(args[0]))
    if kind == "pair":
        return pair(rest, load_emoji)
    if kind == "together":
        return together(rest, load_emoji)
    if kind == "badge":
        return badge(rest, load_emoji)
    if kind == "no":
        return forbidden(rest, load_emoji)
    if kind == "rep":
        return repeated(rest, load_emoji)
    if kind == "grid":
        return grid(rest, load_emoji)
    if kind == "cap":
        return caption(rest, load_emoji)
    if kind == "tl":
        return timeline(rest, load_emoji)
    if kind == "clock":
        return clock(int(args[0]), int(args[1]), args[2] if len(args) > 2 else "")
    if kind == "digital":
        return digital(int(args[0]), int(args[1]))
    if kind == "month":
        return month(int(args[0]))
    if kind == "day":
        first, _, last = args[0].partition("-")
        return day(int(first), int(last) if last else None)
    if kind == "sky":
        return sky(args[0])
    if kind == "freq":
        return frequency(int(args[0]), args[1], load_emoji)
    if kind == "tile":
        return tile(rest)
    raise ValueError(f"Unknown picture spec: {spec}")


DRAWN_KINDS = ("clock", "digital", "month", "day", "sky", "freq", "tile", "face", "wrist", "sundial",
               "timetable", "bluemoon", "days", "pair", "together", "badge", "no", "rep", "grid", "cap", "tl")
