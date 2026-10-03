#!/usr/bin/env python3
"""Compare the quoted text of two versions of some code.

    python3 compare_strings.py <before file-or-folder> <after file-or-folder>

Collects every quoted string (single or double quotes) outside comments in
both versions and lists:
  - strings that are in the before version and nowhere in the after version
  - strings that are used fewer times afterwards
  - strings that are new in the after version

Use it when code is rewritten, moved or split across files: user-visible
text, messages, queries and identifiers held in strings should survive
unless a change is meant to alter them. It compares text only; it cannot
tell whether a string is still reached under the same conditions.

Comments are // to end of line and /* ... */. Add --hash-comments for
languages where # starts a comment. Text inside logging and printing calls
is left out, because log wording is usually free to change; add
--include-logging to compare it too. Python standard library only.
"""
import argparse
from collections import Counter, defaultdict
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".bob", ".vscode"}


LOG_CALLS = {"log", "print", "println", "printf", "console.log", "console.error",
             "console.warn", "logger.info", "logger.debug", "logger.warn",
             "logger.warning", "logger.error", "logging.info", "logging.debug",
             "logging.warning", "logging.error", "system.out.println"}


def skip_string(text, i):
    """Index just after the string that starts at i, or i + 1 if it is not one."""
    c, j, n = text[i], i + 1, len(text)
    while j < n and text[j] != c and text[j] != "\n":
        j += 2 if text[j] == "\\" else 1
    return (j + 1, True) if j < n and text[j] == c else (i + 1, False)


def strings_in(text, hash_comments, skip_calls):
    """Yield (line, value) for each quoted string outside comments."""
    i, n, line = 0, len(text), 1
    while i < n:
        c = text[i]
        if c == "\n":
            line += 1
            i += 1
        elif text.startswith("//", i) or (hash_comments and c == "#"):
            j = text.find("\n", i)
            i = n if j < 0 else j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            line += text.count("\n", i, j)
            i = j
        elif c in "\"'":
            j, ok = skip_string(text, i)
            if ok:
                yield line, text[i + 1:j - 1]
            i = j
        elif c.isalpha() or c == "_":
            j = i
            while j < n and (text[j].isalnum() or text[j] in "_."):
                j += 1
            name = text[i:j].lower()
            k = j
            while k < n and text[k] in " \t":
                k += 1
            if name in skip_calls and k < n and text[k] == "(":
                depth = 0
                while k < n:            # skip the whole call, strings included
                    ch = text[k]
                    if ch in "\"'":
                        k, _ = skip_string(text, k)
                        continue
                    if ch == "\n":
                        line += 1
                    elif ch == "(":
                        depth += 1
                    elif ch == ")":
                        depth -= 1
                        if depth == 0:
                            k += 1
                            break
                    k += 1
                i = k
            else:
                i = j
        else:
            i += 1


def collect(target, exts):
    p = Path(target)
    if p.is_file():
        return [p]
    files = []
    for f in sorted(p.rglob("*")):
        if f.is_file() and not (set(f.parts) & SKIP_DIRS) and (not exts or f.suffix in exts):
            files.append(f)
    return files


def gather(files, hash_comments, skip_calls):
    """The strings of the files. `hash_comments` is True or False for all of them, or {file: True or False}."""
    found = defaultdict(list)
    by_file = hash_comments if isinstance(hash_comments, dict) else None
    for f in files:
        if by_file is not None:
            hash_comments = by_file.get(str(f), False)
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line, value in strings_in(text, hash_comments, skip_calls):
            if value.strip():
                found[value].append((f.name, line))
    return found


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("before")
    ap.add_argument("after")
    ap.add_argument("--hash-comments", action="store_true",
                    help="treat # as the start of a comment")
    ap.add_argument("--include-logging", action="store_true",
                    help="also compare text inside logging and printing calls")
    ap.add_argument("--min-length", type=int, default=3,
                    help="ignore strings shorter than this (default 3)")
    args = ap.parse_args()

    before_files = collect(args.before, None)
    exts = {f.suffix for f in before_files}
    after_files = collect(args.after, exts)
    skip_calls = set() if args.include_logging else LOG_CALLS
    old = gather(before_files, args.hash_comments, skip_calls)
    new = gather(after_files, args.hash_comments, skip_calls)
    new_count = Counter({k: len(v) for k, v in new.items()})

    def long_enough(s):
        return len(s.strip()) >= args.min_length

    missing = sorted((v[0][1], k, len(v)) for k, v in old.items()
                     if k not in new and long_enough(k))
    fewer = sorted((v[0][1], k, len(v), new_count[k]) for k, v in old.items()
                   if k in new and new_count[k] < len(v) and long_enough(k))
    added = sorted(k for k in new if k not in old and long_enough(k))

    print("Before: %s (%d file(s), %d distinct strings, %d uses)"
          % (args.before, len(before_files), len(old), sum(len(v) for v in old.values())))
    print("After:  %s (%d file(s), %d distinct strings, %d uses)\n"
          % (args.after, len(after_files), len(new), sum(new_count.values())))
    print("Missing afterwards: %d   used fewer times: %d   new: %d"
          % (len(missing), len(fewer), len(added)))

    def cut(s):
        return s if len(s) <= 110 else s[:107] + "..."

    if missing:
        print("\nMissing afterwards (line in before, times used, text)")
        for line, k, cnt in missing:
            print("  %6d  x%-3d %s" % (line, cnt, cut(k)))
    if fewer:
        print("\nUsed fewer times (line in before, before -> after, text)")
        for line, k, a, b in fewer:
            print("  %6d  %d -> %d  %s" % (line, a, b, cut(k)))
    if added:
        print("\nNew afterwards")
        for k in added:
            where = new[k][0]
            print("  %s:%d  %s" % (where[0], where[1], cut(k)))


if __name__ == "__main__":
    main()
