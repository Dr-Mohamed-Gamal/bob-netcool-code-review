#!/usr/bin/env python3
"""Show what a change did to some code, beyond what a line diff shows.

    python3 compare_code.py <before file-or-folder> <after file-or-folder>

Works when code was edited in place and when it was rewritten, moved or
split across files. Prints four comparisons:

  1. scan counts        the counts of scan_code.py before and after, and
                        every scan hit that is new after the change
  2. calls              every function whose number of calls changed, and
                        calls that are new to the code or gone from it
  3. operators and keywords that are new to the code
  4. text in strings    strings that are gone, used fewer or more times,
                        or new (logging left out)
  5. changed lines      with --lines, for one file changed in place: every
                        line that differs, before and after

It ends with a Gate block: what holds, and what is still TO SETTLE. With
--report <file>, a difference counts as settled when the report mentions
it (the name, the operator in backticks, the text of the string or of the
line), so the gate can be passed by explaining each difference in the
report, and the script says which ones are not there yet.

Every line it prints is a difference to explain, not a verdict. A change
that is meant to keep behaviour should leave sections 2 to 4 empty apart
from the differences the task asked for. The same input always gives the
same output. It compares text only; it does not run the code.

Comments are // to end of line and /* ... */. Add --hash-comments for
languages where # starts a comment. Python standard library only.
"""
import argparse
import json
import difflib
import re
import sys
from collections import Counter
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import compare_strings  # noqa: E402
import scan_code  # noqa: E402
import trace_code  # noqa: E402

RENAMES = {}                                  # old name -> new name, when the change renamed things
# Columns of a report that hold code as it was or as it is. A difference is explained by what a person
# wrote about it, not by the line that shows it: these cells are left out when the explanations are read.
CODE_COLUMNS = ("before", "after", "example before", "example after", "code", "match", "with", "fix", "old", "new",
                "first line")


def prose(raw):
    """A report without the cells of its tables that quote code."""
    out, blank = [], None
    for line in raw.split("\n"):
        if not line.startswith("|"):
            blank = None
            out.append(line)
            continue
        cells = re.split(r"(?<!\\)\|", line)
        if blank is None:                        # the header row of a table
            blank = {i for i, c in enumerate(cells) if c.strip().lower().startswith(CODE_COLUMNS)}
            out.append(line)
        elif set(line.strip()) <= set("|-: "):
            out.append(line)
        else:
            out.append("|".join("" if i in blank else c for i, c in enumerate(cells)))
    return "\n".join(out)


def read(target, hash_comments, documents=None):
    """Scan one version; return its scan, calls, operators, keywords, files, lines."""
    files = scan_code.collect([target])
    scan = scan_code.Scan()
    scan.add_documents(scan_code.documents_for([target]) if documents is None else documents)
    calls, ops, words = Counter(), {}, {}
    scan.learn(files, hash_comments)
    for f in list(files):
        if not scan.add_file(f, hash_comments):
            files.remove(f)
            continue
        toks = scan_code.lex(f.read_text(encoding="utf-8", errors="replace"), scan.styles[str(f)])
        for i, t in enumerate(toks):
            nxt = toks[i + 1] if i + 1 < len(toks) else None
            where = "%s:%d" % (f.name, t.line)
            if t.kind == "OP":
                ops.setdefault(t.val, where)
            elif t.kind == "NAME" and not t.sigil:
                defined_here = i > 0 and scan_code.is_word(toks[i - 1], scan_code.FUNC_WORDS)
                if scan_code.is_op(nxt, "(") and t.val.lower() not in scan_code.CONTROL_WORDS and not defined_here:
                    calls[t.val] += 1
                elif t.val.lower() in scan_code.KEYWORDS:
                    words.setdefault(t.val.lower(), where)
    scan.finish()
    return scan, calls, ops, words, files, scan.line_count()


def identity(scan, key, hit):
    """What makes a scan hit the same hit in both versions: its name, or its code.

    Letter case and underscores are left out, so a hit is still the same hit after a
    rename between naming styles (order_total, orderTotal, ORDER_TOTAL).
    """
    f, line, note = hit
    if key in ("unset", "unread", "once", "unlisted", "twice", "early", "index", "nocall", "twins", "writeback", "discard", "reapplied"):
        text = note.split(" — ")[0].split(" (")[0]
        text = RENAMES.get(text, text)           # the same hit under the name it has now
    elif key in ("placeholder", "secret", "entity"):
        text = note                              # the text found, wherever its line now is
    elif key == "tag":
        text = note.split(">")[0]
    else:
        text = scan.lines[f][line - 1] if 0 < line <= len(scan.lines[f]) else ""
        text = trace_code.rename_names(text.rstrip("\r"), scan.styles[f], RENAMES)
    return "".join(text.split()).replace("_", "").lower()


def cut(text, width=120):
    text = text.strip()
    return text if len(text) <= width else text[:width - 3] + "..."


def quoted(text, width=110):
    """A string as written, in quotes, so that spaces at its ends can be seen."""
    text = text.replace("\n", "\\n")
    return '"%s"' % (text if len(text) <= width else text[:width - 3] + "...")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("before")
    ap.add_argument("after")
    ap.add_argument("--hash-comments", action="store_true", help="# starts a comment")
    ap.add_argument("--report", help="a report or change log: a difference it mentions counts as settled")
    ap.add_argument("--lines", action="store_true", help="for one file changed in place: list every changed line")
    ap.add_argument("--renames", help="a file that lists the names that were changed: old -> new")
    ap.add_argument("--json", help="also write what was found to this file, as data")
    ap.add_argument("--review", action="store_true",
                    help="the report is a review of the change by someone else: a broken file is settled by a finding")
    args = ap.parse_args()
    RENAMES.update(trace_code.load_renames(args.renames))

    b_scan, b_calls, b_ops, b_words, b_files, b_lines = read(args.before, args.hash_comments)
    a_scan, a_calls, a_ops, a_words, a_files, a_lines = read(args.after, args.hash_comments,
                                                             [Path(d) for d in b_scan.docs])
    print("Before: %s (%d file(s), %d lines)" % (args.before, len(b_files), b_lines))
    print("After:  %s (%d file(s), %d lines)" % (args.after, len(a_files), a_lines))
    print("Every line below is a difference to explain, not a verdict.")

    # when one file was changed in place: which earlier line each later line corresponds to
    back = {}
    if len(b_files) == 1 and len(a_files) == 1:
        old_k = [l.rstrip("\r") for l in b_scan.text[str(b_files[0])].split("\n")]
        new_k = [l.rstrip("\r") for l in a_scan.text[str(a_files[0])].split("\n")]
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old_k, new_k, autojunk=False).get_opcodes():
            if tag == "equal" or (tag == "replace" and i2 - i1 == j2 - j1):
                back.update({j1 + k + 1: i1 + k + 1 for k in range(i2 - i1)})

    # 1. scan counts
    print("\n1. Scan counts                                           before   after")
    fresh, went_up = [], []          # went_up: for the reader; every rise shows as new hits in the gate
    scan_counts = []
    for key, title, _ in scan_code.CHECKS:
        b, a = len(b_scan.hits[key]), len(a_scan.hits[key])
        scan_counts.append((title, b, a))
        print("   %-51s %6d  %6d%s" % (title, b, a, "   went up" if a > b else ""))
        if a > b:
            went_up.append("%s %d -> %d" % (title, b, a))
        known = {identity(b_scan, key, h) for h in b_scan.hits[key]}
        same_line = {h[1] for h in b_scan.hits[key]}     # a hit on a line a correction rewrote is the same hit
        fresh += [(title, h) for h in sorted(set(a_scan.hits[key]))
                  if identity(a_scan, key, h) not in known and back.get(h[1]) not in same_line]
    print("\n   Scan hits that are new after the change: %d" % len(fresh))
    for title, (f, line, note) in fresh:
        code = a_scan.lines[f][line - 1] if 0 < line <= len(a_scan.lines[f]) else ""
        print("   %s — %s:%d  %s" % (title, Path(f).name, line, note))
        print("       %s" % cut(code))

    # 2. calls
    changed = sorted(n for n in set(b_calls) | set(a_calls) if b_calls[n] != a_calls[n])
    defined = sorted(n for n in a_scan.declared if n not in b_scan.declared)
    changed = [n for n in changed if n not in defined]
    new = [n for n in changed if not b_calls[n]]
    gone = [n for n in changed if not a_calls[n]]
    other = [n for n in changed if b_calls[n] and a_calls[n]]
    print("\n2. Calls: %d new to the code, %d gone from it, %d with a different count"
          % (len(new), len(gone), len(other)))
    for label, names in (("New to the code", new), ("Gone from the code", gone),
                         ("Different count", other)):
        if names:
            print("   %s (name, before -> after)" % label)
            for n in names:
                print("     %-40s %4d -> %d" % (n, b_calls[n], a_calls[n]))

    if defined:
        print("   Functions the later version defines: %d (name, times it is called)" % len(defined))
        for n in defined:
            print("     %-40s %4d" % (n, a_calls[n]))

    # 3. operators and keywords
    new_ops = sorted(o for o in a_ops if o not in b_ops)
    new_words = sorted(w for w in a_words if w not in b_words)
    flat = lambda s: s.replace("_", "").lower()
    had = {flat(m) for m in b_scan.members}
    new_members = sorted(m for m in a_scan.members if flat(m) not in had)
    print("\n3. Operators, keywords and member names new to the code: %d"
          % (len(new_ops) + len(new_words) + len(new_members)))
    for o in new_ops:
        print("   operator  %-10s first at %s" % (o, a_ops[o]))
    for w in new_words:
        print("   keyword   %-10s first at %s" % (w, a_words[w]))
    for m in new_members:
        f, line = a_scan.members[m][0]
        print("   member    %-10s first at %s:%d" % (m, Path(f).name, line))

    # 4. text in strings
    hashed = lambda files, scan: {str(f): args.hash_comments or scan.styles[str(f)] in ("hash", "both") for f in files}
    old = compare_strings.gather(b_files, hashed(b_files, b_scan), compare_strings.LOG_CALLS)
    cur = compare_strings.gather(a_files, hashed(a_files, a_scan), compare_strings.LOG_CALLS)
    keep = lambda s: len(s.strip()) >= 2
    missing = sorted((v[0][1], k, len(v)) for k, v in old.items() if k not in cur and keep(k))
    fewer = sorted((v[0][1], k, len(v), len(cur[k])) for k, v in old.items()
                   if k in cur and len(cur[k]) < len(v) and keep(k))
    more = sorted((v[0][1], k, len(old[k]), len(v)) for k, v in cur.items()
                  if k in old and len(v) > len(old[k]) and keep(k))
    added = sorted((v[0][0], v[0][1], k) for k, v in cur.items() if k not in old and keep(k))
    print("\n4. Text in strings, logging left out: %d gone, %d used fewer times, %d used more times, %d new"
          % (len(missing), len(fewer), len(more), len(added)))
    if missing:
        print("   Gone (line in before, times used, text)")
        for line, k, count in missing:
            print("     %6d  x%-3d %s" % (line, count, quoted(k)))
    if fewer:
        print("   Used fewer times (line in before, before -> after, text)")
        for line, k, b, a in fewer:
            print("     %6d  %d -> %d  %s" % (line, b, a, quoted(k)))
    if more:
        print("   Used more times (first line in after, before -> after, text)")
        for line, k, b, a in more:
            print("     %6d  %d -> %d  %s" % (line, b, a, quoted(k)))
    if added:
        print("   New (where in after, text)")
        for f, line, k in added:
            print("     %s:%d  %s" % (f, line, quoted(k)))

    # 5. changed lines, for one file changed in place
    changed_lines = []
    if args.lines and len(b_files) == 1 and len(a_files) == 1:
        old_l = [l.rstrip("\r") for l in b_scan.text[str(b_files[0])].split("\n")]
        new_l = [l.rstrip("\r") for l in a_scan.text[str(a_files[0])].split("\n")]
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old_l, new_l, autojunk=False).get_opcodes():
            if tag == "equal":
                continue
            for k in range(max(i2 - i1, j2 - j1)):
                b = (i1 + k + 1, old_l[i1 + k]) if i1 + k < i2 else (0, None)
                a = (j1 + k + 1, new_l[j1 + k]) if j1 + k < j2 else (0, None)
                changed_lines.append((b, a))
        print("\n5. Places where lines differ: %d (- the earlier line, + the later line)" % len(changed_lines))
        for (bn, bt), (an, at) in changed_lines:
            if bt is not None:
                print("   line %d  - %s" % (bn, cut(bt, 150)))
            if at is not None:
                print("   line %d  + %s" % (an, cut(at, 150)))

    # the gate: what holds as it stands, and what has to be corrected or explained.
    # Each group is a list of (what to show, test); the test says whether a report settles the item.
    plain = lambda s: re.sub(r"\s+", " ", re.sub(r"\\+\|", "|", s).replace("`", "'")).strip()

    def says(*texts):
        """Settled when the report holds one of these texts."""
        wanted = [t for t in texts if t and t.strip()]
        return lambda rep: any(plain(t) in rep["plain"] or t in rep["raw"] for t in wanted)

    def call(n):
        """A call is settled by its count line as the gate prints it, or by its name in backticks."""
        shown = "%s %d -> %d" % (n, b_calls[n], a_calls[n])
        return (shown, lambda rep: shown in rep["raw"] or "`%s`" % n in rep["raw"])

    def line_change(bn, bt, an, at):
        """A changed line is settled by a line of the report that holds its number and its text."""
        text = plain(at if at is not None else bt)
        numbers = [re.compile(r"(?<![\w.])%d(?![\w.])" % n) for n in (bn, an) if n]
        return lambda rep: any(text in l and any(n.search(l) for n in numbers) for l in rep["lines"])

    def new_call(n):
        """A call the earlier version never made is settled only by a line that names it and says it needs a test."""
        shown = "%s %d -> %d" % (n, b_calls[n], a_calls[n])
        return (shown, lambda rep: any((shown in l or "'%s'" % n in l) and re.search(r"\btest", l, re.I) for l in rep["lines"]))

    swapped = [call(n) for n in gone] + [new_call(n) for n in new]
    if swapped:                              # a call that rose is where the work may have moved to
        swapped += [call(n) for n in other if a_calls[n] > b_calls[n]]
    name_kinds = ("unset", "unread", "once", "unlisted", "twice", "early", "index", "nocall", "twins", "writeback", "discard", "reapplied")
    hits, broken = [], []
    for title, (f, line, note) in fresh:
        key = [k for k, t, _ in scan_code.CHECKS if t == title][0]
        if key in ("brackets", "orphan", "strclose"):    # a file that cannot be read: no explanation settles it
            at = "%s:%d" % (Path(f).name, line)
            # the author corrects it; a reviewer reports it, in a finding of its own that names the place
            broken.append(("%s %s" % (at, title), (lambda rep, at=at: any(at in l and re.search(r"\bV-\d+", l) for l in rep["lines"]))
                           if args.review else (lambda rep: False)))
            continue
        code = a_scan.lines[f][line - 1].strip() if 0 < line <= len(a_scan.lines[f]) else ""
        name = note.split(" — ")[0].split(" (")[0]
        where = "%s:%d" % (Path(f).name, line)
        # settled by naming the name; for the other kinds, by quoting the line (a line long enough to be
        # unmistakable) or by writing file:line
        hits.append(("%s %s" % (where, name if key in name_kinds else title),
                     says(name) if key in name_kinds and name else says(code if len(code.strip()) >= 12 else "", where)))
    rows = [
        ("Files the change left broken", broken,
         "a file that holds half a block or half a string cannot be read on its own: in a review this is a finding, so "
         "give each one a V- finding that names the file and line as shown here; it is not an effect of the split to be "
         "explained" if args.review else
         "these cannot be explained, only corrected: each file must hold whole blocks and whole strings. Keep the line "
         "that opens a block and the line that closes it in the same file; a new line, such as the one that reads the "
         "next file, can go between two earlier lines with \"### after line N\""),
        ("Scan hits that are new, and scan counts that went up", hits,
         "correct, or say in the report which earlier hit each one is a renamed form of (name it, or write file:line)"),
        ("Calls gone from the code or new to it", swapped,
         "one way of doing the work may have been swapped for another: undo it unless the task asks for that "
         "function. To explain one in the report, write its count line as shown here, or its name in backticks. A call "
         "the earlier version never made: use the call the code already uses for that work if it has one; if a new one "
         "is needed, the line that names it must also say that it needs a test where the code runs"),
        ("Calls made more often than before",
         [call(n) for n in other if a_calls[n] > b_calls[n] and not swapped],
         "work the earlier version did not do, or did less often: say what asks for it, or undo it. To explain "
         "one in the report, write its count line as shown here, or its name in backticks"),
        ("Conditional operators (?) the earlier version never uses",
         [(o, (lambda rep, o=o: any("`%s`" % o in l and re.search(r"\bV-\d+", l) for l in rep["lines"]))
           if args.review else (lambda rep: False)) for o in new_ops if "?" in o],
         "a finding in a review: give each one a V- finding that names the operator in backticks"
         if args.review else
         "the language of the code may not have this operator, and nothing in the code shows that it does: this cannot "
         "be explained, only rewritten with what the earlier version already uses (for a value chosen by a condition, "
         "an if / else that sets it)"),
        ("Operators, keywords and member names new to the code",
         [(x, says("`%s`" % x)) for x in [o for o in new_ops if "?" not in o] + new_words]
         + [(m, says(m.lstrip("."))) for m in new_members],
         "rewrite with what the earlier version already uses, or say that it needs a test"),
        ("Strings gone, new, or used a different number of times",
         [(quoted(k, 50), says(k.strip())) for _, k, _ in missing] + [(quoted(k, 50), says(k.strip())) for _, k, _, _ in fewer]
         + [(quoted(k, 50), says(k.strip())) for _, k, _, _ in more] + [(quoted(k, 50), says(k.strip())) for _, _, k in added],
         "each must belong to a change the task asked for; restore the others"),
    ]
    if changed_lines:
        rows.append(("Lines that differ",
                     [("line %d" % (bn or an), line_change(bn, bt, an, at))
                      for (bn, bt), (an, at) in changed_lines if (at if at is not None else bt).strip()],
                     "each must be a change the task asked for, with its own row in the report that holds its line "
                     "number and the line as it is now (or as it was, if it was removed); undo the others"))

    def endings(scan):
        """How the lines of a version end: CRLF, LF, or mixed."""
        crlf = sum(t.count("\r\n") for t in scan.text.values())
        lf = sum(t.count("\n") for t in scan.text.values()) - crlf
        return "none" if not crlf + lf else "CRLF" if not lf else "LF" if not crlf else "mixed"

    if endings(b_scan) != endings(a_scan) and "none" not in (endings(b_scan), endings(a_scan)):
        rows.append(("Line endings", [("%s -> %s" % (endings(b_scan), endings(a_scan)), says("line endings"))],
                     "keep the line endings of the earlier version; a tool that reads the file may depend on them"))

    def beyond_ascii(scan):
        """The characters outside ASCII in a version, each with the first place it stands."""
        found = {}
        for name, text in scan.text.items():
            for n, line in enumerate(text.split("\n"), 1):
                for ch in line:
                    if ord(ch) > 127 and ch not in found:
                        found[ch] = (Path(name).name, n)
        return found

    had, has = beyond_ascii(b_scan), beyond_ascii(a_scan)
    if set(has) - set(had):
        rows.append(("Characters outside ASCII that the earlier version does not hold",
                     [("%s (U+%04X), first at %s:%d" % ((ch, ord(ch)) + has[ch]), says("U+%04X" % ord(ch)))
                      for ch in sorted(set(has) - set(had))],
                     "write the line with characters the earlier version uses (a plain hyphen, straight quotes); the "
                     "platform that reads the file may use another encoding. To explain one that the task asks for, "
                     "write its code as shown here"))
    if args.json:
        # the strings in full, each with what happened to it
        told = {"Strings gone, new, or used a different number of times":
                ["%s (gone, was used %d time(s))" % (quoted(k, 160), n) for _, k, n in missing]
                + ["%s (used fewer times: %d -> %d)" % (quoted(k, 160), b, a) for _, k, b, a in fewer]
                + ["%s (used more times: %d -> %d)" % (quoted(k, 160), b, a) for _, k, b, a in more]
                + ["%s (new, first at %s:%d)" % (quoted(k, 160), f, line) for f, line, k in added]}
        Path(args.json).write_text(json.dumps({
            "groups": [{"label": label, "action": action, "items": told.get(label) or [show for show, _ in items]}
                       for label, items, action in rows],
            "scan": scan_counts,
            "before": {"files": len(b_files), "lines": sum(b_scan.line_count(str(f)) for f in b_files),
                       "names": [str(f) for f in b_files]},
            "after": {"files": len(a_files), "lines": sum(a_scan.line_count(str(f)) for f in a_files),
                      "names": [str(f) for f in a_files]},
            "documents": [str(d) for d in a_scan.docs]}, indent=1), encoding="utf-8")
    rep, where = None, args.report
    if args.report:
        path = Path(args.report)
        raw = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
        if raw.lstrip().startswith("# Traceability map"):
            # the tables of a map are written by the script and name every difference themselves:
            # only what was written under its notes can explain anything
            raw = raw.split("## Notes and assumptions", 1)[1] if "## Notes and assumptions" in raw else ""
            where = "%s, under \"Notes and assumptions\"," % args.report
        said = prose(raw)                        # a changed line is settled by its row; anything else by what is written
        rep = {"raw": said, "plain": plain(said), "lines": [plain(l) for l in raw.split("\n")]}
    if len(a_files) > len(b_files):
        print("\nNote: the later version has more files. The scan takes the names of all its files together, so "
              "it cannot tell whether a value set in one file reaches a read in another; a count that went "
              "down may be a finding that is now hidden. Read the hand-over between the files.")
    print("\nGate%s" % (" (a difference that %s explains is settled)" % where if args.report else ""))
    open_items = 0
    for label, items, action in rows:
        if rep is not None:
            items = [(show, test) for show, test in items if not test(rep)]
        if items:
            open_items += len(items) if rep is not None else 1
            shown = ", ".join(show for show, _ in items[:40]) + (" and %d more" % (len(items) - 40) if len(items) > 40 else "")
            print("   TO SETTLE  %s: %s\n              -> %s" % (label, shown, action))
        else:
            print("   holds      %s: %s" % (label, "none" if rep is None else "none, or all in the report"))
    print("Result: %s" % ("nothing to settle" if not open_items
                          else "%d item(s) to settle before the task is finished" % open_items))


if __name__ == "__main__":
    main()
