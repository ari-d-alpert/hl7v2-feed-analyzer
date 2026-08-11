"""Load HL7 messages from files or directories.

Handles the messy realities of real feeds:
- one message per file, or many messages concatenated in one file;
- MLLP framing bytes (VT ``\\x0b`` start, FS ``\\x1c`` + CR end) left in dumps;
- CR / LF / CRLF segment terminators;
- a bad message is logged and skipped, never fatal.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterator

from .parser import Message, parse_message


MLLP_START = "\x0b"
MLLP_END = "\x1c"


@dataclass
class LoadResult:
    messages: list[Message]
    skipped: int
    files_read: int


def _split_batch(text: str) -> list[str]:
    """Split a blob that may contain multiple messages.

    Strategy: strip MLLP frame bytes, then split on the start of each MSH
    segment. A new message always begins with an MSH segment, so we treat each
    'MSH' at a line start as a message boundary.
    """
    text = text.replace(MLLP_START, "").replace(MLLP_END, "")
    # Normalize terminators to \n for boundary scanning only.
    norm = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = norm.split("\n")
    chunks: list[list[str]] = []
    for line in lines:
        if line.startswith("MSH"):
            chunks.append([line])          # new message boundary
        elif chunks:
            chunks[-1].append(line)
        # lines before the first MSH are ignored (headers, blank lines)
    return ["\n".join(c) for c in chunks if any(x.strip() for x in c)]


def iter_messages(
    path: str,
    extensions: tuple[str, ...] = (".hl7", ".txt", ".dat"),
) -> Iterator[tuple[Message | None, str]]:
    """Yield (message, source_file) for each message under ``path``.

    ``message`` is None when a chunk fails to parse, so callers can count
    skips. ``path`` may be a single file or a directory (walked recursively).
    """
    files: list[str] = []
    if os.path.isdir(path):
        for root, _dirs, names in os.walk(path):
            for name in names:
                if name.lower().endswith(extensions):
                    files.append(os.path.join(root, name))
    else:
        files.append(path)

    for fp in sorted(files):
        try:
            with open(fp, "r", encoding="utf-8", errors="replace") as fh:
                blob = fh.read()
        except OSError:
            continue
        for chunk in _split_batch(blob):
            try:
                msg = parse_message(chunk)
                # sanity: must have at least an MSH
                if not msg.segment("MSH"):
                    yield None, fp
                    continue
                yield msg, fp
            except Exception:
                yield None, fp


def load(
    path: str,
    extensions: tuple[str, ...] = (".hl7", ".txt", ".dat"),
) -> LoadResult:
    """Eager load: returns all parsed messages plus skip/file counts."""
    messages: list[Message] = []
    skipped = 0
    seen_files: set[str] = set()
    for msg, fp in iter_messages(path, extensions):
        seen_files.add(fp)
        if msg is None:
            skipped += 1
        else:
            messages.append(msg)
    return LoadResult(messages=messages, skipped=skipped, files_read=len(seen_files))
