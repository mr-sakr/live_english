"""Joining speech clips at the MP3 frame level, so no audio tools are needed.

Every clip is 48 kbps mono at 24 kHz: frames of 144 bytes, plus 1 when padded, lasting 24 ms.
"""
import asyncio

FRAME_SECONDS = 0.024
FRAME_BYTES = 144
SILENT_FRAME = bytes([0xFF, 0xF3, 0x64, 0xC4]) + bytes(FRAME_BYTES - 4)
TICKS_PER_SECOND = 10_000_000
SPOKEN_TAIL = 0.2


def split_frames(data):
    """Splits MP3 bytes into frames, refusing anything that is not the expected format."""
    position = 0
    if data[:3] == b"ID3":
        size = data[6:10]
        position = 10 + (size[0] << 21 | size[1] << 14 | size[2] << 7 | size[3])
    frames = []
    while position < len(data):
        header = data[position:position + 4]
        if len(header) < 4 or header[0] != 0xFF or header[1] != 0xF3 or header[2] >> 4 != 6 or (header[2] >> 2) & 3 != 1:
            raise ValueError(f"Unexpected MP3 data at byte {position}")
        size = FRAME_BYTES + ((header[2] >> 1) & 1)
        frames.append(data[position:position + size])
        position += size
    return frames


def silence(seconds):
    return [SILENT_FRAME] * round(seconds / FRAME_SECONDS)


async def speak_frames(text, voice):
    """Speaks text: (frames, words). The long silence the service adds at the end is removed."""
    import edge_tts

    for attempt in range(4):
        try:
            audio, words = bytearray(), []
            async for chunk in edge_tts.Communicate(text, voice, boundary="WordBoundary").stream():
                if chunk["type"] == "audio":
                    audio += chunk["data"]
                elif chunk["type"] == "WordBoundary":
                    words.append({"text": chunk["text"], "start": chunk["offset"] / TICKS_PER_SECOND,
                                  "end": (chunk["offset"] + chunk["duration"]) / TICKS_PER_SECOND})
            frames = split_frames(bytes(audio))
            if words:
                frames = frames[:int((words[-1]["end"] + SPOKEN_TAIL) / FRAME_SECONDS) + 1]
            return frames, words
        except Exception:
            if attempt == 3:
                raise
            await asyncio.sleep(1 + attempt * 2)
