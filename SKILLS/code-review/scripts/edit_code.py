#!/usr/bin/env python3
"""Change existing code from a written plan: corrections, rules, renames, and new files.

    python3 edit_code.py <code file-or-folder> --out <folder> --report <report.md>

The changed copy and its report are written by this script every time it
runs, from the plan in the notes file next to the report (<report>.notes.md).
The plan is written by the person who changes the code; the script applies it,
so that nobody re-types the code and nothing is lost or mistyped:

  ## Corrections
    ### line 804            the new line(s) under "after:", or "remove: yes"
    ### lines 10-12         the same, for several lines (replaced by the lines given)
    ### after line 804      new lines under "insert:"
    ### rule prefix-logs    "match:" a regular expression, "with:" its replacement
                            (groups as \\1), applied to every line, or to "lines: 1-200"
  ## Renames                old -> new, one per line: applied where the old name is
                            used as a name, not inside strings and not after a dot
  ## Files                  for a split: one block per new file, with the ranges of
    ### folder/file.ext     the earlier code it holds ("lines: 1-57, 3100-3338", in
                            the order wanted) and new lines under "prepend:" and
                            "append:". Every earlier line must land in a file or be
                            removed by a correction.

Every line number is a line of the ORIGINAL code. The copy keeps the encoding
and the line endings of the original. The first run writes the notes file
with the form of each part and the facts of the code that a plan starts from.

It ends with a line that starts with "Result:". Exit code 0 when the plan was
applied in full, 3 when the plan is not complete yet, anything else when the
script itself failed. Python standard library only.
"""
import argparse
import hashlib
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import inventory  # noqa: E402
import notes as notes_file  # noqa: E402
import scan_code  # noqa: E402
import trace_code  # noqa: E402

NOT_PASSED = 3
TITLE = "# Change — "
CAMEL = re.compile(r"^[a-z][a-zA-Z0-9]*$")


COVERED = re.compile(r"^\s*(done|in part|not done)\b\s*:?\s*(.*)$", re.I | re.S)
WAITING = re.compile(r"\b(pending|await\w*|waiting\s+for|subject\s+to)\b[^.;]{0,60}\b(approv\w*|decision|confirmation|sign-?off)\b",
                     re.I)


STRING = re.compile(r"\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'")


def cell(text):
    return "`%s`" % text.strip().replace("|", "\\|").replace("`", "'")


def plain(text):
    return text.replace("|", "\\|").replace("\n", " ")


def short(text, width=150):
    text = " ".join(text.split())
    return text if len(text) <= width else text[:width - 3] + "..."


def span(a, b):
    return "%d" % a if a == b else "%d-%d" % (a, b)


def spans(numbers):
    out, start, prev = [], None, None
    for n in sorted(numbers):
        if start is None:
            start = prev = n
        elif n == prev + 1:
            prev = n
        else:
            out.append(span(start, prev))
            start = prev = n
    if start is not None:
        out.append(span(start, prev))
    return ", ".join(out)


def camel(name):
    """A camelCase form of a name: order_total -> orderTotal, MAXSIZE -> maxsize, HTTPCode_new -> httpCodeNew."""
    parts = [p for p in re.split(r"_+", name) if p]
    words = []
    for p in parts:
        if p.isupper() or p.islower() or p.isdigit():
            words.append(p.lower())
        else:
            words += [w.lower() for w in re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z0-9]+", p)]
    return words[0] + "".join(w[:1].upper() + w[1:] for w in words[1:]) if words else name


def outside_names(scan):
    """Names this code must not rename: (never given a value here, given a value and never read here).

    A name the code never sets is provided by the platform or the caller under that name. A name the code
    sets and never reads is dead, or is read by another component under that name.
    """
    names = {k for k in set(scan.reads) | set(scan.assigns) if scan.reads.get(k) or scan.assigns.get(k)}
    return ({k for k in names if not scan.assigns.get(k)}, {k for k in names if not scan.reads.get(k)})


def read_first(scan):
    """Names the code reads before the line that first gives them a value: their first value comes from outside."""
    return {entry[1] for entry in scan.early}


def mechanical(scan, wanted):
    """The mechanical camelCase renames of the names that are not camelCase: (old -> new, [(old, new) that clash]).

    A clash is another name, or another proposal, that is the same word in another letter case: renaming
    would make two names one. `wanted` holds the renames a person asked for; they are left alone. Names
    the code never sets, or never reads, are not renamed.
    """
    accepted, clashes = {}, []
    given, unread = outside_names(scan)
    given = given | read_first(scan)
    plain_names = {k for k in set(scan.reads) | set(scan.assigns) if (scan.reads.get(k) or scan.assigns.get(k))
                   and k[0] not in scan_code.SIGILS}
    for k in sorted(plain_names, key=str.lower):
        if k in wanted or CAMEL.match(k) or k.lower() in scan_code.KEYWORDS or k in given or k in unread:
            continue
        new = camel(k)
        others = {camel(o).lower() for o in plain_names if o != k and not CAMEL.match(o) and o not in wanted}
        taken = {o.lower() for o in plain_names if o != k} | others | {v.lower() for v in wanted.values()}
        if new.lower() in taken or new == k:
            clashes.append((k, new))
        else:
            accepted[k] = new
    return accepted, clashes


def wrap(items, width=108, indent="       "):
    """Items joined with commas, in lines of a given width."""
    lines, current = [], indent
    for item in items:
        if len(current) + len(item) + 2 > width and current.strip():
            lines.append(current.rstrip())
            current = indent
        current += item + ", "
    if current.strip():
        lines.append(current.rstrip().rstrip(","))
    return lines


VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


def whole_block(text):
    """What a block of lines opens and does not close, or closes without opening: tags of a page, and brackets
    outside strings. Empty when the block is whole."""
    out, tags = [], defaultdict(int)
    tag = re.compile(r"""<(/?)([A-Za-z][\w-]*)((?:\s+[^\s=>/"']+(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>"']+))?)*)\s*(/?)>""")
    for m in tag.finditer(text):                 # an attribute value in quotes may hold < and >
        name = m.group(2).lower()
        if name not in VOID_TAGS and not m.group(4):
            tags[name] += -1 if m.group(1) else 1
    out += ["<%s> opened %d more time(s) than closed" % (k, v) if v > 0 else "</%s> closed %d more time(s) than opened"
            % (k, -v) for k, v in sorted(tags.items()) if v]
    bare = STRING.sub('""', tag.sub(" ", text))
    for o, c in ("()", "[]", "{}"):
        if bare.count(o) != bare.count(c):
            out.append("%s %d, %s %d" % (o, bare.count(o), c, bare.count(c)))
    return "; ".join(out)


STYLE = re.compile(r"([A-Za-z][\w-]*)\s*:\s*(-?\d+(?:\.\d+)?(?:px|em|rem|pt|%)?)")


def varying_styles(lines, a, z, name_line=None, grow=0):
    """The style values of the block a-z that the other blocks of the same shape (the items made like it) set
    differently: [(property, its value here, "value in where, ...", the value for the new item or None)]. A value
    that changes from item to item, such as a margin that fits the length of a label, is a choice for the new item,
    not a part of the model to copy. The value for the new item is that of the items whose name line (offset
    name_line in the block) is as long as the new item's, which is `grow` characters longer than the model's; it
    is given when an item's name is exactly as long, or two items at the nearest length agree."""
    def shape(s):
        s = re.sub(r"\"[^\"]*\"|'[^']*'", '""', s.strip())
        return re.sub(r"\d+", "0", re.sub(r"[A-Za-z_][\w-]*", "N", s))
    n = z - a + 1
    want = [shape(l) for l in lines[a - 1:z]]
    keys = [shape(l) for l in lines]
    siblings = [i for i in range(1, len(lines) - n + 2) if i != a and keys[i - 1:i - 1 + n] == want]
    out = []
    for k in range(n):
        for prop, here in STYLE.findall(lines[a - 1 + k]):
            seen = {}
            for i in siblings:
                for p, v in STYLE.findall(lines[i - 1 + k]):
                    if p == prop and v != here:
                        name = re.search(r"\bid=[\"']([^\"']+)", "\n".join(lines[i - 1:i - 1 + n]))
                        seen.setdefault(v, []).append(name.group(1) if name else "line %d" % (i + k))
            if seen:
                rec = None
                if name_line is not None:
                    near = []                    # (distance from the new name's length, value) for each item
                    base = len(lines[a - 1 + name_line].strip())
                    for i in siblings:
                        vals = [v for p, v in STYLE.findall(lines[i - 1 + k]) if p == prop]
                        if vals:
                            near.append((abs(len(lines[i - 1 + name_line].strip()) - base - grow), vals[0]))
                    if near:
                        best = min(d for d, _ in near)
                        at_best = [v for d, v in near if d == best]
                        top = max(set(at_best), key=at_best.count)
                        if best == 0 or at_best.count(top) >= 2:
                            rec = top
                out.append((prop, here, "; ".join(
                    "%s in %s" % (v, ", ".join(w[:4]) + (" and %d more" % (len(w) - 4) if len(w) > 4 else ""))
                    for v, w in sorted(seen.items(), key=lambda e: -len(e[1]))), rec))
    return out


def skeleton(report, command, scan, files, data):
    """The notes file as it is first written: the form of a plan, and the facts of the code to start from."""
    many = len(files) > 1
    where = lambda f, n: "%s: %d" % (Path(f).name, n) if many else "%d" % n
    md = ["# Plan for the change %s" % report.name, "",
          "The change is made by the script from this plan: the changed copy and the report are written from it, and",
          "the original is never touched. Write the plan, then run the command again:", "",
          "    %s" % command, "",
          "Every line number below is a line of the ORIGINAL code. Do not edit the copy or the report by hand.", "",
          "## Corrections",
          "<!-- One block for each change, in one of these forms:",
          "",
          "### line 120                 replace one line: the new line under \"after:\"",
          "### lines 120-124            replace several lines by the lines under \"after:\" (fenced block, three backticks)",
          "### lines 120, 131, 140-142  with \"remove: yes\": take those lines out (one block, one \"why:\", for any list)",
          "### after line 120           put the lines under \"insert:\" after that line",
          "### rule prefix-logs         a rule for every line: match: <regular expression>  with: <replacement, groups as \\1>",
          "                             add \"lines: 1-200\" to apply it to a range only; put a value in backticks to keep",
          "                             the spaces at its ends. A rule that changes no line is refused.",
          "### commented-out code       \"remove: all\" takes out every line the facts below list as commented-out",
          "                             code; \"except: 523, 1898\" keeps those lines (a comment that explains, not code).",
          "                             \"labels: 221, 760\" also takes out those comment lines the facts list right above",
          "                             that code which only label it (\"# COMMENTED BY ...\", \"uncomment the lines below\");",
          "                             a heading or an explanation of the code that stays is kept.",
          "                             The facts list each line with its text: decide from them, without reading the file",
          "                             again, and do not copy line numbers into a block of your own.",
          "### copy sw1 as sw2          a new item made like an existing one (a device, a menu entry, a case):",
          "                             lines: 40-47     the block of the model, copied right after itself",
          "                             replace:         one \"old -> new\" per line, besides \"sw1 -> sw2\" itself, for the",
          "                                              other spellings of the model's name (SW1 -> SW2, F_SW1_ ->",
          "                                              F_SW2_); a value that has spaces goes in backticks",
          "                             Every other line that names the model (sw1 at the start of a word) is copied right",
          "                             after itself with the same replacements, so the new item is wherever the model is:",
          "                             one block for each new item, and no block or insertion of your own for those lines.",
          "                             The copy is refused while it still holds the model's name in any letter case",
          "                             (SW1, F_SW1_) or another name of the model, or uses a name the",
          "                             code already has; \"keep:\" names text meant to stay or to be shared, \"except:\"",
          "                             lists lines that name the model and are not to be copied (say why). Where a style",
          "                             value of the model (a margin) differs between the items made like it, the gate gives",
          "                             the value of the items whose name is as long as the new one's: put it under replace:.",
          "",
          "Each block has \"why:\" — the sentence of the requirement that asks for it, and what stays the same.",
          "For a merged call or query, \"why:\" says why the rows, grouping, distinct values, counts and order are the same.",
          "Order: corrections and insertions first, then every rule over every line (the new ones too), then the renames.",
          "New lines get the indentation of the line they replace or follow; inside a fenced block the indentation is kept",
          "relative to its first line. The line endings and the encoding of the original are kept.",
          "A removal accounts by itself for what the removed lines held. For a replacement, an insertion or a rule, the gate",
          "asks you to name what it adds or drops (a call, an operator, the text of a string) in \"why:\" or under",
          "\"Explanations\". -->", "",
          "## Renames"]
    names = {k for k in set(scan.reads) | set(scan.assigns) if (scan.reads.get(k) or scan.assigns.get(k))
             and k[0] not in scan_code.SIGILS}
    accepted, clashes = mechanical(scan, {})
    given, unread = outside_names(scan)
    odd = lambda group: sorted((k for k in names & group if not CAMEL.match(k) and k.lower() not in scan_code.KEYWORDS),
                               key=str.lower)
    md += ["<!-- One per line: old -> new. Applied where the old name is used as a name: not inside strings, not after",
           "     a dot. Do not rename what another component reads by name. A new name that the code already uses is",
           "     refused.",
           "     The line \"accept the proposals\" renames every name listed below to its mechanical camelCase form",
           "     (order_total -> orderTotal, MAXSIZE -> maxsize, HTTPCode_new -> httpCodeNew). Add your own lines for",
           "     the names that should say what the value is for: your line wins over the mechanical form.",
           "     Names that are not camelCase (%d):" % len(accepted)]
    md += wrap(sorted(accepted, key=str.lower))
    if clashes:
        md += ["     Left as they are by \"accept the proposals\", because the mechanical form is already another name, or",
               "     would be the same as another proposal (give them a name of their own if they are to be renamed):"]
        md += wrap(["%s (-> %s)" % (k, new) for k, new in clashes])
    if odd(given):
        md += ["     Not renamed, and refused if you list them: this code never gives them a value, so the platform or the",
               "     caller provides them under that name:"]
        md += wrap(odd(given))
    if odd(read_first(scan) - given):
        md += ["     Not renamed, and refused if you list them: the code reads them before the line that first gives them",
               "     a value, so their first value may come from outside under that name (or they are used too early,",
               "     a defect to settle first):"]
        md += wrap(odd(read_first(scan) - given))
    if odd(unread):
        md += ["     Not renamed, and refused if you list them: nothing in this code reads them, so if they are in use,",
               "     another component reads them under that name:"]
        md += wrap(odd(unread))
    md += ["-->", "", "## Files",
           "<!-- Only for a split: one block per new file, in the order the files should be read.",
           "",
           "### folder/newFile.ext",
           "lines: 1-57, 3100-3338      ranges of the earlier code, in the order wanted; a range may go to several files",
           "prepend:                    new lines at the start (fenced block); append: new lines at the end",
           "why: what the file holds, and the sentence of the requirement that asks for it",
           "",
           "When the earlier code is several files, start \"lines:\" with the name of the file the ranges are in, as in",
           "\"lines: rules.js: 1-57, 3100-3338\"; \"lines: rules.js: all\" takes the whole file. A new file that the",
           "requirement asks for and that holds no earlier line has no \"lines:\": its content is under \"prepend:\".",
           "",
           "Every earlier line must land in a file or be removed by a correction; the script lists the ones that do not. -->", "",
           "## Explanations",
           "<!-- The gate compares the earlier and the later code and lists each difference: a call gone or new (name it in",
           "     backticks, or write its count line as the gate prints it), an operator or keyword new to the code (in",
           "     backticks), a string gone or new (its text). Explain each one here, with the sentence of the requirement",
           "     that asks for it, or correct the plan. -->", "",
           "## Verdict",
           "<!-- Two or three sentences: what was done and what was not done and why. The counts are added by the script. -->", "",
           "## Questions for the owner",
           "<!-- One per line: every choice the requirement does not make for you. -->", "",
           "## Not checked",
           "<!-- One per line. -->", "",
           "## Facts of the code, for the plan (written by the script; not read back)", ""]
    if scan.docs:
        at = md.index("## Explanations")
        md[at:at] = [
            "## Coverage of the requirement",
            "<!-- The document that says what the code should become: %s." % ", ".join(Path(d).name for d in scan.docs),
            "     One line for each thing it asks of this task, in its own words, then \" | \", then one of:",
            "       done: the blocks, rules or files above that do it",
            "       in part: what is done; then what is not, and what in the files prevents it",
            "       not done: what in the files prevents it",
            "     What the document asks for is to be done: it is the owner's decision already, so waiting for an",
            "     approval is not a reason. A reason is something the files show: the data needed is not in the",
            "     workspace, two things it asks for cannot both hold, the change would alter what the code does.",
            "     Only what the document leaves open goes under \"Questions for the owner\". -->", ""]
    md.append("Line endings: %s. Files: %s." % (data["endings"], ", ".join(Path(str(f)).name for f in files)))
    md.append("")
    for f in files:
        blocks = scan.outline.get(str(f), [])
        size, depth = 8, 3                       # the larger blocks first: at most about 150 lines of outline
        while sum(1 for a, z, _, d in blocks if z - a + 1 >= size and d < depth) > 150:
            size *= 2
        shown = [(a, z, text, d) for a, z, text, d in blocks if z - a + 1 >= size and d < depth]
        if shown:
            md.append("Outline of %s: the blocks of %d lines or more, to the third level (first line-last line, what "
                      "introduces the block). A range that starts or ends inside a block cuts the block in two." % (
                          Path(str(f)).name, size))
            md += ["  %s%d-%d  %s" % ("  " * d, a, z, text) for a, z, text, d in shown]
            md.append("")
    md.append("Repeated calls, same function and same first argument (candidates for one call):")
    for (fn, first), places in sorted(data["same_source"].items(), key=lambda kv: kv[1][0][1]):
        reach = max(n for _, n in places) - min(n for _, n in places) + 1
        md.append("  %s(%s, ...)  x%d  lines %s%s" % (fn, first, len(places), ", ".join(where(f, n) for f, n in places),
                                                      "  (within %d lines)" % reach if reach <= 150 and not many else ""))
    md.append("  none" if not data["same_source"] else "")
    md.append("Identical calls made more than once:")
    for (fn, a), places in sorted(data["identical"].items(), key=lambda kv: kv[1][0][1]):
        md.append("  %s(%s)  x%d  lines %s" % (fn, short(a, 80), len(places), ", ".join(where(f, n) for f, n in places)))
    md.append("  none" if not data["identical"] else "")
    md.append("Calls made inside a loop: %s" % (", ".join("%s(...) at %s, loop at line %d" % (fn, where(f, n), start)
                                                            for f, n, fn, start in data["in_loop"]) or "none"))
    md.append("Logging calls: %d, on lines %s" % (len(data["log"]), spans(n for _, n in data["log"]) if not many
                                                   else ", ".join(where(f, n) for f, n in data["log"])))
    md.append("Comment lines that look like code (commented-out code): %d, on lines %s"
              % (len(data["commented_code"]), spans(n for _, n, _ in data["commented_code"]) if not many
                 else ", ".join(where(f, n) for f, n, _ in data["commented_code"])))
    if data["commented_code"]:
        md.append("  Each of them, with its text (the block \"### commented-out code\" takes them all out, less \"except:\"):")
        md += ["    %s  %s" % (where(f, n), short(text.strip(), 110)) for f, n, text in data["commented_code"]]
    if data["labels"]:
        md.append("  The comment lines right above them, which may only label them (\"labels:\" in the block takes out")
        md.append("  those you name with the code under them; a heading or one that explains code that stays is kept):")
        md += ["    %s  %s" % (where(f, n), short(text, 110)) for f, n, text in data["labels"]]
    md.append("Names assigned and never read: %s" % (", ".join("%s (line %s)" % (note.split(" (")[0].split(" — ")[0], where(f, n))
                                                               for f, n, note in data["unread"]) or "none"))
    for key, title in (("dupbranch", "Branches with the same statements"), ("repeat", "Same condition twice in one chain")):
        hits = sorted(set(scan.hits[key]))
        if hits:
            md.append("%s: %s" % (title, "; ".join("line %s %s" % (where(f, n), note) for f, n, note in hits)))
    md.append("")
    return "\n".join(md)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("code")
    ap.add_argument("--out", required=True, help="folder for the changed copy")
    ap.add_argument("--report", required=True, help="the report of the change to write (Markdown)")
    ap.add_argument("--notes", help="the plan (default: next to the report, <report>.notes.md)")
    ap.add_argument("--command", help="the command to show in the notes file as the one to run again")
    ap.add_argument("--force", action="store_true", help="replace a file at --report that is not a report of this script")
    ap.add_argument("--hash-comments", action="store_true", help="# starts a comment")
    args = ap.parse_args()

    src, out, report = Path(args.code), Path(args.out), Path(args.report)
    if out.resolve() == src.resolve() or (src.is_file() and out.resolve() == src.resolve().parent):
        raise SystemExit("--out must be a different folder from the one that holds the original")
    if src.is_dir() and out.resolve().is_relative_to(src.resolve()):
        raise SystemExit("--out must not be inside the folder of the original")
    earlier = report.read_text(encoding="utf-8", errors="replace") if report.exists() else ""
    if earlier and not args.force and not earlier.lstrip().startswith(TITLE):
        raise SystemExit("%s exists and is not a report written by this script. Name another file, or pass --force." % report)
    notes_at = Path(args.notes) if args.notes else notes_file.notes_path(report)
    command = args.command or "python3 %s %s --out %s --report %s" % (sys.argv[0], args.code, args.out, args.report)

    scan, files = scan_code.run([src], args.hash_comments)
    if not files:
        raise SystemExit("no code found in %s" % src)
    data = inventory.read(src, args.hash_comments)
    notes = notes_file.read(notes_at)
    first_run = not notes["exists"]
    problems = list(notes["problems"])
    by_name = {Path(str(f)).name: str(f) for f in files}
    one = str(files[0]) if len(files) == 1 else None

    def file_of(block, label):
        name = by_name.get(Path(block["file"]).name) if block.get("file") else one
        if name is None:
            problems.append("%s: say which file, as in \"### rules.js: %d\"." % (label, block.get("first", 0)))
        return name

    # ---- corrections, insertions and rules, by file and original line
    replace = defaultdict(dict)                  # file -> first line -> (last line, new lines, block)
    inserts = defaultdict(lambda: defaultdict(list))   # file -> line -> new lines after it
    rules = []
    for b in notes["corrections"]:               # "### commented-out code": the lines the facts list, less "except:"
        if b["type"] != "commented":
            continue
        label = "the block \"commented-out code\" (line %d of the notes)" % b["at"]
        name = file_of(b, label)
        if name is None:
            continue
        if not (b.get("remove") or "").strip().lower().startswith(("all", "y", "t")):
            problems.append("%s: write \"remove: all\", and list under \"except:\" the lines to keep." % label)
            b["type"] = "skip"
            continue
        keep = notes_file.ranges(b.get("except") or "") if (b.get("except") or "").strip() else []
        if (b.get("except") or "").strip() and keep is None:
            problems.append("%s: \"except:\" must be line numbers such as 523, 1898-1899." % label)
            b["type"] = "skip"
            continue
        kept = {n for x, y in keep or [] for n in range(x, y + 1)}
        listed = sorted(n for f, n, _ in data["commented_code"] if f == Path(name).name)
        wrong = sorted(kept - set(listed))
        if wrong:
            problems.append("%s: \"except:\" names line(s) %s, which the facts do not list as commented-out code."
                            % (label, spans(wrong)))
        chosen = [n for n in listed if n not in kept]
        if not chosen:
            problems.append("%s: no line is left to take out." % label)
            b["type"] = "skip"
            continue
        named = (b.get("labels") or "").strip()      # "labels:": the comment lines above the code that only label it
        offered = {n for f, n, _ in data["labels"] if f == Path(name).name}
        above = set()                                # those right above a line that goes
        for n in chosen:
            k = n - 1
            while k in offered:
                above.add(k)
                k -= 1
        if named and named.lower() not in ("none", "no"):
            asked = notes_file.ranges(named)
            if asked is None:
                problems.append("%s: \"labels:\" must be line numbers such as 221, 760: name each label that goes, "
                                "since some of those lines may explain code that stays." % label)
                b["type"] = "skip"
                continue
            asked = {n for x, y in asked for n in range(x, y + 1)}
            if asked - offered:
                problems.append("%s: \"labels:\" names line(s) %s, which the facts do not list as a comment above "
                                "commented-out code." % (label, spans(sorted(asked - offered))))
            if (asked & offered) - above:
                problems.append("%s: \"labels:\" names line(s) %s, but the code under them stays (\"except:\"): keep "
                                "them too." % (label, spans(sorted((asked & offered) - above))))
            chosen += sorted(asked & above)
        chosen = sorted(set(chosen))
        parts, start = [], chosen[0]
        for x, y in zip(chosen, chosen[1:] + [None]):
            if y != x + 1:
                parts.append((start, x))
                start = y
        b.update(type="lines", parts=parts, first=parts[0][0], last=parts[0][1], remove="yes")
    for b in notes["rules"] + notes["corrections"]:
        at = "line %d of the notes" % b["at"]
        if b["type"] == "skip":
            continue
        if b["type"] == "rule":
            if not b.get("match") or "with" not in b:
                problems.append("rule %s (%s): needs \"match:\" and \"with:\"." % (b["name"], at))
                continue
            for key in ("match", "with"):             # a value in backticks keeps the spaces at its ends
                if len(b[key]) >= 2 and b[key].startswith("`") and b[key].endswith("`"):
                    b[key] = b[key][1:-1]
            try:
                pattern = re.compile(b["match"])
            except re.error as e:
                problems.append("rule %s (%s): the regular expression is not valid: %s." % (b["name"], at, e))
                continue
            where = notes_file.ranges(b["lines"]) if b.get("lines") else None
            if b.get("lines") and where is None:
                problems.append("rule %s (%s): \"lines:\" must be ranges such as 1-200, 350." % (b["name"], at))
                continue
            if len(b.get("why", "")) < 15:
                problems.append("rule %s (%s): \"why:\" is missing or too short." % (b["name"], at))
                continue
            rules.append((b["name"], pattern, b["with"], where, b))
            continue
        label = "the %s for line %d (%s)" % ("insertion" if b["type"] == "insert" else "correction", b["first"], at)
        name = file_of(b, label)
        if name is None:
            continue
        total = len(scan.lines[name]) - (1 if scan.lines[name] and scan.lines[name][-1] == "" else 0)
        if not 0 < b["first"] <= b["last"] <= total:
            problems.append("%s: %s has %d lines." % (label, Path(name).name, total))
            continue
        if len(b.get("why", "")) < 15:
            problems.append("%s: \"why:\" is missing or too short. Say what asks for it and what stays the same." % label)
            continue
        if b["type"] == "insert":
            if not b.get("insert"):
                problems.append("%s: \"insert:\" is missing: give the new lines." % label)
                continue
            inserts[name][b["first"]] += b["insert"]
            continue
        removes = (b.get("remove") or "").strip().lower().startswith(("y", "t"))
        new = b.get("after") or []
        if not new and not removes:
            problems.append("%s: \"after:\" is missing. Give the new line, or \"remove: yes\"." % label)
            continue
        parts = b.get("parts") or [(b["first"], b["last"])]
        if len(parts) > 1 and not removes:
            problems.append("%s: a list of lines can only be removed (\"remove: yes\"). To replace lines, write one "
                            "block for each run of lines." % label)
            continue
        if any(not 0 < a <= z <= total for a, z in parts):
            problems.append("%s: %s has %d lines." % (label, Path(name).name, total))
            continue
        if any(first <= z and a <= last for a, z in parts for first, (last, _, _) in replace[name].items()):
            problems.append("%s: another correction already covers one of these lines." % label)
            continue
        for a, z in parts:
            replace[name][a] = (z, [] if removes else new, b)

    # ---- a comment that explains the live line under it is not commented-out code: it stays with that line
    for name in replace:
        base = Path(name).name
        gone = {n for first, (last, new, _) in replace[name].items() if not new for n in range(first, last + 1)}
        listed = {n for f, n, _ in data["commented_code"] if f == base}
        notes_at_line = data["comment_at"].get(base, set())
        lines = scan.lines[name]
        blank = lambda n: not lines[n - 1].strip()
        for end in sorted(n for n in gone if n + 1 not in gone):
            prose, n = [], end                   # the comment lines at the foot of the removed run, nearest first
            while n in gone and (blank(n) or (n in notes_at_line and n not in listed)):
                if not blank(n):
                    prose.append(n)
                n -= 1
            nxt = end + 1
            while nxt <= len(lines) and blank(nxt):
                nxt += 1
            if prose and nxt <= len(lines) and nxt not in gone and nxt not in notes_at_line:
                problems.append("%s: line(s) %s are a comment, not commented-out code, and stand right above line %d, "
                                "which is live code that stays (%s). Such a comment explains that code: keep it, and "
                                "take the line(s) out of the removal."
                                % (Path(name).name, spans(sorted(prose)), nxt, short(lines[nxt - 1].strip(), 70)))

    # ---- copies: a block copied under a new name, and every other line that names the model, with only the
    # replacements the plan lists. Nothing else in the copy can differ from the model.
    copies = defaultdict(list)                   # file -> [(after line, new lines, source lines, block)]
    first_of = {}                                # the model or the new name -> the block that copies it first
    for b in notes["copies"]:
        label = "copy %s as %s (line %d of the notes)" % (b["old"], b["new"], b["at"])
        twice = [first_of[k] for k in (("model", b["old"].lower()), ("new", b["new"].lower())) if k in first_of]
        if twice:                                # one block copies every line that names the model
            problems.append("%s: the block on line %d of the notes already copies %s as %s, with every line that names "
                            "%s. One block for each new item: take this one out." % (label, twice[0]["at"], twice[0]["old"],
                                                                               twice[0]["new"], twice[0]["old"]))
            continue
        first_of.setdefault(("model", b["old"].lower()), b)
        first_of.setdefault(("new", b["new"].lower()), b)
        m = re.match(r"^\s*(?:(?P<file>[^:\s]+\.\w+)\s*:\s*)?(?P<r>.+)$", b.get("lines", ""))
        where = notes_file.ranges(m.group("r")) if m else None
        if not where or len(where) != 1:
            problems.append("%s: \"lines:\" must be the one run of lines to copy, such as 95-103." % label)
            continue
        name = by_name.get(Path(m.group("file")).name) if m.group("file") else one
        if name is None:
            problems.append("%s: say which file, as in \"lines: page.html: 95-103\"." % label)
            continue
        if len(b.get("why", "")) < 15:
            problems.append("%s: \"why:\" is missing or too short. Say what asks for the copy." % label)
            continue
        lines = [l.rstrip("\r") for l in scan.lines[name]]
        total = len(lines) - (1 if lines and lines[-1] == "" else 0)
        a, z = where[0]
        if not 0 < a <= z <= total:
            problems.append("%s: %s has %d lines." % (label, Path(name).name, total))
            continue
        pairs, bad = [(b["old"], b["new"])], False
        for row in b.get("replace") or []:
            parts = re.split(r"\s+(?:->|=>|→)\s+", row.strip(), maxsplit=1)
            parts = [p.strip()[1:-1] if len(p.strip()) >= 2 and p.strip()[0] == p.strip()[-1] == "`" else p.strip()
                     for p in parts]
            if len(parts) != 2 or not parts[0] or parts[0] == parts[1]:
                problems.append("%s: \"%s\" under \"replace:\" is not \"old -> new\"." % (label, row.strip()))
                bad = True
            elif tuple(parts) in pairs:          # the same pair twice, such as the one of the header: once is enough
                continue
            elif parts[0] in dict(pairs):
                problems.append("%s: \"%s\" is replaced twice." % (label, parts[0]))
                bad = True
            else:
                pairs.append((parts[0], parts[1]))
        if bad:
            continue
        table = dict(pairs)
        alt = re.compile(r"(?<![A-Za-z0-9_])(%s)" % "|".join(re.escape(x) for x, _ in sorted(pairs, key=lambda p: -len(p[0]))))
        model = re.compile(r"(?<![A-Za-z0-9_])%s" % re.escape(b["old"]))
        skip = {n for r in (notes_file.ranges(b["except"]) or []) for n in range(r[0], r[1] + 1)} if b.get("except") else set()
        if not any(model.search(l) for l in lines[a - 1:z]):
            problems.append("%s: lines %s do not name %s." % (label, span(a, z), b["old"]))
            continue
        uneven = whole_block("\n".join(lines[a - 1:z]))
        if uneven:                               # a copy of half a block breaks the page or the code
            problems.append("%s: lines %s are not a whole block: %s. Start the block at the line that opens it and "
                            "end it at the line that closes it." % (label, span(a, z), uneven))
            continue
        decided = "".join([r for r in b.get("replace") or []] + [b.get("keep") or ""]).replace(" ", "")
        pre = dict(pairs)                        # the line that names the item: the shortest line the copy changes
        pre_alt = re.compile(r"(?<![A-Za-z0-9_])(%s)" % "|".join(re.escape(x) for x, _ in sorted(pairs, key=lambda p: -len(p[0]))))
        named = [(len(lines[n - 1].strip()), n - a) for n in range(a, z + 1)
                 if pre_alt.sub(lambda mm: pre[mm.group(1)], lines[n - 1]) != lines[n - 1]]
        k0 = min(named)[1] if named else None
        grow = (len(pre_alt.sub(lambda mm: pre[mm.group(1)], lines[a - 1 + k0]).strip()) - len(lines[a - 1 + k0].strip())) \
            if k0 is not None else 0
        for prop, here, others, rec in varying_styles(lines[:total], a, z, k0, grow):
            if rec is not None and rec != here:
                if "%s:%s->%s:%s" % (prop, here, prop, rec) not in decided:
                    problems.append("%s: the model's %s:%s fits its own name; the items whose name is as long as the new "
                                    "one's use %s:%s (all values: %s). Put \"%s:%s -> %s:%s\" under \"replace:\"."
                                    % (label, prop, here, prop, rec, others, prop, here, prop, rec))
            elif rec is None and prop + ":" + here not in decided:
                problems.append("%s: the model's %s:%s differs between the items made like it (%s). If it fits the name "
                                "(a label of another length), take the value of an item with a name as long as the new "
                                "one under \"replace:\" (%s:%s -> %s:<value>); if the model's value is right for the new "
                                "item, name it under \"keep:\"." % (label, prop, here, others, prop, here, prop))
        sources = list(range(a, z + 1)) + [n for n in range(1, total + 1)
                                           if not a <= n <= z and n not in skip and model.search(lines[n - 1])]
        made = {n: alt.sub(lambda mm: table[mm.group(1)], lines[n - 1]) for n in sources}
        used = {mm.group(1) for n in sources for mm in alt.finditer(lines[n - 1])}
        for x, y in pairs:
            if x not in used:
                problems.append("%s: \"%s -> %s\" changes no line of the copy." % (label, x, y))
        keep = [k.strip().strip("`") for k in re.split(r",\s*", b.get("keep") or "") if k.strip()]
        for n in sources:                        # what the copy still holds of the model, in any letter case
            rest = made[n]
            for y in sorted(set(table.values()) | set(keep), key=len, reverse=True):
                rest = rest.replace(y, " " * len(y)) if y else rest
            held = [x for x, _ in pairs if x in rest]
            held += [m.group(0) for m in re.finditer(re.escape(b["old"]), rest, re.I) if m.group(0) not in held]
            if held:
                problems.append("%s: the copy of line %d still holds %s: `%s`. Add a replacement for it under "
                                "\"replace:\", or name the text that is meant to stay under \"keep:\"."
                                % (label, n, ", ".join("\"%s\"" % x for x in held), short(made[n].strip(), 90)))
        whole = "\n".join(lines[:total])
        for x, y in pairs:                       # the names of the copy are new to the code; a style value is no name
            if STYLE.fullmatch(x.replace(" ", "")) and STYLE.fullmatch(y.replace(" ", "")):
                continue
            hit = re.search(r"(?<![A-Za-z0-9_])%s" % re.escape(y), whole)
            if y.strip() and hit and not any(y in k for k in keep):
                problems.append("%s: \"%s\" is already in the code (line %d), so the copy would share it with what "
                                "is there. Choose a name the code does not use, or name it under \"keep:\" if it is "
                                "meant to be shared." % (label, y, whole.count("\n", 0, hit.start()) + 1))
        copies[name].append((z, [made[n] for n in range(a, z + 1)], list(range(a, z + 1)), b))
        for n in sources[z - a + 1:]:
            copies[name].append((n, [made[n]], [n], b))

    # ---- renames: names only, no clash with a name the code already uses
    renames = {}
    all_names = {k for k in set(scan.reads) | set(scan.assigns) if scan.reads.get(k) or scan.assigns.get(k)}
    not_proposed = []
    wanted = dict(notes["renames"])
    given, unread = outside_names(scan)
    if notes["accept_proposals"]:
        accepted, not_proposed = mechanical(scan, wanted)
        wanted.update(accepted)
    for old, new in wanted.items():
        if (old[0] in scan_code.SIGILS) != (new[0] in scan_code.SIGILS):
            problems.append("rename %s -> %s: both names must have the same prefix, or none." % (old, new))
        elif new in all_names and new not in wanted:
            problems.append("rename %s -> %s: the code already uses %s for something else." % (old, new, new))
        elif list(wanted.values()).count(new) > 1:
            problems.append("rename %s -> %s: two names are renamed to %s." % (old, new, new))
        elif old not in all_names and not any(old == m[1:] for m in scan.members):
            problems.append("rename %s -> %s: the code does not use the name %s." % (old, new, old))
        elif old in given:
            problems.append("rename %s -> %s: this code never gives %s a value, so something outside provides it "
                            "under that name. It cannot be renamed here." % (old, new, old))
        elif old in read_first(scan):
            problems.append("rename %s -> %s: the code reads %s before the line that first gives it a value. Either its "
                            "first value comes from outside under that name, or the code uses it too early, which is a "
                            "defect to settle first. Leave it, and ask the owner." % (old, new, old))
        elif old in unread:
            problems.append("rename %s -> %s: nothing in this code reads %s. If it is in use, another component reads "
                            "it under that name, and a rename would break that. Leave it, and ask the owner." % (old, new, old))
        else:
            renames[old] = new

    # ---- the new text of every original line
    out_lines = {}                               # file -> {original line: [new lines]}
    rows = []                                    # the table of corrections
    rule_hits = defaultdict(list)                # rule name -> [(file, line, before, after)]
    rename_hits = defaultdict(int)               # old name -> lines changed
    renamed_lines = set()                        # (file, original line, part): each line a rename changed, once
    for f in files:
        name = str(f)
        text_lines = scan.lines[name]
        total = len(text_lines) - (1 if text_lines and text_lines[-1] == "" else 0)
        style = scan.styles[name]
        current = {}
        n = 1
        while n <= total:
            if n in replace[name]:
                last, new, b = replace[name][n]
                first_line = text_lines[n - 1]
                indent = first_line[:len(first_line) - len(first_line.lstrip())]
                new_lines = [(indent + l if l.strip() else "") for l in new]
                old_lines = [l.rstrip("\r") for l in text_lines[n - 1:last]]
                kind = b.get("kind") or ("Lines removed" if not new else "Replaced")
                why = b.get("why", "")
                if not new:                      # a removal accounts for everything the lines held
                    why = ("%s %s" % (why, scan_code.account_of("\n".join(old_lines), style))).strip()
                for k in range(max(len(old_lines), len(new_lines))):
                    rows.append((name, n + k if k < len(old_lines) else None, kind,
                                 old_lines[k] if k < len(old_lines) else None,
                                 new_lines[k] if k < len(new_lines) else None, why, k == 0))
                current[n] = new_lines
                for k in range(n + 1, last + 1):
                    current[k] = []
                n = last + 1
                continue
            current[n] = [text_lines[n - 1].rstrip("\r")]
            n += 1
        for n, new in inserts[name].items():
            first_line = text_lines[n - 1]
            indent = first_line[:len(first_line) - len(first_line.lstrip())]
            added = [(indent + l if l.strip() else "") for l in new]
            current[n] = current.get(n, []) + added
            for k, l in enumerate(added):
                rows.append((name, None if k else n, "Inserted after line %d" % n, None, l,
                             next(b.get("why", "") for b in notes["corrections"] if b["type"] == "insert" and b["first"] == n), k == 0))
        for n, new, sources, b in copies[name]:  # a copy keeps the indentation of the line it copies
            current[n] = current.get(n, []) + new
            for k, l in enumerate(new):
                rows.append((name, None if k else n, "Copy of line %d (copy %s as %s)" % (sources[k], b["old"], b["new"]),
                             None, l, b.get("why", ""), k == 0))
        for rule_name, pattern, with_, where, b in rules:
            for n in sorted(current):
                if where and not any(a <= n <= z for a, z in where):
                    continue
                changed = []
                for l in current[n]:
                    try:
                        new_l = pattern.sub(with_, l)
                    except re.error as e:
                        problems.append("rule %s: the replacement is not valid: %s." % (rule_name, e))
                        new_l = l
                    if new_l != l:
                        rule_hits[rule_name].append((name, n, l, new_l))
                    changed.append(new_l)
                current[n] = changed
        if renames:
            for n in sorted(current):
                for i, l in enumerate(current[n]):
                    new_l = trace_code.rename_names(l, style, renames)
                    if new_l != l:
                        current[n][i] = new_l
                        renamed_lines.add((name, n, i))
                        for old in renames:
                            if re.search(r"(?<![\w@$%%])%s(?!\w)" % re.escape(old), l):
                                rename_hits[old] += 1
        out_lines[name] = current
    for rule_name, _, _, _, b in rules:
        if not rule_hits[rule_name]:
            problems.append("rule %s (line %d of the notes): changes no line. Check the regular expression." % (rule_name, b["at"]))
    for old in renames:
        if not rename_hits[old]:
            problems.append("rename %s -> %s: changes no line (the name may only appear after a dot or inside strings)."
                            % (old, renames[old]))

    # ---- the files of the result
    outputs = {}                                 # relative path -> (list of lines, encoding, ending, source file)
    placed = defaultdict(set)                    # file -> original lines that landed somewhere
    file_rows = []
    late = []                                    # (label, source, gaps between its ranges, last line) of a file with "append:"
    if notes["files"] and src.is_file():
        beside = [f for f in scan_code.collect([src.parent]) if f.resolve() != src.resolve()
                  and out.resolve() not in f.resolve().parents]      # the copy itself may lie in that folder
        if beside:
            problems.append("the code given is one file of %s, which holds %d more: %s. A split of one file leaves them out "
                            "of the new structure. Run the command with the folder as the code, and give each of them its "
                            "place (\"lines: <file>: all\" takes a whole file)."
                            % (src.parent, len(beside), ", ".join(str(f.relative_to(src.parent)) for f in beside[:8])))
    if notes["files"]:
        for b in notes["files"]:
            label = "the file %s (line %d of the notes)" % (b["path"], b["at"])
            if ".." in Path(b["path"]).parts or Path(b["path"]).is_absolute():
                problems.append("%s: the path must be relative, inside the output folder." % label)
                continue
            spec = (b.get("lines") or "").strip()
            named = re.match(r"^([^\s:,][^:,]*?)\s*:\s*(.*)$", spec)      # "rules.js: 1-20, 40-60" names its earlier file
            if named and not re.match(r"^\d", named.group(1)):
                b["file"] = named.group(1).strip()
                spec = re.sub(r"%s\s*:" % re.escape(b["file"]), "", named.group(2)).strip()
                if by_name.get(Path(b["file"]).name) is None:
                    problems.append("%s: %s is not one of the earlier files (%s)." % (label, b["file"], ", ".join(sorted(by_name))))
                    continue
            source = file_of(b, label) if (b.get("file") or one) else None
            if spec.lower() in ("all", "all lines", "the whole file") and source is not None:
                where = [(1, len(scan.lines[source]) - (1 if scan.lines[source][-1] == "" else 0))]
            else:
                where = notes_file.ranges(spec) if spec else []
            if where is None:
                problems.append("%s: \"lines:\" must be ranges of the earlier code such as 1-57, 3100-3338, or \"all\"; with "
                                "several earlier files, the name of the file first, as in \"rules.js: 1-57, 3100-3338\"." % label)
                continue
            if source is None and where:
                # a split of a folder: the ranges name their file as "rules.js: 1-20"
                problems.append("%s: with several earlier files, write the ranges as \"file.ext: 1-20\"." % label)
                continue
            if not where and not (b.get("prepend") or b.get("append")):
                problems.append("%s: the file would be empty. Give the earlier lines it takes with \"lines:\", or, for a file "
                                "that holds no earlier line, its content with \"prepend:\"." % label)
                continue
            if source is None:                       # a new file that holds no earlier line: written like the first one
                source = str(files[0])
            for (a1, z1), (a2, z2) in zip(where, where[1:]):
                if a2 <= z1 and not re.search(r"(?<!\d)%s(?!\d)" % re.escape(span(a2, z2)), notes["explanations"] or ""):
                    problems.append("%s: lines %s are placed after lines %s, which they used to come before. Keep the order "
                                    "the lines had, or say under \"Explanations\", naming \"%s\", why the order does not "
                                    "matter." % (label, span(a2, z2), span(a1, z1), span(a2, z2)))
            code_like = [l for l in (b.get("append") or []) if l.strip() and not l.lstrip().startswith(("#", "//", "--", "/*", "*"))]
            if code_like and source is not None:
                late.append((label, source, [(z1 + 1, a2 - 1) for (a1, z1), (a2, z2) in zip(where, where[1:]) if a2 > z1 + 1],
                             where[-1][0] if where else 0))
            lines_out = list(b.get("prepend") or [])
            held = []
            for a, z in where:
                total = len(scan.lines[source]) - (1 if scan.lines[source][-1] == "" else 0)
                if not 0 < a <= z <= total:
                    problems.append("%s: the range %s is outside %s (%d lines)." % (label, span(a, z), Path(source).name, total))
                    continue
                for n in range(a, z + 1):
                    lines_out += out_lines[source][n]
                    placed[source].add(n)
                held.append(span(a, z))
            lines_out += list(b.get("append") or [])
            if b["path"] in outputs:
                problems.append("%s: two blocks write the same file." % label)
                continue
            outputs[b["path"]] = (lines_out, scan.encoding[source], "\r\n" if "\r\n" in scan.text[source] else "\n", source)
            file_rows.append((b["path"], ", ".join(held), len(lines_out), len(b.get("prepend") or []) + len(b.get("append") or []),
                              b.get("why", "")))
        for label, source, gaps, last_start in late:
            # new lines at the end of a file come after its last range: if the lines between its ranges went to
            # other files, the lines that read those files must stand where the gap is, not at the end
            elsewhere = [(a, z) for a, z in gaps if any(n in placed[source] for n in range(a, z + 1))]
            if elsewhere:
                problems.append("%s: its \"append:\" lines come after its last range, but lines %s, which used to stand "
                                "before that range, are now in other files. If the new lines read or call those files, "
                                "they do it too late. Write them where the lines stood, as an insertion (\"### after line "
                                "%d\" with \"insert:\"), and keep \"append:\" for a closing comment."
                                % (label, ", ".join(span(a, z) for a, z in elsewhere), elsewhere[0][0] - 1))
        for f in files:
            name = str(f)
            total = len(scan.lines[name]) - (1 if scan.lines[name][-1] == "" else 0)
            removed = {n for first, (last, new, _) in replace[name].items() for n in range(first, last + 1) if not new}
            missing = sorted(set(range(1, total + 1)) - placed[name] - removed)
            missing = [n for n in missing if scan.lines[name][n - 1].strip()]      # an empty line needs no home
            if missing:
                problems.append("%d line(s) of %s are in no file and not removed: lines %s. Add them to a file, or remove "
                                "them with a correction that says why." % (len(missing), Path(f).name, spans(missing)))
    else:
        for f in files:
            name = str(f)
            rel = Path(f).name if src.is_file() else str(Path(f).relative_to(src))
            total = len(scan.lines[name]) - (1 if scan.lines[name][-1] == "" else 0)
            lines_out = [l for n in range(1, total + 1) for l in out_lines[name][n]]
            outputs[rel] = (lines_out, scan.encoding[name], "\r\n" if "\r\n" in scan.text[name] else "\n", name)

    # ---- write the copy: nothing before everything is worked out
    written = {}
    for rel, (lines_out, encoding, ending, source) in outputs.items():
        target = out / rel
        trailing = ending if scan.text[source].endswith("\n") else ""
        try:
            data_bytes = (ending.join(lines_out) + trailing).encode(encoding)
        except UnicodeEncodeError as e:
            raise SystemExit("A line in the plan holds a character that %s cannot hold in its encoding (%s): %s"
                             % (rel, encoding, e))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data_bytes)
        written[rel] = data_bytes
    if notes["files"] and len(written) > 1:      # a file of a split that no other file of the result names
        texts = {rel: data_bytes.decode("utf-8", errors="replace") for rel, data_bytes in written.items()}

        def names(text, rel):
            return Path(rel).name in text or bool(re.search(r"(?<![\w.])%s(?![\w.])" % re.escape(Path(rel).stem), text))

        for rel in written:
            read_by_another = any(o != rel and names(text, rel) for o, text in texts.items())
            reads_another = any(o != rel and names(texts[rel], o) for o in written)
            if not read_by_another and not reads_another and rel not in (notes["explanations"] or ""):
                problems.append("nothing in the result reads %s: no other file names it. Add the line that reads it, at "
                                "the place where its lines stood, or say under \"Explanations\", naming the file, what "
                                "reads it." % rel)
    stale = [p for p in out.rglob("*") if p.is_file() and str(p.relative_to(out)) not in written
             and not p.name.startswith(".")]
    for p in stale:
        p.unlink()                               # a file of an earlier plan that this plan no longer writes
    after_scan, _ = scan_code.run([out], args.hash_comments, documents=[Path(d) for d in scan.docs])

    # ---- the report
    changed_lines = sum(1 for r in rows if r[6]) + sum(len(v) for v in rule_hits.values())
    md = [TITLE + ", ".join(Path(a).name for a in [src]), "",
          "Written by the change script from the plan in %s. Do not edit this file or the copy under %s: change the "
          "plan and run the script again." % (notes_at.name, out), "", "## Verdict"]
    if notes["verdict"]:
        md += [notes["verdict"], ""]
    copied = [r for r in rows if r[2].startswith("Copy of line")]
    md += ["The plan has %d correction(s), %s%d rule(s) that changed %d line(s), %d rename(s) applied on %d line(s), and "
           "%d file(s) written%s. The original is unchanged."
           % (sum(1 for r in rows if r[6]) - sum(1 for r in copied if r[6]),
              "%d copy(ies) that wrote %d line(s), " % (len(notes["copies"]), len(copied)) if notes["copies"] else "",
              len(rules), sum(len(v) for v in rule_hits.values()), len(renames),
              len(renamed_lines), len(outputs), " as a split of the code" if notes["files"] else ""), "",
           "## Changes made",
           "| # | File | Line | Kind | Before | After | Why: the requirement, and what stays the same |",
           "|---|---|---|---|---|---|---|"]
    k = 0
    for name, line, kind, before, after, why, first in rows:
        k += first
        md.append("| E-%02d | %s | %s | %s | %s | %s | %s |" % (
            k, Path(name).name, line or "", plain(kind), cell(before) if before is not None else "(no line)",
            cell(after) if after is not None else "(removed)", plain(why) if first else "As above."))
    md += ["", "## Rules applied", "| Rule | Match | With | Lines changed | Example before | Example after | Why |",
           "|---|---|---|---|---|---|---|"]
    for rule_name, pattern, with_, where, b in rules:
        hits = rule_hits[rule_name]
        md.append("| %s | %s | %s | %d%s | %s | %s | %s |" % (
            plain(rule_name), cell(pattern.pattern), cell(with_), len(hits),
            " (on lines %s)" % spans(n for _, n, _, _ in hits) if hits and len(files) == 1 else "",
            cell(hits[0][2]) if hits else "", cell(hits[0][3]) if hits else "", plain(b.get("why", ""))))
    # a rule states its change and its reason once; the strings it rewrote are listed here, so that the rule
    # accounts for them by itself, as a removal does for the lines it takes out
    rewrote = []
    for rule_name, _, _, _, b in rules:
        for fname, n, before, after in rule_hits[rule_name]:
            was, now = STRING.findall(before), STRING.findall(after)
            for x, y in zip(was, now):
                if x != y:
                    rewrote.append("- rule %s, line %d: the string %s became %s" % (plain(rule_name), n, x, y))
            if len(was) != len(now):
                rewrote.append("- rule %s, line %d: `%s` became `%s`" % (plain(rule_name), n, before.strip(), after.strip()))
    if rewrote:
        md += ["", "Strings the rules rewrote (%d). Each is the work of its rule, for the reason the rule gives:" % len(rewrote), ""]
        md += rewrote
    if notes["copies"]:
        md += ["", "## Copies made", "| Copy | Lines of the model copied | Lines written | Replacements | Why |", "|---|---|---|---|---|"]
        wrote = []
        for b in notes["copies"]:
            placed_ = [(name, n, new, sources) for name in copies for n, new, sources, c in copies[name] if c is b]
            if not placed_:
                continue
            reps = ["%s -> %s" % (b["old"], b["new"])] + [r.strip() for r in b.get("replace") or [] if r.strip()]
            md.append("| %s as %s | %s | %d | %s | %s |" % (
                plain(b["old"]), plain(b["new"]), spans(s for _, _, _, sources in placed_ for s in sources),
                sum(len(new) for _, _, new, _ in placed_), cell("; ".join(reps)), plain(b.get("why", ""))))
            for name, n, new, sources in placed_:
                for s, l in zip(sources, new):
                    model_line = scan.lines[name][s - 1].rstrip("\r")
                    for x, y in zip(STRING.findall(model_line), STRING.findall(l)):
                        wrote.append("- copy %s as %s, line %d: the string %s %s" % (
                            plain(b["old"]), plain(b["new"]), s, x, "is repeated" if x == y else "became %s" % y))
        if wrote:
            md += ["", "Strings the copies wrote (%d). Each is the string of the model line, with only the replacements "
                   "of its copy:" % len(wrote), ""] + wrote
        calls = defaultdict(int)                 # the calls a copy repeats are those of its model lines
        for name in copies:
            for _, new, _, _ in copies[name]:
                for l in new:
                    for c in re.findall(r"(?<![\w$])([A-Za-z_]\w*)\s*\(", STRING.sub('""', l)):
                        if c.lower() not in scan_code.KEYWORDS:
                            calls[c] += 1
        if calls:
            md += ["", "Calls the copies repeat, as their model lines make them: %s." % ", ".join(
                "`%s` (%d)" % (c, k) for c, k in sorted(calls.items()))]
    md += ["", "## Renames applied", "| Old | New | Lines changed |", "|---|---|---|"]
    md += ["| `%s` | `%s` | %d |" % (old, new, rename_hits[old]) for old, new in renames.items()]
    if not_proposed:
        md += ["", "Not renamed, because the camelCase form would clash with another name: %s. Give these a name of "
               "their own under \"Renames\" if they are to be renamed." % ", ".join(
                   "`%s` (-> %s)" % (k, new) for k, new in not_proposed)]
    if notes["files"]:
        md += ["", "## Files written", "| File | Earlier lines it holds | Lines | New lines (prepend + append) | What it holds |",
               "|---|---|---|---|---|"]
        md += ["| %s | %s | %d | %d | %s |" % (p, held, n, extra, plain(why)) for p, held, n, extra, why in file_rows]
    if notes["coverage"]:
        md += ["", "## Coverage of the requirement", "| What the document asks for | What the plan does |", "|---|---|"]
        md += ["| %s | %s |" % (plain(a), plain(b)) for a, b in notes["coverage"]]
    md += ["", "## Explanations of the differences the gate lists"]
    md += [notes["explanations"] or "None yet."]
    md += ["", "## Checks performed", "| Check | How it was checked | Before | After |", "|---|---|---|---|"]
    for key, title, _ in scan_code.CHECKS:
        b_, a_ = len(set(scan.hits[key])), len(set(after_scan.hits[key]))
        if b_ or a_:
            md.append("| %s | scan_code.py, original and copy | %d | %d%s |" % (plain(title), b_, a_, " (went up)" if a_ > b_ else ""))
    md += ["", "## Not checked", "- Nothing was run. The change is a change to the text of the code."]
    md += ["- %s" % x for x in notes["not_checked"]]
    md += ["", "## Questions for the owner of the code"]
    md += ["%d. %s" % (i, q) for i, q in enumerate(notes["questions"], 1)] or ["1. None."]
    md += ["", "<!-- checksum of the copy: %s -->" % " ".join(
        "%s=%s" % (rel, hashlib.sha1(data_bytes).hexdigest()[:12]) for rel, data_bytes in sorted(written.items())), ""]
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(md), encoding="utf-8")
    if first_run:
        notes_at.parent.mkdir(parents=True, exist_ok=True)
        notes_at.write_text(skeleton(report, command, scan, files, data), encoding="utf-8")

    # ---- say where the change stands
    print("Changed copy: %s (%d file(s), written by this command; do not edit it)" % (out, len(outputs)))
    print("Report:       %s (written by this command; do not edit it)" % report)
    print("  %d correction(s); %s%d rule(s) changed %d line(s); %d rename(s) on %d line(s)."
          % (sum(1 for r in rows if r[6]) - sum(1 for r in copied if r[6]),
             "%d copy(ies) wrote %d line(s); " % (len(notes["copies"]), len(copied)) if notes["copies"] else "",
             len(rules), sum(len(v) for v in rule_hits.values()), len(renames), len(renamed_lines)))
    went_up = ["%s %d -> %d" % (title, len(set(scan.hits[key])), len(set(after_scan.hits[key])))
               for key, title, _ in scan_code.CHECKS if len(set(after_scan.hits[key])) > len(set(scan.hits[key]))]
    if went_up:
        print("  Scan counts that went up in the copy: %s" % "; ".join(went_up))
    print("Your plan: %s%s" % (notes_at, " (written now: the form of a plan, and the facts of the code to start from)"
                               if first_run else ""))
    if scan.docs and not first_run:              # what the plan does about each thing the document asks for
        if not notes["coverage"]:
            problems.append("\"Coverage of the requirement\" has no line yet: one line for each thing %s asks of this "
                            "task, with what the plan does about it (done, in part, or not done and what in the files "
                            "prevents it)." % ", ".join(Path(d).name for d in scan.docs))
        for what, state in notes["coverage"]:
            m = COVERED.match(state)
            label = "coverage of \"%s\"" % short(what, 60)
            if not m:
                problems.append("%s: start what the plan does with \"done:\", \"in part:\" or \"not done:\"." % label)
            elif not m.group(2).strip():
                problems.append("%s: say which blocks do it, or what in the files prevents it." % label)
            elif m.group(1).lower() != "done" and WAITING.search(m.group(2)):
                problems.append("%s: waiting for an approval is not a reason, because the document is the owner's "
                                "decision already. Do it in the plan, or say what in the files prevents it." % label)
    if problems:
        print("To correct in the plan:")
        for p in problems:
            print("  - %s" % p)
    empty = not rows and not rules and not renames and not notes["files"]
    if empty and not first_run:
        print("  The plan has no correction, rule, rename or file yet.")
    complete = not problems and not empty
    if complete:
        print("\nResult: complete")
        sys.exit(0)
    print("\nResult: not complete. %s" % ("This is expected on the first run: write the plan in %s." % notes_at if first_run
                                           else "Correct what is listed, in %s." % notes_at))
    sys.exit(0 if first_run else NOT_PASSED)


if __name__ == "__main__":
    main()
