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
from typing import Iterator, Sequence

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


def collect_files(
    paths: str | Sequence[str],
    extensions: tuple[str, ...] = (".hl7", ".txt", ".dat"),
    recursive: bool = True,
) -> list[str]:
    """Resolve one or more paths to a sorted, de-duplicated file list.

    A directory contributes the files under it matching ``extensions``,
    recursively unless ``recursive`` is False. A path naming a file is taken
    as-is, without an extension check, so an explicitly chosen file is always
    read whatever it is called.

    De-duplication is by real path, so overlapping arguments -- a shell glob
    that repeats a name, or a file also reachable through a directory
    argument -- are counted once rather than inflating every statistic.
    """
    if isinstance(paths, str):
        paths = [paths]

    found: dict[str, None] = {}          # realpath -> None, insertion ordered
    for path in paths:
        if os.path.isdir(path):
            if recursive:
                for root, _dirs, names in os.walk(path):
                    for name in names:
                        if name.lower().endswith(extensions):
                            found[os.path.realpath(os.path.join(root, name))] = None
            else:
                for name in sorted(os.listdir(path)):
                    fp = os.path.join(path, name)
                    if os.path.isfile(fp) and name.lower().endswith(extensions):
                        found[os.path.realpath(fp)] = None
        else:
            found[os.path.realpath(path)] = None
    return sorted(found)


def iter_messages(
    paths: str | Sequence[str],
    extensions: tuple[str, ...] = (".hl7", ".txt", ".dat"),
    recursive: bool = True,
) -> Iterator[tuple[Message | None, str]]:
    """Yield (message, source_file) for each message under ``paths``.

    ``message`` is None when a chunk fails to parse, so callers can count
    skips. ``paths`` may be a single path or several, each a file or a
    directory.
    """
    for fp in collect_files(paths, extensions, recursive):
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
    paths: str | Sequence[str],
    extensions: tuple[str, ...] = (".hl7", ".txt", ".dat"),
    recursive: bool = True,
) -> LoadResult:
    """Eager load: returns all parsed messages plus skip/file counts."""
    messages: list[Message] = []
    skipped = 0
    seen_files: set[str] = set()
    for msg, fp in iter_messages(paths, extensions, recursive):
        seen_files.add(fp)
        if msg is None:
            skipped += 1
        else:
            messages.append(msg)
    return LoadResult(messages=messages, skipped=skipped, files_read=len(seen_files))
