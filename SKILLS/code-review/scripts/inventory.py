#!/usr/bin/env python3
"""Count what is in some code, and list what an optimization would look at.

    python3 inventory.py <code file-or-folder> [<after file-or-folder>]

With one argument, prints the counts and three lists of candidates:

  - repeated calls: the same function called more than once with the same
    first argument (for example several lookups on the same table), and
    identical calls made more than once
  - logging: every logging call, with its line
  - unused: names assigned and never read, and commented-out code

With two arguments, prints the same counts for both versions side by side,
which is the before and after table of an optimization report.

It reads text only. A repeated call is a candidate for merging, not proof
that merging is safe. Python standard library only.
"""
import argparse
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import scan_code  # noqa: E402

CODE_LIKE = re.compile(r"[;{}]\s*$|^\s*(if|else|elseif|elif|for|while|return)\b.*[({:]|\w\s*=(?![=>])\s*\S|\w\(.*\)")


def read(target, hash_comments):
    files = scan_code.collect([target])
    scan = scan_code.Scan()
    scan.add_documents(scan_code.documents_for([target]))
    data = {"lines": 0, "blank": 0, "comment": 0, "commented_code": [], "log": [], "calls": Counter(),
            "same_source": defaultdict(list), "identical": defaultdict(list), "in_loop": [],
            "comment_at": defaultdict(set)}      # file -> the lines that are comments
    kept = []
    scan.learn(files, hash_comments)
    for f in files:
        if not scan.add_file(f, hash_comments):
            continue
        kept.append(f)
        name, style = str(f), scan.styles[str(f)]
        marks = tuple(m for m, on in (("//", style in ("slash", "both")), ("#", style in ("hash", "both")),
                                      ("--", style == "dash")) if on)
        in_block = False
        lines = scan.lines[name][:scan.line_count(name)]
        # what a statement of this code looks like when it is one word, or one word and a string: a comment
        # that holds the same is that statement switched off (#discard, #include "file")
        live = [l.strip() for l in lines if l.strip() and not l.strip().startswith(marks + ("/*", "*"))]
        bare = {m.group(1) for l in live for m in [re.match(r"^([A-Za-z_]\w*);?$", l)] if m}
        starters = {m.group(1) for l in live for m in [re.match(r"^([A-Za-z_]\w*)\s+[\"']", l)] if m}
        # where the code's own variables all carry a prefix, "name = value" with no prefix is an example, not code
        prefixed_only = Path(name).suffix.lower() in scan.body_marked \
            or scan_code.all_prefixed(*scan_code.own_names(scan_code.lex(scan.text[name], style)))
        block, found_here = [], []                 # the lines of the block comment being read: (line, text, is code)
        for n, line in enumerate(lines, 1):
            text = line.strip()
            data["lines"] += 1
            if not text:
                data["blank"] += 1
                continue
            body, in_a_block, closes = None, in_block, False
            if in_block:
                body, in_block = text, "*/" not in text
                closes = not in_block
            elif style != "hash" and text.startswith("/*"):
                body, in_block = text[2:], "*/" not in text
                in_a_block, closes = True, not in_block
            elif text.startswith(marks):
                body = text.lstrip("/#- ")
            if body is not None:
                data["comment"] += 1
                data["comment_at"][f.name].add(n)
                body = body.replace("*/", "").strip()
                word = re.match(r"^([A-Za-z_]\w*)(;?$|\s+[\"'])", body)
                is_code = bool(CODE_LIKE.search(body) or re.match(r"^[{}]", body)
                               or (word and word.group(1) in (bare if word.group(2) in ("", ";") else starters)))
                # a comment sign written twice and then a space opens an explanation, not a line switched off
                # and no statement starts with a number: "1110/01(a=1) or ..." is an example of values
                explains = bool(re.match(r"^(#{2,}|/{3,}|-{3,})\s", text)) or body.lower().startswith(("note", "todo", "see ")) \
                    or bool(re.match(r"^\d", body)) \
                    or (prefixed_only and re.match(r"^[A-Za-z_]\w*\s*=(?!=)", body) and not body.rstrip().endswith((";", "{", "}")))
                is_code = is_code and not explains
                if in_a_block:
                    block.append((n, text, is_code))
                    if closes:                     # the signs that open and close a block of code go with it
                        if any(c for _, _, c in block):
                            found_here += [(f.name, m, s) for m, s, c in block
                                           if c or not re.sub(r"/\*|\*/|[\s{}();*]", "", s)]
                        block = []
                elif is_code:
                    found_here.append((f.name, n, text))
        data["commented_code"] += sorted(found_here, key=lambda r: r[1])
        toks = scan_code.lex(scan.text[name], style)
        loop_of = {}                              # token inside the block of a loop -> line of the loop
        for i, t in enumerate(toks):
            if scan_code.is_word(t, {"while", "until", "for", "foreach", "do"}):
                j = i + 1
                if j < len(toks) and scan_code.is_op(toks[j], "("):
                    j = scan_code.close_of(toks, j) + 1
                if j < len(toks) and scan_code.is_op(toks[j], "{"):
                    for q in range(j, scan_code.close_of(toks, j, "{", "}")):
                        loop_of.setdefault(q, t.line)
        for i, t in enumerate(toks):
            nxt = toks[i + 1] if i + 1 < len(toks) else None
            if t.kind != "NAME" or t.sigil or not scan_code.is_op(nxt, "(") \
                    or t.val.lower() in scan_code.CONTROL_WORDS \
                    or (i and scan_code.is_word(toks[i - 1], scan_code.FUNC_WORDS)):
                continue
            data["calls"][t.val] += 1
            if i in loop_of and t.val.lower() not in scan_code.LOG_CALLS | scan_code.SIZE_WORDS:
                data["in_loop"].append((f.name, t.line, t.val, loop_of[i]))
            end = scan_code.close_of(toks, i + 1)
            args = toks[i + 2:end]
            if t.val.lower() in scan_code.LOG_CALLS:
                data["log"].append((f.name, t.line))
                continue
            depth, first = 0, []
            for a in args:
                depth += scan_code.is_op(a, "(", "[") - scan_code.is_op(a, ")", "]")
                if depth == 0 and scan_code.is_op(a, ","):
                    break
                first.append(a)
            show = lambda ts: re.sub(r"([$@%]) (?=\w)", r"\1", " ".join(
                ("'%s'" % x.val) if x.kind == "STR" else x.sigil + x.val for x in ts))
            if len(args) > len(first) and first and len(first) <= 3:
                data["same_source"][(t.val, show(first))].append((f.name, t.line))
            if args:
                data["identical"][(t.val, show(args))].append((f.name, t.line))
    scan.finish()
    crlf = sum(t.count("\r\n") for t in scan.text.values())
    lf = sum(t.count("\n") for t in scan.text.values()) - crlf
    data["endings"] = "CRLF" if crlf and not lf else "LF" if lf and not crlf else "mixed" if crlf else "none"
    data["files"], data["unread"] = kept, sorted(set(scan.hits["unread"]))
    data["same_source"] = {k: v for k, v in data["same_source"].items() if len(v) > 1}
    data["identical"] = {k: v for k, v in data["identical"].items() if len(v) > 1}
    return data


def counts(d):
    return [("Files", len(d["files"])), ("Lines", d["lines"]), ("Blank lines", d["blank"]),
            ("Comment lines", d["comment"]), ("Comment lines that look like code", len(d["commented_code"])),
            ("Calls, all functions", sum(d["calls"].values())), ("Logging calls", len(d["log"])),
            ("Groups of calls with the same function and first argument", len(d["same_source"])),
            ("Calls in those groups", sum(len(v) for v in d["same_source"].values())),
            ("Groups of identical calls", len(d["identical"])),
            ("Calls made inside a loop", len(d["in_loop"])),
            ("Names assigned and never read", len(d["unread"]))]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("code")
    ap.add_argument("after", nargs="?")
    ap.add_argument("--hash-comments", action="store_true", help="# starts a comment")
    args = ap.parse_args()

    before = read(args.code, args.hash_comments)
    if args.after:
        after = read(args.after, args.hash_comments)
        print("Inventory                                                        before    after")
        for (label, b), (_, a) in zip(counts(before), counts(after)):
            print("  %-60s %8d %8d" % (label, b, a))
        names = sorted(n for n in set(before["calls"]) | set(after["calls"])
                       if before["calls"][n] != after["calls"][n])
        print("\nCalls whose count changed (name, before -> after)")
        for n in names:
            print("  %-40s %4d -> %d" % (n, before["calls"][n], after["calls"][n]))
        if not names:
            print("  none")
        return

    print("Inventory: %s" % args.code)
    for label, n in counts(before):
        print("  %-60s %8d" % (label, n))
    print("  %-60s %8s   (keep them when you edit the file)" % ("Line endings", before["endings"]))
    many = len(before["files"]) > 1
    lines = lambda where: ", ".join(("%s:%d" % (f, n)) if many else str(n) for f, n in where)
    print("\nRepeated calls: same function and same first argument (candidates for one call)")
    for (fn, first), where in sorted(before["same_source"].items(), key=lambda kv: kv[1][0][1]):
        print("  %s(%s, ...)  x%d  lines %s" % (fn, first, len(where), lines(where)))
    if not before["same_source"]:
        print("  none")
    print("\nIdentical calls made more than once")
    for (fn, a), where in sorted(before["identical"].items(), key=lambda kv: kv[1][0][1]):
        text = a if len(a) <= 90 else a[:87] + "..."
        print("  %s(%s)  x%d  lines %s" % (fn, text, len(where), lines(where)))
    if not before["identical"]:
        print("  none")
    print("\nCalls made inside a loop (each one runs once for every pass of the loop)")
    for fname, line, fn, start in before["in_loop"]:
        print("  %sline %d  %s(...)  in the loop that starts on line %d" % (fname + " " if many else "", line, fn, start))
    if not before["in_loop"]:
        print("  none")
    print("\nCalls by function, most used first")
    for fn, n in before["calls"].most_common(15):
        print("  %-40s %4d" % (fn, n))
    print("\nLogging calls: %d  (lines %s)" % (len(before["log"]), lines(before["log"]) or "none"))
    print("\nNames assigned and never read: %d" % len(before["unread"]))
    for f, line, note in before["unread"]:
        print("  line %d  %s" % (line, note))
    print("\nComment lines that look like code: %d" % len(before["commented_code"]))
    for fname, n, text in before["commented_code"]:
        print("  %sline %d  %s" % (fname + " " if many else "", n, text[:120]))


if __name__ == "__main__":
    main()
