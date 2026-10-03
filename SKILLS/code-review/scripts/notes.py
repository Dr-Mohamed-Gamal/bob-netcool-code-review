#!/usr/bin/env python3
"""Read a notes file: the part of a report that a person writes.

The reports that hold one row per item (a review report, a change log, the
report of a change, a traceability map) are written by the scripts. What
only a reader of the code can say goes into a small notes file next to the
report, and the script that writes the report merges it in. This module
reads that file.

A notes file is Markdown with these parts, all optional:

    ## Decisions                    (review)
    - S-12, line 40 — ...
      Decision: not a defect: the reason      or: finding   or: owner: the question
    S-13: finding                   the short form

    ## Findings from reading        (review)
    ### line 804                    or: ### lines 10-12, ### rules.js: 804
    severity: High
    code: a few words that are on that line
    what: ...
    fix: ...
    confidence: ...

    ## Corrections                  (fix, change)
    ### line 804                    the new line(s) under "after:", or "remove: yes"
    ### after line 804              new lines under "insert:"
    ### rule prefix-logs            "match:" a regex, "with:" its replacement, "lines:" a range
    ### copy sw1 as sw2             "lines:" the block to copy, "replace:" lines "old -> new", "keep:", "except:"
    kind: ... / why: ...

    ## Files                        (a split)
    ### folder/new-file.ext
    lines: 1-57, 3100-3338          ranges of the earlier code, in the order wanted
    prepend: / append:              new lines, in a fenced block

    ## Renames
    old_name -> newName             one per line, or a table with two columns

    ## Coverage of the intent       requirement | what was found
    ## Effect                       column: <name>, then <kind of finding>: <text>
    ## Verdict, ## Lines read, ## Questions for the owner, ## Not checked,
    ## Left for the owner, ## Explanations

Text inside <!-- --> is guidance for the writer and is not read.
Python standard library only.
"""
import re
from pathlib import Path

SECTIONS = (("decisions", ("decision",)), ("findings", ("findings from reading", "reading", "finding")),
            ("corrections", ("correction", "edits", "changes")), ("files", ("files", "new files", "split")),
            ("renames", ("rename",)), ("coverage", ("coverage of the intent", "intent", "requirement")),
            ("effect", ("effect",)), ("verdict", ("verdict",)), ("lines_read", ("lines read", "coverage of the code")),
            ("questions", ("question",)), ("not_checked", ("not checked",)), ("left", ("left for the owner", "left")),
            ("explanations", ("explanation", "notes and assumptions", "assumption")))
LINES = re.compile(r"^#{3,4}\s*(?:(?P<file>[^:#]+?\.[A-Za-z0-9]+)\s*:\s*)?(?:lines?\s*)?(?P<a>\d+)(?:\s*(?:-|–|to)\s*(?P<b>\d+))?\s*$",
                   re.I)
SEVERAL = re.compile(r"^#{3,4}\s*(?:(?P<file>[^:#]+?\.[A-Za-z0-9]+)\s*:\s*)?lines?\s+(?P<list>\d[\d\s,;–-]*[,;][\d\s,;–-]*)$", re.I)
INSERT = re.compile(r"^#{3,4}\s*(?:(?P<file>[^:#]+?\.[A-Za-z0-9]+)\s*:\s*)?after\s+line\s+(?P<a>\d+)\s*$", re.I)
RULE = re.compile(r"^#{3,4}\s*rule\s*:?\s*(?P<name>.+?)\s*$", re.I)
COPY = re.compile(r"^#{3,4}\s*copy\s+`?(?P<old>[^`\s]+)`?\s+as\s+`?(?P<new>[^`\s]+)`?\s*$", re.I)
FILE = re.compile(r"^#{3,4}\s*(?:file\s*:?\s*)?`?(?P<path>[^`\s]+\.[A-Za-z0-9]+)`?\s*$", re.I)
KEY = re.compile(r"^([A-Za-z][A-Za-z ]{1,24}?)\s*:\s?(.*)$")
ROW_ID = re.compile(r"^\s*(?:[-*]\s*)?\**([A-Z]-\d+)\**(.*)$")
DECISION_KEY = re.compile(r"^\s*(?:[-*]\s*)?\**decision\**\s*[:=]\s*(.*)$", re.I)
NAME = re.compile(r"^[@$%]?[A-Za-z_]\w*$")
FILLER = ("?", "...", "…", "none yet", "tbd")
BLOCK_KEYS = ("severity", "code", "kind", "what", "fix", "confidence", "after", "why", "effect", "owner", "remove",
              "insert", "match", "with", "lines", "prepend", "append", "for", "replace", "keep", "except")
MANY_LINES = ("after", "insert", "prepend", "append", "replace")      # values that are lines of code, kept as written


def notes_path(report):
    """The notes file that belongs to a report: reports/register.md -> reports/register.notes.md"""
    report = Path(report)
    return report.with_name(report.stem + ".notes.md")


def decision(text):
    """(kind, text) of a decision as written: finding, not, owner, open, or unknown."""
    t = text.strip().strip("*_` ").strip()
    low = t.lower().rstrip(".")
    if not low or low in FILLER:
        return "open", ""
    tail = lambda words: t[len(words):].lstrip(" :—–-=,.").strip()
    for words in ("finding, to be confirmed by the owner", "to be confirmed by the owner", "for the owner",
                  "owner", "question"):
        if low.startswith(words):
            return "owner", tail(words)
    for words in ("not a defect", "not-a-defect", "no defect", "not defect", "false positive"):
        if low.startswith(words):
            return "not", tail(words)
    for words in ("finding", "defect", "confirmed"):
        if low.startswith(words):
            return "finding", tail(words)
    return "unknown", t


def ranges(text):
    """'1-57, 60, 3100-3338' -> [(1, 57), (60, 60), (3100, 3338)]; None when the text is not ranges."""
    out = []
    for part in re.split(r"[,;]\s*|\s+and\s+", text.strip()):
        part = part.strip().replace("lines", "").replace("line", "").strip()
        if not part:
            continue
        m = re.match(r"^(\d+)(?:\s*(?:-|–|to)\s*(\d+))?$", part)
        if not m:
            return None
        a, b = int(m.group(1)), int(m.group(2) or m.group(1))
        out.append((min(a, b), max(a, b)))
    return out


def read(path):
    """The content of a notes file, part by part. A file that does not exist reads as empty notes."""
    out = {"exists": False, "decisions": {}, "findings": [], "corrections": [], "rules": [], "files": [], "copies": [],
           "renames": {}, "accept_proposals": False, "none_found": False, "coverage": [], "effect_column": "", "effects": {}, "verdict": "",
           "lines_read": "", "questions": [], "not_checked": [], "left": [], "explanations": "", "problems": []}
    path = Path(path)
    if not path.is_file():
        return out
    out["exists"] = True
    text = path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
    # guidance is not content: blank it, keeping the line numbers. A block written inside the guidance by
    # mistake would be lost without a word, so it is reported (the examples of the templates use line 120).
    for m in re.finditer(r"<!--.*?-->", text, flags=re.S):
        first = text.count("\n", 0, m.start()) + 1
        for k, line in enumerate(m.group(0).split("\n")):
            head = LINES.match(line.strip()) or INSERT.match(line.strip())
            if head and not 120 <= int(head.group("a")) <= 124:
                out["problems"].append("line %d of the notes is inside the guidance (between <!-- and -->), which is "
                                       "not read: move the block below the guidance: %s" % (first + k, line.strip()[:60]))
            elif re.match(r"^\s*(?:[-*]\s*)?\**decision\**\s*[:=]\s*(?!\?)\S", line, re.I):
                out["problems"].append("line %d of the notes is inside the guidance (between <!-- and -->), which is "
                                       "not read: move the decision below the guidance." % (first + k))
    text = re.sub(r"<!--.*?-->", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
    section, current_id, block, key, fence = None, None, None, None, None
    free = {"verdict": [], "lines_read": [], "explanations": []}

    def close_block():
        if block is None:
            return
        for k in list(block):
            if isinstance(block[k], str):
                block[k] = block[k].strip()
        for k in MANY_LINES:                      # lines of code: without their common indentation
            if k + "_lines" in block:
                lines = block.pop(k + "_lines")
                while lines and not lines[0].strip():
                    lines.pop(0)
                while lines and not lines[-1].strip():
                    lines.pop()
                if len(lines) == 1:
                    lines = [re.sub(r"^`(.*)`$", r"\1", lines[0].strip())]
                indent = min((len(l) - len(l.lstrip()) for l in lines if l.strip()), default=0)
                block[k] = [l[indent:].rstrip() for l in lines]
        {"findings": out["findings"], "rule": out["rules"], "file": out["files"], "copy": out["copies"]}.get(
            block["section"] if block["section"] == "findings" else block["type"], out["corrections"]).append(block)

    for n, line in enumerate(text.split("\n"), 1):
        if fence is not None:                     # inside a fenced block: the lines are kept as written
            if line.strip().startswith("```"):
                if block is not None and key in MANY_LINES:
                    block[key + "_lines"] = block.get(key + "_lines", []) + fence
                elif block is not None and key:
                    block[key] = (block[key] + " " + " ".join(l.strip() for l in fence)).strip()
                fence = None
            else:
                fence.append(line)
            continue
        m = re.match(r"^##\s+(.*)$", line)
        if m and not line.startswith("###"):
            close_block()
            block, key, current_id = None, None, None
            title = m.group(1).strip().lower()
            section = next((name for name, words in SECTIONS if any(title.startswith(w) or w in title for w in words)), None)
            continue
        if section in ("findings", "corrections", "files"):
            header = None
            if section == "files":
                m = FILE.match(line.strip())
                if m:
                    header = {"type": "file", "path": m.group("path").strip()}
            else:
                m = INSERT.match(line.strip())
                if m:
                    header = {"type": "insert", "file": (m.group("file") or "").strip() or None,
                              "first": int(m.group("a")), "last": int(m.group("a"))}
                else:
                    m = RULE.match(line.strip())
                    copy = COPY.match(line.strip())
                    if copy and section == "corrections":
                        header = {"type": "copy", "old": copy.group("old"), "new": copy.group("new")}
                    elif m and section == "corrections":
                        header = {"type": "rule", "name": m.group("name")}
                    else:
                        m = LINES.match(line.strip())
                        several = SEVERAL.match(line.strip())
                        if m:
                            a, b = int(m.group("a")), int(m.group("b") or m.group("a"))
                            header = {"type": "lines", "file": (m.group("file") or "").strip() or None,
                                      "first": min(a, b), "last": max(a, b)}
                        elif several and ranges(several.group("list")):
                            parts = ranges(several.group("list"))     # "### lines 178, 184, 189-190": to remove
                            header = {"type": "lines", "file": (several.group("file") or "").strip() or None,
                                      "first": parts[0][0], "last": parts[0][1], "parts": parts}
            if header:
                close_block()
                block = dict(header, section=section, at=n)
                key = None
                continue
            if line.strip().startswith("```") and block is not None and key:
                fence = []
                continue
            if block is None:
                if line.strip().lower().strip(".*_ ") in ("none", "none found", "nothing found", "no findings"):
                    out["none_found"] = True
                elif line.strip() and not line.startswith("#"):
                    out["problems"].append("line %d of the notes is not inside a block that starts with \"### line "
                                           "<number>\" (or \"### rule <name>\", \"### <file>\"): %s" % (n, line.strip()[:80]))
                continue
            m = KEY.match(line) if not line.startswith((" ", "\t")) else None
            if m and m.group(1).strip().lower() in BLOCK_KEYS:
                key = m.group(1).strip().lower()
                if key in MANY_LINES:
                    block[key + "_lines"] = [m.group(2)] if m.group(2).strip() else []
                    block[key] = []
                else:
                    block[key] = m.group(2)
            elif not line.strip():
                key = key if key in MANY_LINES else None      # an empty line ends a value, except lines of code
            elif key in MANY_LINES:
                block[key + "_lines"].append(line)
            elif key:
                block[key] = block[key] + " " + line.strip()
            else:
                out["problems"].append("line %d of the notes is not understood (a value starts with its name and "
                                       "a colon, for example \"what: ...\"): %s" % (n, line.strip()[:80]))
            continue
        if section == "decisions":
            d = DECISION_KEY.match(line)
            m = ROW_ID.match(line)
            if d and current_id:
                out["decisions"][current_id] = decision(d.group(1)) + (n,)
            elif m:
                current_id = m.group(1)
                short = re.match(r"^\s*(?:,?\s*lines?\s*[\d, -]+?)?\s*[:=]\s*(.+)$", m.group(2))
                if short:
                    out["decisions"][current_id] = decision(short.group(1)) + (n,)
            continue
        if not line.strip():
            continue
        if section == "renames":
            if re.match(r"^\W*(accept|use|apply|take)\b.*propos", line.strip(), re.I):
                out["accept_proposals"] = True
                continue
            cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")] if line.strip().startswith("|") \
                else [c.strip().strip("`") for c in re.split(r"\s*(?:->|=>|→)\s*", line.strip())]
            if len(cells) >= 2 and NAME.match(cells[0]) and NAME.match(cells[1]) and cells[0] != cells[1]:
                out["renames"][cells[0]] = cells[1]
            elif not set(line.strip()) <= set("|-: ") and not re.match(r"^\|?\s*(old|from|earlier)\b", line.strip(), re.I):
                out["problems"].append("line %d of the notes, under the renames, is not \"old -> new\" with two names: %s"
                                       % (n, line.strip()[:80]))
        elif section == "coverage":
            if set(line.strip()) <= set("|-: "):
                continue
            cells = [c.strip() for c in re.split(r"(?<!\\)\|", line.strip().strip("|"))]
            if len(cells) >= 2 and cells[0] and cells[0].lower() not in ("requirement", "requirements"):
                out["coverage"].append((cells[0], " | ".join(c for c in cells[1:] if c)))
            elif len(cells) < 2:
                out["problems"].append("line %d of the notes, under the coverage of the intent, has no \" | \" "
                                       "between the requirement and what was found: %s" % (n, line.strip()[:80]))
        elif section == "effect":
            m = re.match(r"^\s*[-*]?\s*(.+?)\s*:\s*(.*)$", line)
            if m and m.group(1).strip().lower() == "column":
                out["effect_column"] = m.group(2).strip()
            elif m and m.group(2).strip():
                out["effects"][m.group(1).strip().strip("`*").lower()] = m.group(2).strip()
        elif section in ("questions", "not_checked", "left"):
            item = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", line).strip()
            if item and item.lower().rstrip(".") not in FILLER + ("none",):
                out[section].append(item)
        elif section in free:
            free[section].append(line.strip())
    close_block()
    out["verdict"] = " ".join(free["verdict"]).strip()
    out["lines_read"] = " ".join(free["lines_read"]).strip()
    out["explanations"] = "\n".join(free["explanations"]).strip()
    return out
