#!/usr/bin/env python3
"""Write a corrected copy of some code and its change log, and say whether the fix is complete.

    python3 fix_code.py <code file-or-folder> --out <folder> --log <change-log.md>
                        [--register <review report>]

The copy and the change log are written by this script every time it runs,
from three sources:

  1. the scan: the corrections that have only one possible form
       - a single = inside a condition              -> the comparison operator ==
       - an entity without its closing ;            -> the ; added
       - a tag written twice instead of closed      -> the second one closed
       - a ; straight after a condition             -> the ; removed
       - a name read, or given a value, without its prefix -> the prefix added
       - a name that is another name written with a different letter case or
         with two letters swapped, the read half of a misspelt pair, or a name
         that a list of names next to the code does not hold -> that name
  2. the notes file next to the change log (<log>.notes.md), written by the
     person who fixes: one block for each correction of their own, with the
     new line or lines, the kind of defect and why the new form is right
  3. with --register, the review report: its findings are listed with what
     was done about each, and a High finding that is neither corrected nor
     left to the owner in the notes keeps the fix incomplete.

Nobody edits the copy or the change log: a correction goes into the notes,
and this script is run again. The original is never changed. The copy keeps
the encoding and the line endings of the original, byte for byte, outside
the corrected lines.

It ends with a line that starts with "Gate:". Exit code 0 when the fix is
complete, 3 when it is not complete yet, anything else when the script
itself failed. Python standard library only.
"""
import argparse
import hashlib
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import notes as notes_file  # noqa: E402
import report_rows  # noqa: E402
import scan_code  # noqa: E402

NOT_PASSED = 3
TITLE = "# Change log"
# what a correction of the script changes when the code runs, by kind
NOW = {"cond": "The condition now compares instead of assigning: the branch runs only when the two are equal, and the "
               "value on the left is no longer overwritten. What the single = did before needs a test.",
       "entity": "The entity is now well formed.",
       "tag": "The tag is now closed, so the markup is well formed.",
       "prefix": "The value read is now the one of the prefixed name, where an unset name was read before.",
       "prefix_set": "The value now goes to the prefixed name, which the code reads.",
       "rename": "The name now read is one that the code sets.",
       "quote": "The word is now text, as in the other places where the code writes it; before, an unset name was read.",
       "semi": "The block now depends on the condition; before, it ran every time."}
HEAD = re.compile(r"^\s*\}?\s*(if|else\s*if|elseif|elsif|elif|while|until|unless)\b", re.I)
KINDS = {"cond": "Assignment in a condition", "entity": "Entity without its closing ;",
         "tag": "Tag not closed", "prefix": "Name read without its prefix",
         "prefix_set": "Name given a value without its prefix",
         "rename": "Name misspelt or in the wrong letter case",
         "quote": "Text written without its quotes",
         "semi": "Condition followed by ;"}
SUM = re.compile(r"<!-- checksum of the copy: (.*?) -->")
# which corrections of the script close a finding of which kind: a correction of another kind on the
# same line corrects something else, and a finding from reading is closed only by a correction of the notes
COVERS = {"Assignment in a condition": {"cond"}, "Entity without its closing ;": {"entity"},
          "Tag opened and closed a different number of times": {"tag"}, "Name read, never assigned": {"prefix", "rename", "quote"},
          "Name not in the list of names": {"rename"}, "Name used once, close to another name": {"rename"},
          "Name assigned, never read": {"prefix_set"}, "Condition followed by ;": {"semi"}}


def cell(text):
    return "`%s`" % text.strip().replace("|", "\\|").replace("`", "'")


def plain(text):
    return text.replace("|", "\\|").replace("\n", " ")


def short(text, width=150):
    text = " ".join(text.split())
    return text if len(text) <= width else text[:width - 3] + "..."


def numbers(text):
    """The line numbers a cell cites, ranges of up to 50 lines included."""
    found = set()
    for a, b in re.findall(r"(?<![\w.])(\d{1,7})\s*(?:-|–|to)\s*(\d{1,7})(?![\w.])", text):
        if 0 < int(b) - int(a) <= 50:
            found.update(range(int(a), int(b) + 1))
    found.update(int(x) for x in re.findall(r"(?<![\w.])(\d{1,7})(?![\w.])", text))
    return found


def findings_of(path):
    """The findings of a review report: [{id, severity, where, lines, kind, fix, decision, question}]."""
    out = []
    if not path:
        return out
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    asked = {}
    section = re.search(r"^## Questions for the owner.*?\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    for line in (section.group(1).split("\n") if section else []):
        item = re.sub(r"^\d+\.\s*", "", line).strip()
        head = item.split(":")[0]
        ids = re.findall(r"\b([A-Z]-\d+)\b", head)
        if ids and re.match(r"^[A-Z]-\d+(,\s*[A-Z]-\d+)*\s*\(lines?[^)]*\)$", head.strip()):
            item = item.split(":", 1)[1].strip()          # "S-61, S-62 (lines 3137, 3138): question"
        for row_id in ids:
            asked[row_id] = item
    for _, c, cols in report_rows.rows(text.split("\n")):
        if "kind" not in cols or cols["kind"] >= len(c):
            continue
        cited = c[cols["line"]]
        fname = re.match(r"^\s*([^:|]+?\.[A-Za-z0-9]+)\s*:", cited)
        out.append({"id": c[cols["id"]], "severity": c[cols["severity"]] if "severity" in cols else "",
                    "where": cited, "file": fname.group(1).strip() if fname else None,
                    "lines": numbers(cited[fname.end():] if fname else cited), "kind": c[cols["kind"]].replace("\\|", "|"),
                    "code": c[cols["code"]].replace("\\|", "|").strip("`") if "code" in cols and cols["code"] < len(c) else "",
                    "fix": c[cols["fix"]].replace("\\|", "|") if "fix" in cols else "",
                    "decision": c[cols["decision"]] if "decision" in cols and cols["decision"] < len(c) else "Finding",
                    "question": asked.get(c[cols["id"]], "")})
    return out


def replaces_value(name, old, new, style):
    """True when new code drops a name without keeping the word: not as text, not with its prefix, not respelt."""
    bare = name.lstrip("@$%")
    old_names = {t.sigil + t.val for t in scan_code.lex(old, style) if t.kind == "NAME"}
    for t in scan_code.lex(new, style):
        if t.kind == "STR" and bare in t.val:
            return False                         # the word is now text
        if t.kind == "NAME" and (t.val == bare or (t.sigil + t.val not in old_names and scan_code.near(bare, t.val))):
            return False                         # still read, given its prefix, or its spelling corrected
    return True


AS_WRITTEN = "What should the code do there?"     # the question of the script where it cannot say what the choice is


def default_question(r):
    """The question that leaves a finding to the owner as it stands."""
    m = re.match(r"Name read, never assigned: ([@$%]?[A-Za-z_]\w*)", r["kind"])
    if m:
        return "Nothing in this code sets %s, which line %s reads. Which value is meant there?" % (m.group(1), r["where"])
    return "%s (line %s). %s" % (short(r["kind"].split(" — ")[0], 110), r["where"], AS_WRITTEN)


def skeleton(log, command, todo, rest, owner):
    """The notes file as it is first written: the form of a correction, and the findings that are still open."""
    md = ["# Notes for the change log %s" % log.name, "",
          "Your corrections go in this file. The corrected copy and the change log are written by the script from",
          "the code and from these notes: do not edit them. After you change this file, run the command again:", "",
          "    %s" % command, "",
          "## Corrections",
          "<!-- One block for each correction you make yourself. The line numbers are those of the ORIGINAL code.",
          "",
          "### line 120",
          "kind: the kind of defect it corrects",
          "after: the line as it should read",
          "why: why this is the correct form, with a worked example: one input, what the code produced before,",
          "     what it produces now",
          "for: R-04            (only when the correction closes a finding that is on another line: its ID)",
          "",
          "     Several new lines go in a fenced block (three backticks) under \"after:\": under \"### line 120\" they",
          "     replace that one line, under \"### lines 120-124\" they replace those lines. To take lines out, write",
          "     \"remove: yes\" instead of \"after:\". The script keeps the indentation and the line endings of the",
          "     original, and replaces its own correction on a line your block covers.",
          "     To comment on a correction the script made, beyond what the change log already says about it, write a",
          "     block for its line with \"effect:\" and no \"after:\".",
          "     Correct only what the code and the requirement show to be the right form. Do not put in a value they",
          "     do not show to be the right one: another variable, an empty text, a default, a grouping of conditions.",
          "     A block with \"after:\" and \"owner: <question>\" is a proposal: it is listed for the owner and NOT applied.",
          "     On a block with \"effect:\" only, \"owner:\" asks the owner to confirm what the script's correction does.",
          "     Do not repeat these questions under \"Questions for the owner\".",
          "     A correction that adds a call, an operator or a keyword the code did not use before is listed by the",
          "     gate: prefer what the code already uses; if it is needed, name it in \"why:\" the way the gate shows it",
          "     (a call as `name 6 -> 7` or in backticks, an operator in backticks) and say that it needs a test. -->", "",
          "## Left for the owner",
          "<!-- One line for each finding you do not correct because the choice is the owner's. Start with its ID,",
          "     then a colon, then only the question (the script adds the line):",
          "       S-12: <the question> -->", ""]
    if todo:
        md += ["<!-- The findings below are rated High and have no single correct form, so they are left to the owner",
               "     as they stand. Correct one (a block under \"Corrections\") only when the code or the requirement",
               "     shows the right form; then delete its line here. A line that still ends with \"%s\"" % AS_WRITTEN,
               "     is not finished: read the code there, then correct it or write what the owner has to choose between. -->"]
        for r in todo:
            md.append("%s: %s" % (r["id"], default_question(r)))
            if r.get("code"):
                md.append("<!--   line %s: %s -->" % (r["where"], short(r["code"].replace("--", "- -"), 170)))
        md += [""]
    if rest:
        md += ["<!-- Other findings the script did not correct (a correction is welcome where the form is clear; findings",
               "     about unused code, repeated code and performance belong to a later change of the code):"]
        md += ["       %s  line %s  %s" % (r["id"], r["where"], short(r["kind"], 110)) for r in rest[:60]]
        if len(rest) > 60:
            md.append("       ... and %d more, in the change log" % (len(rest) - 60))
        md += ["-->", ""]
    if owner:
        md += ["<!-- Already with the owner, from the review (nothing to do): %s -->" % ", ".join(r["id"] for r in owner), ""]
    md += ["## Verdict",
           "<!-- Optional: one or two sentences. The counts are added by the script. -->", "",
           "## Questions for the owner",
           "<!-- One per line. -->", "",
           "## Not checked",
           "<!-- One per line. -->", ""]
    return "\n".join(md)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("code")
    ap.add_argument("--out", required=True, help="folder for the corrected copy")
    ap.add_argument("--log", required=True, help="the change log to write (Markdown)")
    ap.add_argument("--register", help="the review report: its findings are accounted for in the change log")
    ap.add_argument("--notes", help="the notes file (default: next to the change log, <log>.notes.md)")
    ap.add_argument("--command", help="the command to show in the notes file as the one to run again")
    ap.add_argument("--force", action="store_true", help="replace a file at --log that is not a change log")
    ap.add_argument("--hash-comments", action="store_true", help="# starts a comment")
    args = ap.parse_args()

    src, out, log = Path(args.code), Path(args.out), Path(args.log)
    if out.resolve() == src.resolve() or out.resolve() == src.resolve().parent and src.is_file():
        raise SystemExit("--out must be a different folder from the one that holds the original")
    earlier = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
    if earlier and not args.force and not earlier.lstrip().startswith(TITLE):
        raise SystemExit("%s exists and is not a change log written by this script. Name another file, or pass "
                         "--force to replace it." % log)
    notes_at = Path(args.notes) if args.notes else notes_file.notes_path(log)
    command = args.command or "python3 %s %s --out %s --log %s%s" % (
        sys.argv[0], args.code, args.out, args.log, " --register %s" % args.register if args.register else "")

    scan, files = scan_code.run([src], args.hash_comments)
    notes = notes_file.read(notes_at)
    first_run = not notes["exists"]
    problems = list(notes["problems"])
    by_name = {f.name: str(f) for f in files}
    targets = {str(f): out / (f.name if src.is_file() else f.relative_to(src)) for f in files}

    # ---- the corrections of the notes, file by file: {first line: (last line, new lines, block)}
    blocks, remarks = defaultdict(dict), defaultdict(dict)
    proposals = []                               # corrections that decide what is the owner's to decide: listed, not applied
    findings = findings_of(args.register)
    for b in notes["corrections"]:
        label = "the correction for line %d (line %d of the notes)" % (b["first"], b["at"])
        name = by_name.get(Path(b["file"]).name) if b["file"] else (str(files[0]) if len(files) == 1 else None)
        if name is None:
            problems.append("%s: say which file, as in \"### rules.js: %d\"." % (label, b["first"]))
            continue
        if not 0 < b["first"] <= b["last"] <= len(scan.lines[name]):
            problems.append("%s: %s has %d lines." % (label, Path(name).name, len(scan.lines[name])))
            continue
        removes = (b.get("remove") or "").strip().lower().startswith(("y", "t"))
        new = [l for l in b.get("after", [])] if isinstance(b.get("after"), list) else []
        if not new and not removes:
            if b.get("effect") or b.get("owner"):
                remarks[name][b["first"]] = b            # a remark on a correction, not a correction
            else:
                problems.append("%s: \"after:\" is missing. Give the new line, or \"remove: yes\", or an "
                                "\"effect:\" if this is a remark on a correction the script made." % label)
            continue
        if len((b.get("why") or "")) < 15:
            problems.append("%s: \"why:\" is missing or too short. Say why the new form is right, with a worked "
                            "example." % label)
            continue
        parts = b.get("parts") or [(b["first"], b["last"])]
        if len(parts) > 1 and not removes:
            problems.append("%s: a list of lines can only be removed (\"remove: yes\"). To replace lines, write one "
                            "block for each run of lines." % label)
            continue
        if any(not 0 < a <= z <= len(scan.lines[name]) for a, z in parts):
            problems.append("%s: %s has %d lines." % (label, Path(name).name, len(scan.lines[name])))
            continue
        if any(first <= z and a <= last for a, z in parts for first, (last, _, _) in blocks[name].items()):
            problems.append("%s: another correction in the notes already covers one of these lines." % label)
            continue
        covered = [r for r in findings if r["decision"].startswith("Finding")
                   and (not r["file"] or by_name.get(Path(r["file"]).name) == name)
                   and any(a <= n <= z for a, z in parts for n in r["lines"])]
        b["reason"] = "its block asks the owner whether it is right" if b.get("owner") else ""
        if not b.get("owner"):                   # the review left the line to the owner: the fix does not decide it
            owned = [r for r in covered if r["decision"] != "Finding" and len(r["lines"]) <= 2]
            if owned:
                b["owner"] = owned[0]["question"] or "The review left this to the owner: %s" % short(owned[0]["kind"], 100)
                b["reason"] = "the review left %s on that line to the owner" % owned[0]["id"]
        if not b.get("owner") and not removes:   # a line that was switched off, switched back on
            old_lines = [l.rstrip("\r") for a, z in parts for l in scan.lines[name][a - 1:z]]
            off = {}
            for l in old_lines:
                s = l.strip()
                for mark in ("//", "#", "--"):
                    if s.startswith(mark) and s[len(mark):].strip():
                        off[re.sub(r"\s+", " ", s[len(mark):].strip())] = s
                        break
            back = [l.strip() for l in new if re.sub(r"\s+", " ", l.strip()) in off]
            if back:
                b["owner"] = ("The line `%s` was switched off in the code (commented out); switching it back on changes "
                              "what the code does. Should it run?" % off[re.sub(r"\s+", " ", back[0])])
                b["reason"] = "it switches back on a line the code has switched off"
        if not b.get("owner") and not removes:   # another value in the place of a name that nothing sets
            old_text = "\n".join(l.rstrip("\r") for a, z in parts for l in scan.lines[name][a - 1:z])
            for r in covered:
                m = re.match(r"Name read, never assigned: ([@$%]?[A-Za-z_]\w*)", r["kind"])
                if m and replaces_value(m.group(1), old_text, "\n".join(new), scan.styles[name]):
                    b["owner"] = "Nothing in the code sets %s. The value proposed in its place is not shown by the code " \
                                 "or the requirement to be the one meant: which value is meant?" % m.group(1)
                    b["reason"] = "it puts another value in the place of %s, which nothing sets" % m.group(1)
                    break
        if b.get("owner"):                       # what the owner has to decide is proposed, not done
            proposals.append((name, parts, [] if removes else new, b))
            continue
        for a, z in parts:
            blocks[name][a] = (z, [] if removes else new, b)

    # ---- "for:" names a finding on another line; a finding whose own line has a correction is not that
    spans = [(name, a, z, b) for name in blocks for a, (z, _, b) in blocks[name].items()] \
        + [(name, a, z, b) for name, parts, _, b in proposals for a, z in parts]
    for name, a, z, b in spans:
        for fid in re.findall(r"\b[A-Z]-\d+\b", b.get("for", "")):
            r = next((r for r in findings if r["id"] == fid), None)
            if r is None or (r["file"] and by_name.get(Path(r["file"]).name) != name) \
                    or any(a <= n <= z for n in r["lines"]):
                continue
            own = [c for c in spans if c[0] == name and c[3] is not b and any(c[1] <= n <= c[2] for n in r["lines"])]
            if own:
                problems.append("the correction for line %d (line %d of the notes): \"for: %s\" names the finding on "
                                "line %s, which has a correction of its own (line %d of the notes). \"for:\" is only "
                                "for a finding on another line that this correction closes: check the ID, or take "
                                "the line out." % (b["first"], b["at"], fid, ", ".join(map(str, sorted(r["lines"]))),
                                                   own[0][3]["at"]))

    # ---- work everything out first; nothing is written before this is done
    content, rows, changed = {}, [], defaultdict(set)      # changed: file -> original lines that were corrected
    closes, replaced = set(), []                 # findings a correction names with "for:"; script corrections it replaced
    by_notes, by_script = defaultdict(set), defaultdict(dict)    # file -> lines; file -> line -> kinds of correction
    kinds_at = defaultdict(set)
    for f, _, _, _, kind, line in scan.fixes:
        kinds_at[(f, line)].add(kind)
    for f in files:
        name = str(f)
        before, base = scan.lines[name], scan.corrected(name).split("\n")
        after, n, copy_line = [], 1, 1
        while n <= len(before):
            if n in blocks[name]:
                last, new, b = blocks[name][n]
                first_line = before[n - 1]
                ending = "\r" if first_line.endswith("\r") else ""
                indent = first_line[:len(first_line) - len(first_line.lstrip())]
                new_lines = [(indent + l if l.strip() else "") + ending for l in new]
                old_lines = before[n - 1:last]
                if [l.rstrip("\r") for l in new_lines] == [l.rstrip("\r") for l in old_lines]:
                    if all(base[k - 1] == before[k - 1] for k in range(n, last + 1)):
                        problems.append("the correction for line %d (line %d of the notes): the new text is the same "
                                        "as the original." % (n, b["at"]))
                    kind = "Correction of the script undone: %s" % (b.get("kind") or "by decision")
                    undone = True
                else:
                    kind, undone = b.get("kind") or ("Line removed" if not new else "Corrected by hand"), False
                why = b.get("why", "")
                if not new:                      # a removal accounts for everything the lines held
                    why = ("%s %s" % (why, scan_code.account_of("\n".join(l.rstrip("\r") for l in old_lines),
                                                               scan.styles[name]))).strip()
                for k in range(max(len(old_lines), len(new_lines))):
                    rows.append({"file": name, "line": n + k if k < len(old_lines) else None,
                                 "copy": copy_line + k if k < len(new_lines) else None, "kind": kind,
                                 "before": old_lines[k] if k < len(old_lines) else None,
                                 "after": new_lines[k] if k < len(new_lines) else None,
                                 "why": why, "by": "notes", "undone": undone, "span": (n, last, b["at"]),
                                 "owner": b.get("owner", ""), "first": k == 0})
                if not undone:
                    changed[name].update(range(n, last + 1))
                    by_notes[name].update(range(n, last + 1))
                    closes.update(re.findall(r"\b[A-Z]-\d+\b", b.get("for", "")))
                    replaced += [k for k in range(n, last + 1) if base[k - 1] != before[k - 1]]
                after += new_lines
                copy_line += len(new_lines)
                n = last + 1
                continue
            if base[n - 1] != before[n - 1]:
                remark = remarks[name].get(n, {})
                now = " ".join(dict.fromkeys(NOW[k] for k in sorted(kinds_at[(name, n)]) if k in NOW))
                if HEAD.match(before[n - 1]) and not kinds_at[(name, n)] & {"cond", "semi"}:
                    now += " The line is a condition: the block below it can now run, or not run, where its outcome was fixed before."
                now = ("%s %s" % (now, scan_code.text_changed(before[n - 1].rstrip("\r"), base[n - 1].rstrip("\r"),
                                                             scan.styles[name]))).strip()
                rows.append({"file": name, "line": n, "copy": copy_line,
                             "kind": ", ".join(KINDS.get(k, k) for k in sorted(kinds_at[(name, n)])),
                             "before": before[n - 1], "after": base[n - 1], "by": "script", "undone": False,
                             "why": (now + (" Reviewer: " + remark["effect"] if remark.get("effect") else "")).strip(),
                             "owner": remark.get("owner", ""), "first": True})
                changed[name].add(n)
                by_script[name][n] = set(kinds_at[(name, n)])
            after.append(base[n - 1])
            copy_line += 1
            n += 1
        for n, b in remarks[name].items():
            if base[n - 1] == before[n - 1] and n not in changed[name]:
                problems.append("the remark for line %d (line %d of the notes): the script made no correction on "
                                "that line. To correct the line yourself, add \"after:\"." % (n, b["at"]))
        try:
            content[name] = "\n".join(after).encode(scan.encoding[name])
        except UnicodeEncodeError as e:
            raise SystemExit("A correction in the notes holds a character that %s cannot hold in its encoding "
                             "(%s): %s" % (Path(name).name, scan.encoding[name], e))

    # ---- the findings of the review: what was done about each
    left_notes = notes["left"]

    def left_for(r):
        for item in left_notes:
            head = item.split(":")[0]
            if r["id"] in re.findall(r"\b[A-Z]-\d+\b", head) or (numbers(re.sub(r"\b[A-Z]-\d+\b", "", head)) & r["lines"]):
                return item.split(":", 1)[1].strip() if ":" in item else item
        return ""

    def corrected(r):
        names = [n for n in ([by_name.get(Path(r["file"]).name)] if r["file"] else list(changed)) if n]
        if r["id"] in closes or any(r["lines"] & by_notes[n] for n in names):
            return True
        wanted = COVERS.get(r["kind"].split(":")[0].strip(), set())
        return any(by_script[n].get(line, set()) & wanted for n in names for line in r["lines"])

    def proposed_for(r):
        """The question of a proposal that covers a finding, with the line proposed."""
        mine = [p for p in proposals if not r["file"] or by_name.get(Path(r["file"]).name) == p[0]]
        on_line = [p for p in mine if any(a <= n <= z for a, z in p[1] for n in r["lines"])]
        named = [p for p in mine if r["id"] in re.findall(r"\b[A-Z]-\d+\b", p[3].get("for", "") + " " + p[3].get("kind", ""))]
        for name, parts, new, b in on_line + named:      # the proposal on the finding's own line comes first
            return "%s Proposed, not applied: %s" % (b["owner"], cell(new[0]) if new else "remove the line")
        return ""

    done, todo, rest, with_owner, as_written = [], [], [], [], []
    for r in findings:
        if not r["decision"].startswith("Finding"):
            continue
        r["left"] = left_for(r) or proposed_for(r)
        if corrected(r):
            done.append(r)
        elif r["decision"] != "Finding" or r["left"]:
            with_owner.append(r)
            if r["left"].rstrip().endswith(AS_WRITTEN):
                as_written.append(r)         # nobody has looked at it yet: the question is the script's own
        elif r["severity"].startswith("High"):
            todo.append(r)
        else:
            rest.append(r)

    # ---- the scan of the copy, for the counts before and after
    for name, target in targets.items():
        target.parent.mkdir(parents=True, exist_ok=True)
    edited = []                                  # the copy was changed by hand since this script wrote it
    recorded = dict(x.split("=", 1) for m in SUM.finditer(earlier) for x in m.group(1).split(" ") if "=" in x)
    for name, target in targets.items():
        if target.exists() and recorded.get(target.name) \
                and hashlib.sha1(target.read_bytes()).hexdigest() != recorded[target.name]:
            edited.append(str(target))
    aside = []
    for name, target in targets.items():
        if str(target) in edited and target.read_bytes() != content[name]:
            keep = log.parent / (log.stem + ".edited-by-hand") / target.name
            keep.parent.mkdir(parents=True, exist_ok=True)
            keep.write_bytes(target.read_bytes())
            aside.append(str(keep))
        target.write_bytes(content[name])
    after_scan, _ = scan_code.run([out if src.is_dir() else targets[str(files[0])]] if files else [out],
                                  args.hash_comments, documents=[Path(d) for d in scan.docs])

    # ---- a correction of the notes must not add a defect: a scan hit on a line it wrote that was not there before
    back = {str(target): name for name, target in targets.items()}
    written = {(r["file"], r["copy"]): r["span"] for r in rows if r["by"] == "notes" and not r["undone"] and r["copy"]}
    subject = lambda note: note.split(" — ")[0].split(" (")[0]
    places = lambda line, note: [int(x) for x in re.search(r"\bon lines? ([\d, ]+)", note).group(1).replace(" ", "").split(",") if x] \
        if re.search(r"\bon lines? ([\d, ]+)", note) else [line]
    told = set()
    for key, title, _ in scan_code.CHECKS:
        for f, line, note in sorted(set(after_scan.hits[key])):
            for n in places(line, note):
                span = written.get((back.get(f), n))
                if not span or (key, span) in told:
                    continue
                a, z, at = span
                was = any(g == back[f] and subject(m) == subject(note) and set(places(l, m)) & set(range(a, z + 1))
                          for g, l, m in scan.hits[key])
                if not was:
                    told.add((key, span))
                    problems.append("the correction for line %d (line %d of the notes) adds a defect that was not there: "
                                    "%s%s. Correct the new line, or take the correction out and leave the finding to the "
                                    "owner with the question." % (a, at, title, " — " + note if note else ""))

    # ---- the change log
    by_script = sum(1 for r in rows if r["by"] == "script")
    by_hand = len({(r["file"], r["line"] or r["copy"]) for r in rows if r["by"] == "notes" and not r["undone"]})
    md = [TITLE, "",
          "Written by the fix script from the code and from the notes in %s. Do not edit this file or the corrected "
          "copy: write in the notes and run the script again." % notes_at.name, "",
          "## Verdict"]
    if notes["verdict"]:
        md += [notes["verdict"], ""]
    md += ["%d line(s) were corrected in a copy (%s); the original is unchanged. %d by the script, as corrections "
           "with one possible form; %d from the notes of the person who fixed. Of the findings of the review, %d "
           "are corrected, %d are left to the owner and %d are left as they are."
           % (by_script + by_hand, out, by_script, by_hand, len(done), len(with_owner), len(todo) + len(rest)), "",
           "## Changes made",
           "| # | File | Line | Line in the copy | Kind | Before | After | Behaviour changes? Worked example |",
           "|---|---|---|---|---|---|---|---|"]
    counter = {"C": 0, "H": 0}
    for r in rows:
        letter = "C" if r["by"] == "script" else "H"
        if r["first"]:
            counter[letter] += 1
        last = r["why"] or ("Yes: this is the correction of the defect." if r["by"] == "script" else "")
        if r["owner"]:
            last += " To be confirmed by the owner: %s" % r["owner"]
        md.append("| %s-%02d | %s | %s | %s | %s | %s | %s | %s |" % (
            letter, counter[letter], targets[r["file"]].name, r["line"] or "", r["copy"] or "", plain(r["kind"]),
            cell(r["before"]) if r["before"] is not None else "(no line)",
            cell(r["after"]) if r["after"] is not None else "(removed)", plain(last) if r["first"] else "As above."))
    md += ["", "## Findings of the review that were not corrected",
           "| ID | Severity | Line | Kind | What was decided |", "|---|---|---|---|---|"]
    for r in with_owner:
        md.append("| %s | %s | %s | %s | For the owner: %s |" % (r["id"], plain(r["severity"]), r["where"], plain(r["kind"]),
                                                                plain(r["left"] or r["question"] or "see the review")))
    for r in todo:
        md.append("| %s | %s | %s | %s | NOT DECIDED: correct it, or leave it to the owner with the question |"
                  % (r["id"], plain(r["severity"]), r["where"], plain(r["kind"])))
    for r in rest:
        md.append("| %s | %s | %s | %s | Left as it is: %s |" % (r["id"], plain(r["severity"]), r["where"], plain(r["kind"]),
                                                               plain(short(r["fix"], 160)) or "no correction with one form"))
    if proposals:
        md += ["", "## Proposed, not applied: for the owner to confirm",
               "| File | Line | As it is | Proposed | Why | Question for the owner |", "|---|---|---|---|---|---|"]
        for name, parts, new, b in proposals:
            a, z = parts[0]
            md.append("| %s | %s | %s | %s | %s | %s |" % (
                targets[name].name, ", ".join("%d" % p if p == q else "%d-%d" % (p, q) for p, q in parts),
                cell(scan.lines[name][a - 1]), "<br>".join(cell(l) for l in new) if new else "(remove)",
                plain(b.get("why", "")), plain(b["owner"])))
    explained = []
    if any(r["by"] == "script" and "cond" in kinds_at[(r["file"], r["line"])] for r in rows):
        explained.append("The script's corrections of a single = in a condition use the comparison operator `==`.")
    if notes["explanations"]:
        explained.append(notes["explanations"])
    if explained:
        md += ["", "## Explanations of the differences the gate lists"] + explained
    md += ["", "## Checks performed", "| Check | How it was checked | Before | After |", "|---|---|---|---|"]
    for key, title, _ in scan_code.CHECKS:
        b, a = len(set(scan.hits[key])), len(set(after_scan.hits[key]))
        if b or a:
            md.append("| %s | scan_code.py, original and copy | %d | %d%s |" % (plain(title), b, a, "  (went up)" if a > b else ""))
    md += ["", "## Not checked", "- Nothing was run. The corrections are changes to the text of the code."]
    md += ["- %s" % x for x in notes["not_checked"]]
    asked = {}                                   # question -> the rows that ask it
    for r in with_owner:
        if r["left"] or r["question"]:
            asked.setdefault(r["left"] or r["question"], []).append(r)
    questions = ["%s (line%s %s): %s" % (", ".join(r["id"] for r in rs), "s" if len(rs) > 1 else "",
                                         ", ".join(r["where"] for r in rs), q) for q, rs in asked.items()]
    questions += ["Line %d: %s" % (r["line"] or r["copy"], r["owner"]) for r in rows if r["owner"] and r["first"]]
    questions += ["Line %d: %s" % (parts[0][0], b["owner"]) for _, parts, _, b in proposals
                  if not any(b["owner"] in q for q in questions)]
    questions += notes["questions"]
    md += ["", "## Questions for the owner of the code"]
    md += ["%d. %s" % (i, q) for i, q in enumerate(dict.fromkeys(questions), 1)] or ["1. None."]
    md += ["", "<!-- checksum of the copy: %s -->" % " ".join(
        "%s=%s" % (targets[n].name, hashlib.sha1(content[n]).hexdigest()) for n in sorted(content)), ""]
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("\n".join(md), encoding="utf-8")
    if first_run:
        notes_at.parent.mkdir(parents=True, exist_ok=True)
        notes_at.write_text(skeleton(log, command, todo, rest, with_owner), encoding="utf-8")

    # ---- say where the fix stands
    print("Corrected copy: %s (written by this command; do not edit it)" % out)
    print("Change log:     %s (written by this command; do not edit it)" % log)
    print("  %d line(s) corrected: %d by the script, %d from your notes." % (by_script + by_hand, by_script, by_hand))
    went_up = ["%s %d -> %d" % (title, len(set(scan.hits[key])), len(set(after_scan.hits[key])))
               for key, title, _ in scan_code.CHECKS if len(set(after_scan.hits[key])) > len(set(scan.hits[key]))]
    if went_up:
        print("  Scan counts that went up in the copy: %s" % "; ".join(went_up))
    if proposals:
        print("  %d correction(s) of your notes are the owner's to decide. They are listed in the change log as "
              "proposals and are NOT applied:" % len(proposals))
        for _, parts, _, b in proposals:
            print("    line %d: %s" % (parts[0][0], b["reason"]))
    if replaced:
        print("  Your notes replace the script's own correction on line%s %s."
              % ("" if len(replaced) == 1 else "s", ", ".join(str(n) for n in replaced)))
    if findings:
        print("  Findings of the review: %d corrected, %d left to the owner, %d left as they are. "
              "(One corrected line can close several findings.)" % (len(done), len(with_owner), len(todo) + len(rest)))
    print("Your notes: %s%s" % (notes_at, " (written now: it shows the form of a correction and lists the findings "
                                "that are still open)" if first_run else ""))
    if aside:
        print("  The copy had been edited by hand since the last run. The copy is written from the notes, so those "
              "edits are not in it; the edited file is kept at %s. Put each edit in the notes as a correction."
              % ", ".join(aside))
    if todo:
        print("  High findings neither corrected nor left to the owner: %d" % len(todo))
        for r in todo[:40]:
            print("    %s  line %s  %s" % (r["id"], r["where"], short(r["kind"], 100)))
    if as_written and not first_run:
        print("  Left to the owner with the question as the script wrote it: %d. Read the code at each one, then correct "
              "it where the code or the requirement shows the right form, or write what the owner has to choose between:"
              % len(as_written))
        for r in as_written[:40]:
            print("    %s  line %s  %s" % (r["id"], r["where"], short(r["kind"], 100)))
    if problems:
        print("To correct in the notes:")
        for p in problems:
            print("  - %s" % p)
    complete = not todo and not problems and not as_written
    if complete:
        print("\nResult: complete")
        sys.exit(0)
    print("\nResult: not complete. %s" % (
        "This is expected on the first run: write your corrections in %s." % notes_at if first_run
        else "Correct what is listed, in %s." % notes_at))
    sys.exit(0 if first_run else NOT_PASSED)


if __name__ == "__main__":
    main()
