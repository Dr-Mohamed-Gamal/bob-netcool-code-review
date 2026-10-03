#!/usr/bin/env python3
"""Show where each line of some code went after it was moved, split or renamed.

    python3 trace_code.py <before file-or-folder> <after file-or-folder>
                          [--out <map.md>] [--renames <file>]

Takes every line of code of the earlier version and looks for it in the
later version, in three passes:

  1. in order: the longest sequence of lines that are the same in both, so
     that a line that did not move is paired with itself
  2. anywhere: the same text somewhere else, for code that moved. Text is
     compared without spaces, letter case, underscores and comments, so a
     line still matches after re-indenting and after a rename between naming
     styles (order_total, orderTotal, ORDER_TOTAL)
  3. the same line with other names: the variables may differ, but the
     calls, the prefixed names, the text in strings and the operators are
     the same. Only lines that hold a call, a prefixed name or a string are
     matched this way.

With --renames, a file that lists the names that were changed (one
"old -> new" per line, or a table with two columns), each old name is
replaced by its new one before the first pass, where it is used as a name:
not inside strings and not after a dot.

Prints the counts, the earlier lines now in each later file, and the code
that has no counterpart, as runs of consecutive lines. Each run is marked:
rewritten (an earlier run and a later run in the same place), logging (only
logging calls), removed or added. With --out, writes the same as a Markdown
report, the traceability map of a restructuring. A map that is written
again keeps what was filled in by hand.

A line that is found has the same text; whether it still runs under the
same conditions has to be read. Python standard library only.
"""
import argparse
import difflib
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import scan_code  # noqa: E402

NAME = re.compile(r"^[@$%]?[A-Za-z_]\w*$")
LOG_LINE = re.compile(r"\s*(?:\w+\s*\.\s*)*(?:%s)\s*\(" % "|".join(sorted(scan_code.LOG_CALLS)), re.I)


def load_renames(path):
    """Read a list of changed names: 'old -> new' lines, or the first two cells of table rows."""
    names = {}
    if not path:
        return names
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    m = re.search(r"^## Renames.*?\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    if m:                                        # a notes file or a report: only its renames section counts
        text = m.group(1)
    for line in text.split("\n"):
        line = line.replace("`", "").strip()
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
        else:
            cells = [c.strip() for c in re.split(r"\s*(?:->|=>|→)\s*", line)]
        if len(cells) >= 2 and NAME.match(cells[0]) and NAME.match(cells[1]) and cells[0] != cells[1]:
            names[cells[0]] = cells[1]
    return names


def rename_names(body, style, renames):
    """Put the new name where an old one is used as a name: not inside a string, not after a dot."""
    if not renames:
        return body
    toks = scan_code.lex(body, style)
    for i in range(len(toks) - 1, -1, -1):
        t = toks[i]
        key = t.sigil + t.val if t.kind == "NAME" else None
        if key in renames and not (i and scan_code.is_op(toks[i - 1], ".", "->", "::")):
            body = body[:t.pos] + renames[key] + body[t.pos + len(key):]
    return body


def shape(body, style):
    """The line with its plain variable names left out, or '' when too little is left to match on."""
    toks = scan_code.lex(body, style)
    parts, anchors = [], 0
    for i, t in enumerate(toks):
        nxt = toks[i + 1] if i + 1 < len(toks) else None
        if t.kind == "NAME" and t.sigil:
            parts.append(t.sigil + t.val.lower())
            anchors += 1
        elif t.kind == "NAME":
            if scan_code.is_op(nxt, "(") and t.val.lower() not in scan_code.CONTROL_WORDS:
                parts.append(t.val.lower())
                anchors += 1
            else:
                parts.append(t.val.lower() if t.val.lower() in scan_code.KEYWORDS else "#")
        elif t.kind == "STR":
            parts.append("'%s'" % t.val)
            anchors += len(t.val.strip()) >= 3
        else:
            parts.append(t.val)
    return " ".join(parts) if anchors and len(parts) >= 3 else ""


def code_lines(target, hash_comments, renames=None):
    """[(file name, line number, text, key, shape)] for every line that holds code."""
    out = []
    for f in scan_code.collect([target]):
        try:
            raw = f.read_bytes()
        except OSError:
            continue
        if b"\0" in raw[:8192]:
            continue
        text = raw.decode("utf-8", errors="replace")
        style = scan_code.style_for(f, hash_comments, text)
        marks = [m for m, on in (("//", style in ("slash", "both")), ("#", style in ("hash", "both")),
                                 ("--", style == "dash")) if on]
        in_block = False
        for n, line in enumerate(text.split("\n"), 1):
            body = line
            if in_block:
                if "*/" not in body:
                    continue
                body, in_block = body.split("*/", 1)[1], False
            if style != "hash":
                body = re.sub(r"/\*.*?\*/", "", body)
                if "/*" in body:
                    body, in_block = body.split("/*", 1)[0], True
            for m in marks:                       # a comment mark outside quotes ends the code
                quote, i = "", 0
                while i < len(body):
                    c = body[i]
                    if quote:
                        if c == "\\":
                            i += 1
                        elif c == quote:
                            quote = ""
                    elif c in "\"'":
                        quote = c
                    elif body.startswith(m, i):
                        body = body[:i]
                        break
                    i += 1
            body = rename_names(body.rstrip("\r"), style, renames)
            key = re.sub(r"[\s_]", "", body).lower()
            if len(key) > 1 and re.search(r"[a-z0-9]", key):
                out.append((f.name, n, line.strip(), key, shape(body, style)))
    return out


def spans(numbers):
    """[1, 2, 3, 7, 8] -> '1-3, 7-8'"""
    out, start, prev = [], None, None
    for n in sorted(numbers):
        if start is None:
            start = prev = n
        elif n == prev + 1:
            prev = n
        else:
            out.append((start, prev))
            start = prev = n
    if start is not None:
        out.append((start, prev))
    return ", ".join("%d" % a if a == b else "%d-%d" % (a, b) for a, b in out)


def runs(lines, unmatched):
    """Group unmatched lines that follow each other in the code: [file, first, last, count, first text, first index, last index]."""
    out, current = [], None
    for index in sorted(unmatched):
        fname, n, text = lines[index][:3]
        if current and current[0] == fname and index == current[6] + 1:
            current[2], current[3], current[6] = n, current[3] + 1, index
        else:
            current = [fname, n, n, 1, text, index, index]
            out.append(current)
    return out


def span(a, b):
    return "%d" % a if a == b else "%d-%d" % (a, b)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("before")
    ap.add_argument("after")
    ap.add_argument("--out", help="write the map as a Markdown report")
    ap.add_argument("--renames", help="a file that lists the names that were changed: old -> new")
    ap.add_argument("--notes", help="a notes file whose \"Explanations\" (or \"Notes and assumptions\") go into the map")
    ap.add_argument("--hash-comments", action="store_true", help="# starts a comment")
    args = ap.parse_args()

    renames = load_renames(args.renames)
    old = code_lines(args.before, args.hash_comments, renames)
    new = code_lines(args.after, args.hash_comments)

    taken = set()                                  # later lines already matched to an earlier line
    dest = {}                                      # index of an earlier line -> index of its later line
    how = {}                                       # index of an earlier line -> "same" or "names"
    # 1. in order: lines that did not move are paired with themselves
    matcher = difflib.SequenceMatcher(None, [l[3] for l in old], [l[3] for l in new], autojunk=False)
    for a, b, size in matcher.get_matching_blocks():
        for k in range(size):
            dest[a + k], how[a + k] = b + k, "same"
            taken.add(b + k)
    # 2 and 3. anywhere: the same text, then the same line with other names
    last_file = None
    for label, column in (("same", 3), ("names", 4)):
        free = defaultdict(list)
        for j, line in enumerate(new):
            if j not in taken and line[column]:
                free[line[column]].append(j)
        for i, line in enumerate(old):
            if i in dest:
                last_file = new[dest[i]][0]
                continue
            if not line[column] or not free[line[column]]:
                continue
            options = free[line[column]]
            pick = next((j for j in options if new[j][0] == last_file), options[0])   # stay with the neighbours
            options.remove(pick)
            taken.add(pick)
            dest[i], how[i], last_file = pick, label, new[pick][0]

    by_file = defaultdict(lambda: defaultdict(list))
    for i, j in dest.items():
        by_file[new[j][0]][old[i][0]].append(old[i][1])
    lost = runs(old, [i for i in range(len(old)) if i not in dest])
    added = runs(new, [j for j in range(len(new)) if j not in taken])

    # what happened to each run: an earlier run and a later run in the same place are one rewrite,
    # if they share enough of their words; otherwise one was removed and the other added
    words = lambda lines, r: {w.lower() for k in range(r[5], r[6] + 1)
                              for w in re.findall(r"[@$%]?[A-Za-z_]\w+|'[^']+'|\"[^\"]+\"", lines[k][2])}
    alike = lambda a, b: bool(a and b) and len(a & b) * 4 >= min(len(a), len(b))
    starts = {r[5]: r for r in added}
    ends = {r[6]: r for r in added}
    what_lost, what_added = {}, {}
    for r in lost:
        before_it = next((i for i in range(r[5] - 1, -1, -1) if i in dest), None)
        after_it = next((i for i in range(r[6] + 1, len(old)) if i in dest), None)
        partner = starts.get(dest[before_it] + 1 if before_it is not None else 0) \
            or (ends.get(dest[after_it] - 1) if after_it is not None else None)
        if partner is not None and id(partner) not in what_added and alike(words(old, r), words(new, partner)):
            what_lost[id(r)] = "Rewritten: now %s:%s" % (partner[0], span(partner[1], partner[2]))
            what_added[id(partner)] = "Rewritten from %s:%s" % (r[0], span(r[1], r[2]))
    logging = lambda lines, r: all(LOG_LINE.match(lines[k][2]) for k in range(r[5], r[6] + 1))
    for r in lost:
        what_lost.setdefault(id(r), "Logging removed or reworded" if logging(old, r) else "Removed")
    for r in added:
        what_added.setdefault(id(r), "Logging added or reworded" if logging(new, r) else "Added")

    same = sum(1 for v in how.values() if v == "same")
    tally = lambda what, rs: ", ".join("%d %s" % (sum(1 for r in rs if what[id(r)].startswith(k)), k.lower())
                                       for k in ("Rewritten", "Logging", "Removed", "Added")
                                       if any(what[id(r)].startswith(k) for r in rs))
    head = ["Before: %s (%d lines of code)" % (args.before, len(old)),
            "After:  %s (%d lines of code)" % (args.after, len(new)),
            "Earlier lines found in the later version: %d of %d (%d with the same text, %d with other names). "
            "Not found: %d, in %d run(s). Later lines that are new: %d, in %d run(s)."
            % (len(dest), len(old), same, len(how) - same, len(old) - len(dest), len(lost),
               len(new) - len(taken), len(added))]
    if lost or added:
        head.append("Runs of earlier code: %s. Runs of later code: %s."
                    % (tally(what_lost, lost) or "none", tally(what_added, added) or "none"))
    if renames:
        head.append("Names followed to their new name: %d, from %s" % (len(renames), args.renames))
    print("\n".join(head))
    print("\n1. Where the earlier code is now (later file <- earlier lines)")
    for target in sorted(by_file):
        for fname, numbers in sorted(by_file[target].items()):
            print("   %s <- %d lines of %s: %s" % (target, len(numbers), fname, spans(numbers)))
    print("\n2. Earlier code not found in the later version: %d line(s) in %d run(s)" % (len(old) - len(dest), len(lost)))
    for r in lost:
        print("   %s:%s (%d)  %s  |  %s" % (r[0], span(r[1], r[2]), r[3], what_lost[id(r)], r[4][:100]))
    print("\n3. Later code that was not in the earlier version: %d line(s) in %d run(s)"
          % (len(new) - len(taken), len(added)))
    for r in added:
        print("   %s:%s (%d)  %s  |  %s" % (r[0], span(r[1], r[2]), r[3], what_added[id(r)], r[4][:100]))

    if args.out:
        cell = lambda t: "`%s`" % t.replace("|", "\\|").replace("`", "'")
        out = Path(args.out)
        kept, tail = {}, ["1. None yet.", ""]        # what was filled in by hand in an earlier map
        if args.notes and Path(args.notes).is_file():
            given = Path(args.notes).read_text(encoding="utf-8", errors="replace")
            for heading in ("## Explanations", "## Notes and assumptions"):
                m = re.search(r"^%s.*?\n(.*?)(?=^## |\Z)" % re.escape(heading), given, re.M | re.S)
                if m and m.group(1).strip():
                    tail = re.sub(r"<!--.*?-->", "", m.group(1), flags=re.S).strip().split("\n") + [""]
                    break
        if out.exists():
            earlier = out.read_text(encoding="utf-8", errors="replace")
            for row in earlier.split("\n"):
                cells = [c.strip() for c in re.split(r"(?<!\\)\|", row)]
                if len(cells) == 8 and cells[6] and cells[4].startswith("`"):
                    kept[(cells[1], cells[4])] = cells[6]
            for heading in ("## Notes and assumptions", "## Assumptions"):
                if heading in earlier:
                    tail = earlier.split(heading, 1)[1].lstrip("\n").split("\n")
                    break
        note = lambda f, t: kept.get((f, cell(t)), "")
        md = ["# Traceability map", ""] + ["- " + h for h in head] + [
            "", "A line that is found has the same text, apart from spacing, letter case, underscores and, in the "
            "last pass, the names of its variables. Whether it still runs under the same conditions is for "
            "the review to read.", "",
            "## Where the earlier code is now",
            "| Now in | Earlier file | Lines of code | Earlier lines |", "|---|---|---|---|"]
        for target in sorted(by_file):
            for fname, numbers in sorted(by_file[target].items()):
                md.append("| %s | %s | %d | %s |" % (target, fname, len(numbers), spans(numbers)))
        md += ["", "## Earlier code not found in the later version",
               "The script says what happened to each run. The last column is for a reason the report does not give.", "",
               "| Earlier file | Lines | Lines of code | First line (quoted) | What happened | Why |",
               "|---|---|---|---|---|---|"]
        md += ["| %s | %s | %d | %s | %s | %s |" % (r[0], span(r[1], r[2]), r[3], cell(r[4]), what_lost[id(r)],
                                                 note(r[0], r[4])) for r in lost]
        md += ["", "## Later code that was not in the earlier version",
               "The script says where each run comes from. The last column is for a reason the report does not give.", "",
               "| File | Lines | Lines of code | First line (quoted) | What happened | Why |",
               "|---|---|---|---|---|---|"]
        md += ["| %s | %s | %d | %s | %s | %s |" % (r[0], span(r[1], r[2]), r[3], cell(r[4]), what_added[id(r)],
                                                 note(r[0], r[4])) for r in added]
        md += ["", "## Notes and assumptions"] + tail
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(md), encoding="utf-8")
        print("\nMap written to %s" % out)


if __name__ == "__main__":
    main()
