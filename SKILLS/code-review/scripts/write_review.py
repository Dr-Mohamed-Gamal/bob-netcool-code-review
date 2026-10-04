#!/usr/bin/env python3
"""Write the review of a change: a later version of code against the version it started from.

    python3 write_review.py <before> <after> --out <review> [--renames <file>]

The script compares the two versions (compare_code.py) and writes the review
report: the size of both versions, the scan counts before and after, every
difference it found, and the judgements of the reviewer. The reviewer writes
those judgements in the notes file next to the report, <review>.notes.md:

  ## Differences            one line for each difference: its class and why
  ## Findings               one block for each defect in the later version
  ## Checks performed       what was checked by reading, and how
  ## Claims of the author   whether each claim of the author's reports holds
  ## Coverage of the intent what the change did about each requirement
  ## Verdict, ## Not checked

The first run writes the notes file with every difference listed and the
form of each part. The review is complete when every difference has a class,
every unintended difference is a finding, every finding quotes words that
are on the line it cites, and every check and claim has an answer.

Python standard library only. The same input gives the same output.
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scan_code  # noqa: E402

HERE = Path(__file__).resolve().parent
TITLE = "# Review of a change — "
NOT_PASSED = 3
CLASSES = (("no behaviour change", ("no behaviour change", "no behavior change", "same behaviour", "same behavior")),
           ("intended", ("intended",)),
           ("unintended", ("unintended", "not intended")))
CHECKS = (
    "Merged queries, loops and branches give the same rows, grouping, counts and order",
    "Every variable is still set before it is read",
    "Every value that is read still receives a value on every path and in every file",
    "A step that every case used to reach is not now inside the part for one case",
    "No branch has become unreachable",
    "No output text differs, even by one character",
    "No escaping or conversion is done twice",
    "Each earlier fix produces what it should",
    "No question the author listed for the owner was acted on anyway",
    "No change lies outside the task",
)
SECTION = re.compile(r"^##\s+(.+?)\s*$")
D_LINE = re.compile(r"^\s*(D-\d+)(?:\s*(?:to|-|–|\.\.+)\s*(D-\d+))?\s*:\s*(.*)$", re.I)
ID_NUM = re.compile(r"D-(\d+)", re.I)


def cell(text):
    return re.sub(r"\s+", " ", str(text)).replace("|", "\\|").strip()


def code(text):
    """A line of code for a table cell: as it is written, its spaces kept."""
    return str(text).replace("|", "\\|").replace("`", "'").replace("\n", " ")


def notes_path(report):
    report = Path(report)
    return report.with_name(report.stem + ".notes.md")


def strip_comments(text):
    """The notes without the guidance written inside <!-- -->."""
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)


def sections(text):
    """{title in lower case: its lines}."""
    out, current = {}, None
    for line in strip_comments(text).split("\n"):
        m = SECTION.match(line)
        if m:
            current = m.group(1).strip().lower()
            out[current] = []
        elif current is not None:
            out[current].append(line.rstrip())
    return out


def part(found, *words):
    for title, lines in found.items():
        if any(title.startswith(w) or w in title for w in words):
            return lines
    return []


def klass(text):
    """(the class, what follows it) of an answer such as "intended: the fix of S-12"."""
    low = text.strip().lower()
    for name, words in sorted(CLASSES, key=lambda c: -max(len(w) for w in c[1])):
        for w in sorted(words, key=len, reverse=True):
            if low.startswith(w):
                return name, text.strip()[len(w):].lstrip(" :—-,").strip()
    return None, text.strip()


NAME = re.compile(r"[@$%]?[A-Za-z_][A-Za-z0-9_]*")
QUOTED = re.compile(r"\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'")


def line_changes(before_names, after_names, hash_comments=False):
    """What happened to the lines of each file that both versions hold: rewritten, renamed, removed, added.

    Two files are paired when they have the same name, or when each version is one file. Lines are compared
    without their indentation. A line whose text differs only in its names, outside quoted strings, is a
    rename; any other changed line is a rewritten line. A removed comment line that is not commented-out code
    is an explanation, listed with the line it stood above when that line stays.
    """
    import difflib
    from collections import Counter
    import inventory
    out = {"rewritten": [], "removed_code": [], "removed_comments": [], "removed_explanations": [], "added": [],
           "renames": Counter(), "renamed_lines": 0, "paired": 0}
    by_name = {Path(f).name: f for f in after_names}
    pairs = [(b, by_name[Path(b).name]) for b in before_names if Path(b).name in by_name]
    if not pairs and len(before_names) == 1 and len(after_names) == 1:
        pairs = [(before_names[0], after_names[0])]
    for b_file, a_file in pairs:
        try:
            b_text = Path(b_file).read_text(encoding="utf-8", errors="replace")
            a_text = Path(a_file).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        out["paired"] += 1
        style = scan_code.style_for(b_file, False, b_text)
        signs = {"hash": ("#",), "slash": ("//",), "dash": ("--",), "both": ("#", "//")}.get(style, ("//",))
        a = [l.rstrip("\r") for l in b_text.split("\n")]
        b = [l.rstrip("\r") for l in a_text.split("\n")]
        inside, state = set(), False                 # earlier lines inside a /* */ block
        for i, s in enumerate(a):
            if state:
                inside.add(i)
            if "/*" in s and "*/" not in s.split("/*", 1)[1]:
                state = True
                inside.add(i)
            elif state and "*/" in s:
                state = False

        def comment(i, s):
            return s.strip().startswith(signs + ("/*", "*/")) or i in inside

        def shape(s):
            return NAME.sub("N", QUOTED.sub('""', s.strip())), QUOTED.findall(s)

        name = Path(a_file).name
        names_before = Counter(x for s in a for x in NAME.findall(QUOTED.sub('""', s)))
        names_after = Counter(x for s in b for x in NAME.findall(QUOTED.sub('""', s)))

        def renamed_to(x, y):
            """True when x became y everywhere: x is (all but) gone from the later version, and y was (all but)
            absent from the earlier one. A name replaced by one the code already used is a correction."""
            return names_after[x] <= max(1, names_before[x] // 10) and names_before[y] <= max(1, names_after[y] // 10)

        pending = []                                 # (earlier line, later line, names changed, a rename by itself)

        def differ(i, j):
            """Record what distinguishes an earlier line from the later line it became."""
            if a[i].strip() == b[j].strip():
                return
            pairs_here = [(x, y) for x, y in zip(NAME.findall(QUOTED.sub('""', a[i])), NAME.findall(QUOTED.sub('""', b[j])))
                          if x != y]
            # a rename gives a name another name everywhere: the old one is gone and the new one is new. A name
            # replaced by one the code already had, or still used elsewhere, is a correction of that line.
            renamed = bool(pairs_here) and all(renamed_to(x, y) for x, y in pairs_here) and shape(a[i]) == shape(b[j])
            pending.append((i, j, pairs_here, renamed))

        def settle():
            """A name that only gained its prefix, or that now shares its new name with another earlier name, was
            corrected, not renamed: the line now reads a value it did not read before. Of several earlier names
            that became one, the one on the most lines is the rename."""
            uses = Counter(p for _, _, ps, ok in pending if ok for p in ps)
            into = {}
            for (x, y), n in uses.items():
                into.setdefault(y, []).append((n, x))
            merged = {(x, y) for y, olds in into.items() if len(olds) > 1 for _, x in sorted(olds)[:-1]}
            prefixed = {(x, y) for x, y in uses if y != x and y.lstrip("@$%") == x.lstrip("@$%")}
            for i, j, pairs_here, renamed in pending:
                if renamed and not set(pairs_here) & (merged | prefixed):
                    out["renamed_lines"] += 1
                    for pair in pairs_here:
                        out["renames"][pair] += 1
                else:
                    out["rewritten"].append((name, i + 1, a[i].strip(), j + 1, b[j].strip()))

        try:                                         # the earlier comment lines that are commented-out code
            code_off = {n for _, n, _ in inventory.read(Path(b_file), hash_comments)["commented_code"]}
        except Exception:
            code_off = None
        gone_lines, explained = set(), []

        def gone(i):
            gone_lines.add(i)
            if not a[i].strip():
                return
            if not comment(i, a[i]):
                out["removed_code"].append((name, i + 1, a[i].strip()))
            elif code_off is None or i + 1 in code_off or not re.sub(r"/\*|\*/|[\s{}();*#/-]", "", a[i]):
                out["removed_comments"].append((name, i + 1, a[i].strip()))
            else:
                explained.append(i)

        def new_line(j):
            if b[j].strip():
                out["added"].append((name, j + 1, b[j].strip()))

        # lines are lined up by their shape, so that a line whose names changed is still the same line; the
        # strings stay in the key, so that lines alike but for a string (one per item of a list) keep their place
        def key(s):
            parts, last = [], 0
            for m in QUOTED.finditer(s.strip()):
                parts += [NAME.sub("N", s.strip()[last:m.start()]), m.group(0)]
                last = m.end()
            return "".join(parts + [NAME.sub("N", s.strip()[last:])])

        keys_a = [key(x) for x in a]
        keys_b = [key(x) for x in b]
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, keys_a, keys_b, autojunk=False).get_opcodes():
            if tag == "equal":
                for i, j in zip(range(i1, i2), range(j1, j2)):
                    differ(i, j)
                continue
            olds, news = list(range(i1, i2)), list(range(j1, j2))
            # inside a changed run, an earlier line and a later line are the same line when they are alike enough
            alike = {(i, j): difflib.SequenceMatcher(None, keys_a[i], keys_b[j]).ratio() for i in olds for j in news} \
                if len(olds) * len(news) <= 2500 else {}
            best = {}                                # the pairing that keeps the order and holds the most alike lines
            # where the run has as many later lines as earlier ones, line for line, less alike is enough: a short
            # line whose long path or value was replaced is still that line rewritten
            enough = 0.4 if len(olds) == len(news) else 0.6
            for x in range(len(olds), -1, -1):
                for y in range(len(news), -1, -1):
                    if x == len(olds) or y == len(news):
                        best[(x, y)] = (0.0, None)
                        continue
                    options = [(best[(x + 1, y)][0], "old"), (best[(x, y + 1)][0], "new")]
                    score = alike.get((olds[x], news[y]), 0.0)
                    if score >= enough and a[olds[x]].strip() and b[news[y]].strip() \
                            and comment(olds[x], a[olds[x]]) == b[news[y]].strip().startswith(signs + ("/*", "*/")):
                        options.append((best[(x + 1, y + 1)][0] + score, "pair"))
                    best[(x, y)] = max(options, key=lambda o: o[0])
            x = y = 0
            while x < len(olds) or y < len(news):
                step = best[(x, y)][1] if x < len(olds) and y < len(news) else ("old" if x < len(olds) else "new")
                if step == "pair":
                    differ(olds[x], news[y])
                    x, y = x + 1, y + 1
                elif step == "old":
                    gone(olds[x])
                    x += 1
                else:
                    new_line(news[y])
                    y += 1
        settle()
        for i in explained:                          # the line the explanation stood above, if it stays
            k = i + 1
            while k < len(a) and (not a[k].strip() or k in explained):
                k += 1
            stays = k < len(a) and k not in gone_lines and not comment(k, a[k])
            out["removed_explanations"].append((name, i + 1, a[i].strip(), (k + 1, a[k].strip()) if stays else None))
    return out


def spans(numbers):
    """[3, 4, 5, 9] -> "3-5, 9"."""
    out, run = [], []
    for n in sorted(set(numbers)):
        if run and n == run[-1] + 1:
            run.append(n)
        else:
            if run:
                out.append("%d-%d" % (run[0], run[-1]) if len(run) > 1 else str(run[0]))
            run = [n]
    if run:
        out.append("%d-%d" % (run[0], run[-1]) if len(run) > 1 else str(run[0]))
    return ", ".join(out)


def clip(text, width=120):
    return text if len(text) <= width else text[:width - 3] + "..."


def answers_to(keys, found):
    """The answer to each of keys from the notes' (left, right) lines. A line answers a key when its left side is
    the key, or the start of it (24 characters or more), or the key with more after it; case, spacing and a
    closing "..." do not count. A line that would answer two keys answers neither."""
    norm = lambda s: re.sub(r"\s+", " ", re.sub(r"(\.\.\.|…)\s*$", "", s)).strip().lower()
    nk = [norm(k) for k in keys]
    out = {}
    for left, right in found:
        l = norm(left)
        hits = [i for i, k in enumerate(nk) if k == l] or \
               [i for i, k in enumerate(nk) if (len(l) >= 24 and k.startswith(l)) or (k and l.startswith(k))]
        if len(hits) == 1 and not out.get(hits[0]):
            out[hits[0]] = right
    return [out.get(i, "") for i in range(len(keys))]


def author_claims(report):
    """The headline sentence of each report these scripts wrote next to the review: what the author says was done."""
    out = []
    folder = Path(report).parent
    for f in sorted(folder.glob("*.md")) if folder.is_dir() else []:
        if f.name.endswith(".notes.md") or f.resolve() == Path(report).resolve() or not scan_code.written_by_script(f):
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if text.lstrip().startswith(("# Traceability map", TITLE.strip())):
            continue
        if text.lstrip().startswith("# Review —"):
            continue                                 # the review the change started from says nothing about the change
        for line in text.split("\n"):
            m = re.search(r"(\d+ line\(s\) were corrected[^.]*\.|The plan has [^.]*\.)", line)
            if m:
                out.append((f.name, m.group(1)))
                break
        if "## Coverage of the requirement" in text:     # what the author says was done about each requirement
            table = text.split("## Coverage of the requirement", 1)[1].split("\n## ", 1)[0]
            for line in table.split("\n"):
                cells = [c.strip() for c in re.split(r"(?<!\\)\|", line)[1:-1]]
                if len(cells) == 2 and re.match(r"^(done|in part)\b", cells[1], re.I):
                    out.append((f.name, "%s: %s" % (cells[0], clip(cells[1], 160))))
    return out


def skeleton(report, command, items, claims, docs):
    md = ["# Notes for the review %s" % Path(report).name, "",
          "Your judgements go in this file. The review report is written by the script from the comparison of the two",
          "versions and from these notes: do not edit it. After you change this file, run the command again:", "",
          "    %s" % command, "",
          "## Differences",
          "<!-- The script found these differences between the two versions. After each colon write its class, then why:",
          "       no behaviour change: <what shows it: a rename, a comment, moved code that runs under the same conditions>",
          "       intended: <the requirement or the defect it serves>",
          "       unintended: <what is wrong, and the finding below that reports it>",
          "     When the intent says behaviour must stay the same, every unintended difference is a finding.",
          "     Several in a row can be answered at once: \"D-03 to D-18: intended: ...\". Read the lines before you",
          "     answer: a difference is not harmless because the task asked for a change of that kind. -->"]
    for i, (group, show) in enumerate(items, 1):
        md.append("D-%02d:        <!-- %s: %s -->" % (i, group, show.replace("--", "- -")))
    if not items:
        md.append("<!-- The comparison lists no difference in calls, operators, strings, scan hits or structure. -->")
    md += ["", "## Findings",
           "<!-- One block for each defect you find in the later version by reading it against the earlier one:",
           "",
           "### file.ext: 120",
           "severity: High, Medium or Low",
           "quote: a few words that are on that line of the later version",
           "what: what is wrong and what it does, in one sentence",
           "introduced: yes: <what the earlier version had there>   or   no: the earlier version has it too, line N",
           "",
           "     The findings are numbered V-01, V-02 ... in the order of the blocks. If reading finds none, write",
           "     \"none found: yes\" on a line of its own. -->", "",
           "## Checks performed",
           "<!-- Read each changed file in full, then answer each line after the \" | \": what you found, and where you",
           "     looked (file and lines). \"not applicable: <why>\" is an answer. \"yes\" alone is not. -->"]
    md += ["%s | " % c for c in CHECKS]
    md += ["", "## Claims of the author",
           "<!-- What the author's reports say was done. After the \" | \" write \"holds: <the evidence>\" or",
           "     \"does not hold: <the evidence>\". Check each against the files, not against the report. -->"]
    md += ["%s: %s | " % (name, claim) for name, claim in claims] or ["<!-- No report of the author was found next to this review. -->"]
    md += ["", "## Coverage of the intent"]
    if docs:
        md += ["<!-- The document that says what the change should do: %s." % ", ".join(Path(d).name for d in docs),
               "     One line for each thing it asks that this change covers: \"<the requirement> | done: <evidence>\",",
               "     \"partly done: <what is missing>\" or \"not done: <evidence>\". \"All\" or \"every\" is done only",
               "     when a count shows none left. -->"]
    else:
        md += ["<!-- No requirement document came with the code. If the request stated the intent, one line for each",
               "     thing it asked: \"<the requirement> | done: <evidence>\". -->"]
    md += ["", "## Verdict",
           "<!-- One or two sentences: is the later version fit to replace the earlier one, and what stands in the way.",
           "     The counts are added by the script. Never say tested or verified: nothing was run. -->", "",
           "## Questions for the owner",
           "<!-- One per line: what only the owner of the code can settle, such as the value of a name that comes from",
           "     outside, or a choice the requirement does not make. -->", "",
           "## Not checked", "<!-- One per line. -->", ""]
    return "\n".join(md)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("before")
    ap.add_argument("after")
    ap.add_argument("--out", required=True)
    ap.add_argument("--renames")
    ap.add_argument("--command", default="")
    ap.add_argument("--hash-comments", action="store_true")
    args = ap.parse_args()
    report, notes_at = Path(args.out), notes_path(args.out)
    command = args.command or "python3 %s %s %s --out %s" % (sys.argv[0], args.before, args.after, args.out)

    # ---- the comparison of the two versions
    with tempfile.TemporaryDirectory() as tmp:
        data_at = Path(tmp) / "found.json"
        cmd = [sys.executable, "-B", str(HERE / "compare_code.py"), args.before, args.after, "--review", "--json", str(data_at)]
        cmd += ["--renames", args.renames] if args.renames else []
        cmd += ["--hash-comments"] if args.hash_comments else []
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0 or not data_at.is_file():
            sys.stderr.write(r.stderr)
            raise SystemExit("the comparison of the two versions failed (compare_code.py, exit code %d)" % r.returncode)
        found = json.loads(data_at.read_text(encoding="utf-8"))
    # where the earlier lines went: how many are still there, with the same text or with other names
    cmd = [sys.executable, "-B", str(HERE / "trace_code.py"), args.before, args.after]
    cmd += ["--renames", args.renames] if args.renames else []
    r = subprocess.run(cmd, capture_output=True, text=True)
    traced = []
    m = re.search(r"Earlier lines found in the later version: (\d+) of (\d+) .*?Not found: (\d+), in \d+ run\(s\)\. "
                  r"Later lines that are new: (\d+)", r.stdout)
    if m:
        traced = ["Of the %s earlier lines of code, %s are found in the later version (the same line, allowing for "
                  "indentation and for renamed variables) and %s are not: they were rewritten or removed. %s line(s) of "
                  "the later version are new." % (m.group(2), m.group(1), m.group(3), m.group(4))]
    lc = line_changes(found["before"].get("names", []), found["after"]["names"], args.hash_comments)
    items = []
    if len(lc["rewritten"]) <= 150:
        items += [("Line rewritten", "%s:%d `%s` is now line %d `%s`" % (f, i, clip(o), j, clip(n)))
                  for f, i, o, j, n in lc["rewritten"]]
    elif lc["rewritten"]:
        items.append(("Lines rewritten", "%d line(s), listed in the report" % len(lc["rewritten"])))
    if len(lc["removed_code"]) <= 60:
        items += [("Line of code removed", "%s:%d `%s`" % (f, i, clip(o))) for f, i, o in lc["removed_code"]]
    elif lc["removed_code"]:
        items.append(("Lines of code removed", "%d line(s): %s" % (len(lc["removed_code"]), spans(i for _, i, _ in lc["removed_code"]))))
    if len(lc["added"]) <= 60:
        items += [("Line added", "%s:%d `%s`" % (f, j, clip(n))) for f, j, n in lc["added"]]
    elif lc["added"]:
        items.append(("Lines added", "%d line(s): %s" % (len(lc["added"]), spans(j for _, j, _ in lc["added"]))))
    if lc["removed_comments"]:
        items.append(("Comment lines removed", "%d line(s) of the earlier version: %s"
                      % (len(lc["removed_comments"]), spans(i for _, i, _ in lc["removed_comments"]))))
    # a comment that is not commented-out code explains something: each is judged on its own
    items += [("Comment removed that is not commented-out code", "%s:%d `%s`%s" % (
        f, i, clip(t), " - it stood above line %d `%s`, which stays" % (above[0], clip(above[1], 80)) if above else ""))
        for f, i, t, above in lc["removed_explanations"][:60]]
    if len(lc["removed_explanations"]) > 60:
        items.append(("Comments removed that are not commented-out code", "%d more line(s): %s" % (
            len(lc["removed_explanations"]) - 60, spans(i for _, i, _, _ in lc["removed_explanations"][60:]))))
    if lc["renames"]:
        pairs_ = sorted(lc["renames"], key=lambda p: p[0].lower())
        items.append(("Names changed", "%d name(s) on %d line(s) that differ in names only: %s%s"
                      % (len(pairs_), lc["renamed_lines"], ", ".join("%s -> %s" % p for p in pairs_[:8]),
                         " ... all are listed in the report" if len(pairs_) > 8 else "")))
    # a string that is gone or new on a line already listed as rewritten is that same difference: not listed twice
    lines_listed = [o for _, _, o, _, n in lc["rewritten"]] + [n for _, _, o, _, n in lc["rewritten"]] if len(lc["rewritten"]) <= 150 else []
    lines_listed += [n for _, _, n in lc["added"]] if len(lc["added"]) <= 60 else []          # and on a line added or removed
    lines_listed += [o for _, _, o in lc["removed_code"]] if len(lc["removed_code"]) <= 60 else []
    covered = 0
    for g in found["groups"]:
        for show in g["items"]:
            m = re.match(r'^"(.*)" \((?:gone|new|used)', show, re.S) if g["label"].startswith("Strings") else None
            if m and "..." not in m.group(1) and any(m.group(1) in l for l in lines_listed):
                covered += 1
                continue
            items.append((g["label"], show))
    broken = {i for i, (group, _) in enumerate(items, 1) if group == "Files the change left broken"}
    docs = found.get("documents", [])
    claims = author_claims(report)
    first_run = not notes_at.is_file()
    raw = "" if first_run else notes_at.read_text(encoding="utf-8", errors="replace")
    found_parts = sections(raw)
    problems = []

    # ---- the class of each difference
    answers = {}
    for line in part(found_parts, "difference"):
        m = D_LINE.match(line)
        if not m:
            continue
        a = int(ID_NUM.match(m.group(1)).group(1))
        z = int(ID_NUM.match(m.group(2)).group(1)) if m.group(2) else a
        for n in range(min(a, z), max(a, z) + 1):
            if m.group(3).strip():
                answers[n] = m.group(3).strip()
    rows, counts = [], {"no behaviour change": 0, "intended": 0, "unintended": 0, "": 0}
    for n, (group, show) in enumerate(items, 1):
        name, why = klass(answers.get(n, ""))
        if n in answers and name is None:
            problems.append("D-%02d: start the answer with its class: \"no behaviour change\", \"intended\" or \"unintended\"." % n)
        elif name and len(why) < 10:
            problems.append("D-%02d: say why it is %s." % (n, name))
        elif name and n in broken and name != "unintended":
            problems.append("D-%02d: a file left with half a block or half a string cannot be loaded on its own. It is "
                            "\"unintended\", with a finding, whatever the task was." % n)
            name = None
        counts[name or ""] += 1
        rows.append((n, group, show, name or "", why if name else ""))

    # ---- the findings
    after = Path(args.after)
    names = {Path(f).name: f for f in found["after"]["names"]}
    blocks, block = [], None
    none_found = False
    for line in part(found_parts, "finding"):
        head = re.match(r"^###\s*(?:(.+?\.[A-Za-z0-9]+)\s*:\s*)?(?:lines?\s*)?(\d+)\s*$", line.strip())
        if head:
            block = {"file": (head.group(1) or "").strip(), "line": int(head.group(2))}
            blocks.append(block)
        elif re.match(r"^\s*none found\s*:\s*y", line, re.I):
            none_found = True
        elif block is not None:
            m = re.match(r"^\s*(severity|quote|what|introduced)\s*:\s*(.*)$", line, re.I)
            if m:
                block[m.group(1).lower()] = m.group(2).strip()
                block["_last"] = m.group(1).lower()
            elif line.strip() and block.get("_last"):
                block[block["_last"]] += " " + line.strip()
    findings = []
    for i, b in enumerate(blocks, 1):
        vid, label = "V-%02d" % i, "the finding on line %d" % b["line"]
        target = names.get(Path(b["file"]).name) if b["file"] else (found["after"]["names"][0] if len(names) == 1 else None)
        severity = (b.get("severity") or "").strip().capitalize()
        if target is None:
            problems.append("%s: say which file of the later version, as in \"### rules.js: %d\"." % (label, b["line"]))
            continue
        try:
            lines = Path(target).read_text(encoding="utf-8", errors="replace").split("\n")
        except OSError:
            lines = []
        quoted = lines[b["line"] - 1].rstrip("\r") if 0 < b["line"] <= len(lines) else ""
        want = re.sub(r"\s+", " ", (b.get("quote") or "").strip().strip("`\""))
        if not severity.startswith(("High", "Medium", "Low")):
            problems.append("%s: \"severity:\" must be High, Medium or Low." % label)
        if not want or want not in re.sub(r"\s+", " ", quoted):
            problems.append("%s: \"quote:\" must be words that are on line %d of %s. That line reads: %s"
                            % (label, b["line"], Path(target).name, quoted.strip()[:160] or "(no such line)"))
        if len(b.get("what", "")) < 15:
            problems.append("%s: \"what:\" is missing or too short." % label)
        if not re.match(r"^(yes|no)\b", b.get("introduced", ""), re.I):
            problems.append("%s: \"introduced:\" starts with yes or no, then the evidence from the earlier version." % label)
        findings.append((vid, severity, "%s:%d" % (Path(target).name, b["line"]), quoted.strip(), b.get("what", ""),
                         b.get("introduced", "")))
    known = {f[0] for f in findings}
    for n, group, show, name, why in rows:
        if name == "unintended" and not (set(re.findall(r"V-\d+", why)) & known):
            problems.append("D-%02d is unintended: name the finding that reports it (V-01, V-02 ...), and write that "
                            "finding under \"Findings\"." % n)
    missing = [n for n, _, _, name, _ in rows if not name]
    reading_done = bool(findings) or none_found

    # ---- checks, claims, coverage
    def pairs(lines):
        out = []
        for line in lines:
            if " | " in line or line.rstrip().endswith(" |"):
                left, _, right = line.partition(" |")
                out.append((left.strip(), right.strip(" |").strip()))
        return out

    check_rows = list(zip(CHECKS, answers_to(CHECKS, pairs(part(found_parts, "checks")))))
    for c, answer in check_rows:
        if not first_run and (len(answer) < 12 or answer.lower() in ("yes", "ok", "done", "checked")):
            problems.append("check \"%s\": say what you found and where you looked." % c)
    claim_keys = ["%s: %s" % (name, claim) for name, claim in claims]
    claim_rows = []
    for (name, claim), key, answer in zip(claims, claim_keys, answers_to(claim_keys, pairs(part(found_parts, "claims")))):
        if not first_run and not re.match(r"^(holds|does not hold)\b.{8,}", answer, re.I | re.S):
            problems.append("claim of %s \"%s\": %s. The line starts with the claim, or its first words, then \" | \", "
                            "then \"holds: <the evidence>\" or \"does not hold: <the evidence>\"."
                            % (name, clip(claim, 70), "the answer has no evidence" if answer else "no line answers it"))
        claim_rows.append((name, claim, answer))
    coverage = pairs(part(found_parts, "coverage"))
    if docs and not coverage and not first_run:
        problems.append("\"Coverage of the intent\" has no line yet: one for each thing %s asks that this change covers."
                        % ", ".join(Path(d).name for d in docs))
    for what, state in coverage:
        if not re.match(r"^(done|partly done|not done)\b.{6,}", state, re.I | re.S):
            problems.append("coverage of \"%s\": start with \"done:\", \"partly done:\" or \"not done:\", then the evidence."
                            % what[:60])
    verdict = " ".join(l.strip() for l in part(found_parts, "verdict") if l.strip())
    if not first_run and len(verdict) < 20:
        problems.append("\"Verdict\" is missing: one or two sentences.")
    not_checked = [l.strip().lstrip("-").strip() for l in part(found_parts, "not checked") if l.strip()]
    questions = [l.strip().lstrip("-").strip() for l in part(found_parts, "questions") if l.strip()]
    if not first_run and not reading_done:
        problems.append("\"Findings\" is empty: write a block for each finding, or \"none found: yes\" after reading "
                        "the later version against the earlier one.")

    # ---- the report
    sev = {"High": 0, "Medium": 0, "Low": 0}
    for f in findings:
        for k in sev:
            if f[1].startswith(k):
                sev[k] += 1
    b_, a_ = found["before"], found["after"]
    md = [TITLE + "%s against %s" % (args.after, args.before), "",
          "Written by the review script from the comparison of the two versions and from the notes in %s. Do not edit "
          "this file: write in the notes and run the script again." % notes_at.name, "",
          "## Verdict",
          "The comparison lists %d difference(s) between the two versions: %d without a change of behaviour, %d intended, "
          "%d unintended%s. Findings from reading: %d (High %d, Medium %d, Low %d). Nothing was run."
          % (len(rows), counts["no behaviour change"], counts["intended"], counts["unintended"],
             ", %d not yet judged" % counts[""] if counts[""] else "", len(findings), sev["High"], sev["Medium"], sev["Low"]),
          "", verdict or "The reviewer's verdict is not written yet.", "",
          "## The two versions", "| | Files | Lines |", "|---|---|---|",
          "| Earlier: %s | %d | %d |" % (cell(args.before), b_["files"], b_["lines"]),
          "| Later: %s | %d | %d |" % (cell(args.after), a_["files"], a_["lines"]), ""] + ([] if lc["paired"] else traced) + ["",
          "## What the change consists of"]
    if lc["paired"]:
        md += ["| What happened to the lines | Lines |", "|---|---|",
               "| Rewritten | %d |" % len(lc["rewritten"]),
               "| Changed in names only | %d (%d name(s)) |" % (lc["renamed_lines"], len(lc["renames"])),
               "| Lines of code removed | %d |" % len(lc["removed_code"]),
               "| Comment lines removed: commented-out code | %d |" % len(lc["removed_comments"]),
               "| Comment lines removed: explanations, not code | %d |" % len(lc["removed_explanations"]),
               "| Added | %d |" % len(lc["added"])]
        if len(lc["rewritten"]) > 150:
            md += ["", "Lines rewritten:", "", "| Earlier line | It read | Later line | It reads |", "|---|---|---|---|"]
            md += ["| %s:%d | `%s` | %d | `%s` |" % (f, i, code(o), j, code(n)) for f, i, o, j, n in lc["rewritten"][:400]]
        if covered:
            md += ["", "%d string(s) that are gone, new or used a different number of times stand on the lines rewritten, "
                   "added or removed listed below, and are judged with them." % covered]
        if lc["renames"]:
            listed = ["%s -> %s" % pair for pair in sorted(lc["renames"], key=lambda pair: pair[0].lower())]
            md += ["", "Names changed (%d): each earlier name is gone from the later version and its later name is new." % len(listed), ""]
            md += ["`%s`" % "`, `".join(listed[k:k + 6]) + ("," if k + 6 < len(listed) else "") for k in range(0, len(listed), 6)]
    else:
        md.append("The two versions do not hold their code in files of the same names, so the lines were not compared one "
                  "by one: the differences below come from the comparison of the code as a whole.")
    md += ["", "## What the scan finds in each version", "| Kind of defect | Earlier | Later | |", "|---|---|---|---|"]
    same = [title for title, b, a in found["scan"] if (b or a) and a == b]
    for title, b, a in found["scan"]:
        if a != b:
            md.append("| %s | %d | %d | %s |" % (cell(title), b, a, "went up" if a > b else "went down"))
    if not any(a != b for _, b, a in found["scan"]):
        md.append("| No count differs between the two versions | | | |")
    if same:
        md += ["", "The same in both versions: %s." % "; ".join("%s (%d)" % (title, b) for title, b, a in found["scan"] if (b or a) and a == b)]
    md += ["", "## Differences between the two versions",
           "| ID | Kind | What | Class | Why |", "|---|---|---|---|---|"]
    md += ["| D-%02d | %s | %s | %s | %s |" % (n, cell(group), cell(show), name or "NOT JUDGED", cell(why))
           for n, group, show, name, why in rows] or ["| | | The comparison lists no difference in calls, operators, "
                                                      "strings, scan hits or structure. | | |"]
    md += ["", "## Findings",
           "| ID | Severity | Where | The line, quoted | What is wrong | Introduced by the change |", "|---|---|---|---|---|---|"]
    md += ["| %s | %s | %s | `%s` | %s | %s |" % (v, s, w, code(clip(q, 200)), cell(what), cell(intro))
           for v, s, w, q, what, intro in findings] or ["| | | | | %s | |" % ("None found by reading." if none_found else "Not written yet.")]
    md += ["", "## Checks performed", "| Check | What was found, and where |", "|---|---|"]
    md += ["| %s | %s |" % (cell(c), cell(a) or "NOT ANSWERED") for c, a in check_rows]
    md += ["", "## Claims of the author", "| Report | What it says | Does it hold |", "|---|---|---|"]
    md += ["| %s | %s | %s |" % (cell(n), cell(c), cell(a) or "NOT ANSWERED") for n, c, a in claim_rows] \
        or ["| | No report of the author was found next to this review. | |"]
    md += ["", "## Coverage of the intent", "| Requirement | What the change did |", "|---|---|"]
    md += ["| %s | %s |" % (cell(a), cell(b)) for a, b in coverage] or ["| | %s |" % (
        "Not written yet." if docs else "No requirement document came with the code.")]
    md += ["", "## Not checked", "- Nothing was run. The review is a reading of the two versions and of the comparison "
           "the script made of them."]
    md += ["- %s" % x for x in not_checked if not re.match(r"^nothing was run\b", x, re.I)]
    md += ["", "## Questions for the owner of the code"]
    md += ["%d. %s" % (i, q) for i, q in enumerate(questions, 1)] or ["1. None."]
    md.append("")
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(md), encoding="utf-8")
    if first_run:
        notes_at.parent.mkdir(parents=True, exist_ok=True)
        notes_at.write_text(skeleton(report, command, items, claims, docs), encoding="utf-8")

    # ---- say where the review stands
    print("Review of the change: %s (written by this command; do not edit it)" % report)
    print("  Earlier version: %d file(s), %d lines. Later version: %d file(s), %d lines."
          % (b_["files"], b_["lines"], a_["files"], a_["lines"]))
    if lc["paired"]:
        print("  Lines: %d rewritten, %d changed in names only (%d name(s)), %d of code removed, %d comment line(s) removed "
              "(%d of them explanations, not code), %d added."
              % (len(lc["rewritten"]), lc["renamed_lines"], len(lc["renames"]), len(lc["removed_code"]),
                 len(lc["removed_comments"]) + len(lc["removed_explanations"]), len(lc["removed_explanations"]),
                 len(lc["added"])))
    else:
        for line in traced[:1]:
            print("  %s" % line)
    changed = ["%s %d -> %d" % (title, b, a) for title, b, a in found["scan"] if a != b]
    print("  Scan counts that changed: %s" % ("; ".join(changed) if changed else "none"))
    print("  Differences: %d (%d without a change of behaviour, %d intended, %d unintended, %d to judge). Findings: %d."
          % (len(rows), counts["no behaviour change"], counts["intended"], counts["unintended"], counts[""], len(findings)))
    print("Your notes: %s%s" % (notes_at, " (written now: every difference is listed, with the form of each part)"
                                if first_run else ""))
    if missing and not first_run:
        print("  Differences still to judge: %s" % ", ".join("D-%02d" % n for n in missing[:60]))
    if problems and not first_run:
        print("To correct in the notes:")
        for p in problems[:60]:
            print("  - %s" % p)
    if first_run:
        print("\nResult: not complete. This is expected on the first run: write your judgements in %s." % notes_at)
        sys.exit(0)
    if not problems and not missing:
        print("\nResult: complete")
        sys.exit(0)
    print("\nResult: not complete. Correct what is listed, in %s." % notes_at)
    sys.exit(NOT_PASSED)


if __name__ == "__main__":
    main()
