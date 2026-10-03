"""Task 3: review a rules folder against the trap catalogue, without trusting how it was made.

check(root, catalogue_md) reads the rules and lookup files as text and returns (findings, summary):
syntax (braces, brackets, quotes), paths (every include and table under $NC_RULES_HOME and present),
logs (one key=value format with the rules file and the node), commented-out code, dispatch (every
trap of the catalogue has exactly one case, and every case's event id has a lookup row), lookups
(columns, unique keys, severity and type values, the catalogue's severity), variables ($n within the
trap's variables, every variable set before use), clears (a problem and its clear share AlertGroup
and AlertKey; a clear by value sets $clear), and the alarm-ID lookup.

run(root, catalogue_md, out) writes the review report and its notes: each finding needs Bob's
decision (fix | owner | not a defect: <why>); with no finding the gate passes at once.
"""
import json
import os
import re

import catalogue as catmod

GLOBALS = {"Node", "IPaddress", "ReceivedTime", "enterprise", "generic-trap", "specific-trap", "Uptime",
           "community", "Protocol", "PeerIPaddress", "notify", "Manager"}
TYPE_NUM = {"problem": "1", "resolution": "2", "information": "13"}


def strip_strings(line):
    return re.sub(r'"(?:\\.|[^"\\])*"', '""', line)


def code_part(line):
    s = strip_strings(line)
    i = s.find("#")
    return s if i < 0 else s[:i]


def load(root):
    files = {}
    for dirpath, dirs, names in os.walk(root):
        dirs.sort()
        for n in sorted(names):
            full = os.path.join(dirpath, n)
            rel = os.path.relpath(full, root)
            with open(full, encoding="utf-8", errors="replace") as fh:
                files[rel] = fh.read().split("\n")
    return files


def resolve(path, root):
    """$NC_RULES_HOME/<home>/<rel> -> the file under root, by the longest tail that exists."""
    p = path.replace("$NC_RULES_HOME/", "")
    parts = p.split("/")
    for i in range(len(parts)):
        cand = os.path.join(root, *parts[i:])
        if os.path.exists(cand):
            return os.path.relpath(cand, root)
    return None


def check(root, catalogue_md):
    jpath = catalogue_md[:-3] + ".json" if catalogue_md.endswith(".md") else catalogue_md + ".json"
    cat = json.load(open(jpath, encoding="utf-8"))
    files = load(root)
    F = []

    def find(where, what):
        F.append({"where": where, "what": what})

    rules = {k: v for k, v in files.items() if k.endswith(".rules")}
    lookups = {k: v for k, v in files.items() if k.endswith(".lookup")}
    tables = {}
    # syntax, paths, logs, commented-out code
    for rel, lines in rules.items():
        depth = 0
        for i, line in enumerate(lines, 1):
            c = code_part(line)
            if line.count('"') - len(re.findall(r'\\"', line)) - 0 < 0:
                pass
            raw_q = len(re.findall(r'(?<!\\)"', line.split("#")[0] if '"' not in line else line))
            if len(re.findall(r'(?<!\\)"', re.sub(r"#[^\"]*$", "", line))) % 2:
                find("%s:%d" % (rel, i), "unbalanced quotes")
            depth += c.count("{") - c.count("}")
            if depth < 0:
                find("%s:%d" % (rel, i), "a closing brace with no opening brace")
                depth = 0
            if c.count("(") != c.count(")"):
                find("%s:%d" % (rel, i), "unbalanced parentheses")
            for m in re.finditer(r'\b(include|table\s+\w+\s*=)\s*"([^"]+)"', line):
                path = m.group(2)
                if not path.startswith("$NC_RULES_HOME/"):
                    find("%s:%d" % (rel, i), "path not under $NC_RULES_HOME: %s" % path)
                elif not resolve(path, root):
                    find("%s:%d" % (rel, i), "the file named is not in the rules folder: %s" % path)
            m = re.match(r"\s*table\s+(\w+)\s*=", line)
            if m:
                tables[m.group(1)] = rel
            if re.search(r"\blog\s*\(", c) and not ("rules_file=" in line and "node=" in line):
                find("%s:%d" % (rel, i), "a log line without rules_file= and node=")
            s = line.strip()
            if s.startswith("#") and re.match(r"^#+\s*(@\w+\s*=|\$\w+\s*=|if\s*\(|switch\s*\(|case\s+\"|discard|include\s+\"|log\s*\(|details\s*\()", s):
                find("%s:%d" % (rel, i), "commented-out code: %s" % s[:80])
        if depth:
            find(rel, "%d brace(s) left open" % depth)
    # lookups
    rows = {}
    trap_lookup = [k for k in lookups if k.endswith("_traps.lookup")]
    alarm_lookup = [k for k in lookups if k.endswith("_alarm_ids.lookup")]
    if not trap_lookup:
        find(root, "no *_traps.lookup file")
    for rel in trap_lookup:
        for i, line in enumerate(lookups[rel], 1):
            if not line.strip():
                continue
            cols = line.split("\t")
            if len(cols) != 8:
                find("%s:%d" % (rel, i), "%d columns, 8 expected" % len(cols))
                continue
            if cols[0] in rows:
                find("%s:%d" % (rel, i), "event id %s twice" % cols[0])
            rows[cols[0]] = cols
            if cols[4] not in "012345" or len(cols[4]) != 1:
                find("%s:%d" % (rel, i), "severity %s is not 0 to 5" % cols[4])
            if cols[5] not in ("1", "2", "13"):
                find("%s:%d" % (rel, i), "type %s is not 1, 2 or 13" % cols[5])
            if not cols[6].isdigit():
                find("%s:%d" % (rel, i), "expiry %s is not a number" % cols[6])
    alarm_rows = {}
    for rel in alarm_lookup:
        for i, line in enumerate(lookups[rel], 1):
            if not line.strip():
                continue
            cols = line.split("\t")
            if len(cols) != 3 or not cols[0].isdigit():
                find("%s:%d" % (rel, i), "an alarm-ID row must be: ID, event id, name")
                continue
            if cols[0] in alarm_rows:
                find("%s:%d" % (rel, i), "alarm ID %s twice" % cols[0])
            alarm_rows[cols[0]] = cols
            if cols[1] not in rows:
                find("%s:%d" % (rel, i), "event id %s has no row in the traps lookup" % cols[1])
    # every lookup() names a declared table
    for rel, lines in rules.items():
        for i, line in enumerate(lines, 1):
            for m in re.finditer(r"\blookup\s*\([^,]+,\s*(\w+)\s*\)", code_part(line) if '"' not in line else line):
                if m.group(1) not in tables:
                    find("%s:%d" % (rel, i), "lookup in table %s, which no file declares" % m.group(1))
    # dispatch: cases per (enterprise, specific) and per generic number
    cases = {}
    for rel, lines in rules.items():
        if not rel.startswith("transformation_rules") or rel.endswith("field_normalization.rules"):
            continue
        generic_file = rel.endswith(".generic.rules")
        ent = None
        cur = None
        depth = 0
        for i, line in enumerate(lines, 1):
            c = code_part(line)
            m = re.match(r'\s*case\s+"([^"]+)"\s*:', line)
            if m and depth == 0:
                if generic_file:
                    cur = ("generic", m.group(1))
                    cases.setdefault(cur, []).append({"file": rel, "line": i, "body": []})
                else:
                    ent = m.group(1).lstrip(".")
                    cur = None
            elif m and depth == 1 and ent is not None:
                cur = (ent, m.group(1))
                cases.setdefault(cur, []).append({"file": rel, "line": i, "body": []})
            elif re.match(r"\s*default\s*:", line):
                cur = None
            elif cur is not None and line.strip():
                cases[cur][-1]["body"].append((i, line))
            depth += c.count("{") - c.count("}")
    by_key = {}
    for e in cat["entries"]:
        k = ("generic", str(e["generic"])) if e["generic"] != 6 else (e["enterprise"], str(e["specific"]))
        by_key.setdefault(k, []).append(e)
    for k, es in by_key.items():
        got = cases.get(k, [])
        if not got:
            find(", ".join(e["name"] for e in es), "no case in the rules (%s %s)" % k)
        elif len(got) > 1:
            find(", ".join(e["name"] for e in es), "%d cases in the rules: %s" % (len(got), ", ".join("%s:%d" % (g["file"], g["line"]) for g in got)))
    for k in cases:
        if k not in by_key:
            g = cases[k][0]
            find("%s:%d" % (g["file"], g["line"]), "a case for %s %s, which is not in the catalogue" % k)
    # per case: event id, variables, keys, clears
    assigned_global = set()
    for rel, lines in rules.items():
        for line in lines:
            for m in re.finditer(r"\$([A-Za-z_][\w-]*)\s*=(?!=)", code_part(line)):
                assigned_global.add(m.group(1))
            for m in re.finditer(r"\[([^\]]+)\]\s*=\s*lookup", code_part(line)):
                for v in re.findall(r"\$([A-Za-z_][\w-]*)", m.group(1)):
                    assigned_global.add(v)
    keys_of = {}
    for k, es in by_key.items():
        for g in cases.get(k, [])[:1]:
            e = es[0]
            body = g["body"]
            text = "\n".join(l for _, l in body)
            where = "%s:%d %s" % (g["file"], g["line"], e["name"])
            nvb = len(e["varbinds"])
            local = {}
            for i, line in body:
                c = code_part(line)
                for m in re.finditer(r"(?<![\w$])\$(\d+)\b", c):
                    if nvb and int(m.group(1)) > nvb:
                        find("%s:%d" % (g["file"], i), "$%s, but %s has %d variables" % (m.group(1), e["name"], nvb))
                m = re.match(r"\s*\$([A-Za-z_]\w*)\s*=\s*\$(\d+)\s*$", c)
                if m:
                    local[m.group(1)] = int(m.group(2))
                rhs = c.split("=", 1)[1] if re.match(r"\s*[@$][\w-]+\s*=(?!=)", c) else c
                for m in re.finditer(r"\$([A-Za-z_][\w-]*)", rhs):
                    v = m.group(1)
                    if v in GLOBALS or re.match(r"OID\d+$", v) or v in assigned_global:
                        continue
                    find("%s:%d" % (g["file"], i), "$%s is used but never set" % v)
            if e.get("aggregated"):
                if "_alarm_ids)" not in text:
                    find(where, "a trap that carries alarm IDs without the alarm-ID lookup")
            else:
                m = re.search(r'\$OS_EventId\s*=\s*"([^"]+)"', text)
                if not m:
                    find(where, "no event id ($OS_EventId)")
                else:
                    row = rows.get(m.group(1))
                    if not row:
                        find(where, "event id %s has no row in the traps lookup" % m.group(1))
                    else:
                        if e.get("severity") is not None and row[4] != str(e["severity"]):
                            find(where, "severity %s in the lookup, %s in the catalogue" % (row[4], e["severity"]))
                        if e.get("type") and row[5] != TYPE_NUM[e["type"]]:
                            find(where, "type %s in the lookup, %s (%s) in the catalogue" % (row[5], TYPE_NUM[e["type"]], e["type"]))
                        keys_of[e["name"]] = {"group": row[3]}
                mk = re.search(r"@AlertKey\s*=\s*(.+)", text)
                if not mk:
                    find(where, "no @AlertKey")
                else:
                    names = set()
                    for v in re.findall(r"\$([A-Za-z_]\w*)", mk.group(1)):
                        base = v[:-len("_instance")] if v.endswith("_instance") else v
                        n = local.get(base)
                        names.add((e["varbinds"][n - 1]["name"] if n and n <= nvb else base) + ("#instance" if v.endswith("_instance") else ""))
                    keys_of.setdefault(e["name"], {})["key"] = names
                if "@Summary" not in text:
                    find(where, "no @Summary")
                if e.get("clear_when"):
                    var, val = e["clear_when"]
                    if not re.search(r'match\(\$%s,\s*"%s"\)' % (re.escape(catmod_ident(var)), re.escape(val)), text) or '$clear = "1"' not in text:
                        find(where, "the catalogue clears it when %s = %s, the rules do not" % (var, val))
    # pairs share group and key
    groups = {}
    for e in cat["entries"]:
        if e["type"] in ("problem", "resolution") and not e.get("aggregated"):
            groups.setdefault(e["group"], []).append(e)
    pairs = 0
    for gname, es in groups.items():
        probs = [x for x in es if x["type"] == "problem"]
        res = [x for x in es if x["type"] == "resolution"]
        if not probs or not res:
            continue
        pairs += 1
        ref = probs[0]["name"]
        for x in es[1:] if es[0]["name"] == ref else es:
            if x["name"] == ref or ref not in keys_of or x["name"] not in keys_of:
                continue
            a, b = keys_of[ref], keys_of[x["name"]]
            if a.get("group") != b.get("group"):
                find("%s, %s" % (ref, x["name"]), "same clear group in the catalogue, different AlertGroup in the lookup (%s, %s)" % (a.get("group"), b.get("group")))
            if a.get("key") != b.get("key"):
                find("%s, %s" % (ref, x["name"]), "same clear group, different AlertKey (%s; %s)" % (
                    ", ".join(sorted(a.get("key") or [])) or "empty", ", ".join(sorted(b.get("key") or [])) or "empty"))
    # alarm IDs
    for a in cat.get("alarms", []):
        if cat.get("aggregated") and str(a["id"]) not in alarm_rows:
            find("alarm ID %d" % a["id"], "no row in the alarm-ID lookup")
        row = alarm_rows.get(str(a["id"]))
        if row and row[1] in rows and a.get("severity") is not None and rows[row[1]][4] != str(a["severity"]):
            find("alarm ID %d" % a["id"], "severity %s in the lookup, %s in the catalogue" % (rows[row[1]][4], a["severity"]))
    if not F:
        import simulate
        sim_f, sim_summary = simulate.run_catalogue(root, catalogue_md)
        F.extend(sim_f)
    else:
        sim_summary = "not simulated: the findings above come first"
    n_cases = sum(len(v) for v in cases.values())
    summary = ("%d rules files and %d lookups; %d cases for %d catalogue traps; %d alarm IDs; %d clear groups; "
               "syntax, paths, logs, commented-out code, variables, event ids, severities and types, keys; %s" % (
                   len(rules), len(lookups), n_cases, len(by_key), len(alarm_rows), pairs, sim_summary))
    return F, summary


def catmod_ident(name):
    return re.sub(r"[^A-Za-z0-9_]", "_", name)


def run(root, catalogue_md, out):
    notes = out[:-3] + ".notes.md" if out.endswith(".md") else out + ".notes.md"
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    if not os.path.isdir(root):
        return "%s is not a folder: give the rules folder (the one that holds <name>.master.rules).\nGate: not passed." % root, False
    masters = [f for f in os.listdir(root) if f.endswith(".master.rules")]
    if not masters:
        subs = sorted(d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d)) and
                      any(f.endswith(".master.rules") for f in os.listdir(os.path.join(root, d))))
        if len(subs) == 1:
            root = os.path.join(root, subs[0])
        else:
            return ("%s holds %s: give the folder of one set of rules (the one that holds <name>.master.rules).\nGate: not passed."
                    % (root, ("%d sets of rules (%s)" % (len(subs), ", ".join(subs))) if subs else "no <name>.master.rules")), False
    findings, summary = check(root, catalogue_md)
    decisions = catmod.read_notes(notes)
    items = []
    for i, f in enumerate(findings, 1):
        d = decisions.get(("finding", "R-%d" % i), {"decision": ""})["decision"]
        ok = d in ("fix", "owner") or d.startswith("not a defect:")
        items.append((i, f, d, ok))
    lines = ["# Rules review: notes", "",
             "Rules: `%s`; catalogue: `%s`. Each finding needs a decision: `fix` (the generator or the notes must change), "
             "`owner` (a question for the owner), or `not a defect: <why>`." % (root, catalogue_md), ""]
    lines += catmod.section_text([{"kind": "finding", "key": "R-%d" % i} for i, f, d, ok in items], decisions)
    for i, f, d, ok in items:
        lines += ["### finding R-%d" % i, "- %s: %s" % (f["where"], f["what"]), "choices: fix | owner | not a defect: <why>", "decision: " + d, ""]
    if not items:
        lines.append("No finding: nothing to decide.")
    with open(notes, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    open_n = sum(1 for x in items if not x[3])
    rep = ["# Rules review", "", "Rules: `%s`. Catalogue: `%s`." % (root, catalogue_md), "",
           "Checked: %s." % summary, "",
           "%d finding(s)%s." % (len(findings), (": %d to fix, %d for the owner, %d not a defect" % (
               sum(1 for x in items if x[2] == "fix"), sum(1 for x in items if x[2] == "owner"),
               sum(1 for x in items if x[2].startswith("not a defect")))) if findings else ""), ""]
    if findings:
        rep += ["| # | Where | What | Decision |", "|---|---|---|---|"]
        rep += ["| R-%d | %s | %s | %s |" % (i, catmod.esc(f["where"]), catmod.esc(f["what"]), catmod.esc(d or "open")) for i, f, d, ok in items]
    rep += ["", "## Not checked", "",
            "- The rules were not loaded by a probe: run the probe's rules syntax check (for example `nco_p_syntax`), then send a test trap of each kind and compare the events.", ""]
    gate = "Gate: passed. %s" % ("No finding." if not findings else "Every finding has a decision.") if not open_n else \
        "Gate: not passed. %d finding(s) without a decision in %s." % (open_n, notes)
    rep.append(gate)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(rep) + "\n")
    return "Checked %s: %s.\n%d finding(s); wrote %s and %s.\n%s" % (root, summary, len(findings), out, notes, gate), not open_n
