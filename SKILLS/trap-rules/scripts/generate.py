"""Task 2: the rules, generated from the trap catalogue and Bob's notes.

First run writes <report>.notes.md: the layout, the files, the expiry, and for every trap the
AlertKey and Summary the script proposes, with a block for each one that needs a decision.
Each later run writes the rules folder and the report, checks the rules (review.check) and
prints the gate.

Layout (one folder per integration; every path in the rules goes through $NC_RULES_HOME):
  <name>/<name>.master.rules                      entry point: dispatch, then normalization
  <name>/config/<name>.master.include.rules       every table declaration
  <name>/config/<name>.common.constants.rules     constants set before dispatch
  <name>/transformation_rules/<file>.rules        one case per trap, grouped by vendor
  <name>/transformation_rules/field_normalization.rules   fields from the catalogue lookup
  <name>/lookups/probe_specific/<name>_traps.lookup        event id -> name, agent, group, severity, type, expiry, flags
  <name>/lookups/probe_specific/<name>_alarm_ids.lookup    alarm ID -> event id, alarm name
  <name>/lookups/constants/field_normalization.constant.rules   value maps of enumerated variables
"""
import json
import os
import re
import time

import catalogue as catmod

VENDOR_PREFIX = re.compile(r"^[a-z]{1,6}$")
STOP = {"the", "is", "in", "on", "of", "to", "a", "an", "and", "for", "has", "with", "from", "at", "by", "was",
        "changed", "status", "type", "value", "name", "reported", "case", "new", "message", "id"}


# ---------------------------------------------------------------- names and templates
def ident(name):
    return re.sub(r"[^A-Za-z0-9_]", "_", name)


def event_id(e):
    return "SNMPTRAP-%s-%s" % (e["module"] or "SHEET", ident(e["name"]))


def alarm_event_id(agg_module, aid):
    return "SNMPTRAP-%s-alarm-%d" % (agg_module, aid)


def quote(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def title_group(stem_text, module=""):
    toks = stem_text.split()
    if toks and toks[0] == "alarm":
        toks = toks[1:]
    if len(toks) >= 3 and re.match(r"^[a-z]{2,4}$", toks[0]) and toks[0] not in ("link", "fan", "disk", "power", "data", "dos"):
        toks = toks[1:]
    toks = [t for t in toks if t not in ("trap", "notification", "event")]
    words = " ".join(t.capitalize() if not t.isupper() else t for t in toks).strip()
    words = re.sub(r"\b([A-Za-z]) (\d+)\b", r"\1\2", words)
    return words or "General"


GROUP_DROP = set(catmod.STATE) | {"is", "has", "been", "the", "of", "a", "an", "was", "to", "trap", "alert", "suspected"}


def clean_label(text, strip=True):
    t = re.sub(r"\[.*?\]|\(.*?\)", " ", text or "")
    t = re.sub(r"^(critical|non-critical|system)\s+alert\s*:", " ", t, flags=re.I)
    drop = GROUP_DROP if strip else {"the", "trap", "alert"}
    words = [w for w in re.findall(r"[A-Za-z0-9][A-Za-z0-9/&-]*", t) if w.lower() not in drop]
    return " ".join(w if not w.islower() else w.capitalize() for w in words[:5])


def group_label(e, strip=True, label=None):
    """A readable AlertGroup: the trap list's label, else the MIB's type text, else the trap's name."""
    labels = [label] if label else [r.get("label") for r in e.get("rows", [])]
    for lab in labels:
        lab = clean_label(lab or "", strip)
        if lab:
            return lab
    lab = clean_label(e.get("type_hint") or "", strip)
    if lab:
        return lab
    for r in e.get("rows", []):
        d = re.split(r"\s+-\s+", first_sentence(r.get("description") or "", 200))[0]
        if d and len(d) <= 70 and not re.match(r"^(a|an|the|this)\b.*\b(trap|notification)\b|^(this|sent|notification)\b", d, re.I):
            lab = clean_label(d, strip)
            if lab:
                return lab
    lab = clean_label(humanize(e["name"]), strip)
    return lab or title_group(catmod.stem(e["name"]))


def parse_template(text):
    """'Link {ifIndex} is {2}' -> [("text","Link "), ("var","ifIndex"), ("text"," is "), ("n",2)]"""
    out, pos = [], 0
    for m in re.finditer(r"\{([A-Za-z0-9_.-]+)\}", text):
        if m.start() > pos:
            out.append(("text", text[pos:m.start()]))
        tok = m.group(1)
        out.append(("n", int(tok)) if tok.isdigit() else ("var", tok))
        pos = m.end()
    if pos < len(text):
        out.append(("text", text[pos:]))
    return out


def template_names(text):
    return [t[1] for t in parse_template(text) if t[0] == "var"] + ["$%d" % t[1] for t in parse_template(text) if t[0] == "n"]


# ---------------------------------------------------------------- proposals
def humanize(name):
    """vndPowerSupplyFailure -> Power Supply Failure (the vendor prefix and 'Trap' dropped)."""
    toks = catmod.tokens(name)
    if len(toks) >= 3 and re.match(r"^[a-z]{2,4}$", toks[0]):
        toks = toks[1:]
    toks = [t for t in toks if t.lower() not in ("trap", "notification")]
    return " ".join(t if t.isupper() else t.capitalize() for t in toks) or name


def first_sentence(text, limit=90):
    t = re.sub(r"\s+", " ", (text or "").strip().strip('"')).strip()
    m = re.match(r"^(.+?[.!?])(\s|$)", t)
    t = m.group(1) if m else t
    return t[:limit].rstrip()


def propose_summary(e):
    """(template, issues) for a trap: from the trap list's text, the MIB's summary, or a description."""
    vbs = e["varbinds"]
    names = [v["name"] for v in vbs]
    texts = [r["text"] for r in e["rows"] if r.get("text")]
    issues = []
    if texts:
        text = texts[0]
        tables = sorted(set(r["table"].split("@")[0] for r in e["rows"]))
        src = [r["table"].split("@")[0] for r in e["rows"] if r.get("text")][0]
        if len(tables) > 1 and any(not r.get("text") for r in e["rows"]):
            issues.append("the text comes from the sheet %s, but %s also list this trap: the summary must fit every device that sends it"
                          % (src, ", ".join(t for t in tables if t != src)))
        out = text

        def sub(m):
            n = int(m.group(1))
            if names and n <= len(names):
                return "{%s}" % names[n - 1]
            if not names and e["source"] == "SHEET":
                return "{%d}" % n
            issues.append("the trap list's text uses $%s%s but the trap has %d variable(s)" % (m.group(1), m.group(2), len(names)))
            return ""
        bad = [m.group(0) for m in re.finditer(r"\$(\d+)([VR])", text) if names and int(m.group(1)) > len(names)]
        for b in bad:
            issues.append("the trap list's text uses %s but the trap has %d variable(s); the proposal leaves it out" % (b, len(names)))
            text_wo = re.sub(r"\s*\([^()]*%s[^()]*\)" % re.escape(b), "", text)
            if text_wo == text:
                text_wo = re.sub(r",?\s*[A-Za-z][\w ]{0,24}?:?\s*%s" % re.escape(b), "", text)
            text = text_wo
        out = re.sub(r"\$(\d+)([VR])", sub, text)
        for m in re.finditer(r"\$([A-Za-z]\w*)", out):
            issues.append("the trap list's text uses $%s, which is not a variable of the trap" % m.group(1))
        out = re.sub(r"\$[A-Za-z]\w*", "", out)
        if re.search(r"\$\d+R", text):
            issues.append("the trap list's text uses $nR; it is read as the value of variable n")
        for m in re.finditer(r"(\w+)\s*:?\s*\$(\d+)[VR]", text):
            word, n = m.group(1).lower(), int(m.group(2))
            if len(word) < 3 or word in STOP or not names or n > len(names):
                continue
            own = names[n - 1].lower()
            others = [x for i, x in enumerate(names) if i != n - 1 and word in x.lower()]
            if word not in own and others:
                issues.append("the text says '%s $%d' but variable %d is %s; %s is %s" % (
                    m.group(1), n, n, names[n - 1], "variable %d" % (names.index(others[0]) + 1), others[0]))
        out = re.sub(r"\s+", " ", out).strip()
        out = re.sub(r"\s+([,.;:)])", r"\1", out)
        return out, issues, "trap list text"
    hint = e.get("summary_hint") or ""
    if hint:
        args = e.get("summary_args") or []
        k = [0]

        def sub2(m):
            i = k[0]
            k[0] += 1
            if i < len(args) and args[i] < len(names):
                return "{%s}" % names[args[i]]
            if not args and i < len(names):
                return "{%s}" % names[i]
            issues.append("the MIB's summary has more %%-fields than ARGUMENTS name")
            return ""
        out = re.sub(r"%[a-z]", sub2, hint)
        return re.sub(r"\s+", " ", out).strip(), issues, "MIB summary"
    car = carrier_vars(e)
    if car:
        name_v, oid_v, val_v = car
        return "%s: %s on {%s}%s" % (humanize(e["name"]), ("{%s}" % name_v) if name_v else "", oid_v,
                                     (", value {%s}" % val_v) if val_v else ""), issues, "carried object"
    desc = ""
    for r in e["rows"]:
        d = first_sentence(r.get("description") or "", 200)
        if d and len(d) <= 70 and not re.match(r"^(a|an|the|this)\b.*\b(trap|notification)\b|^(this|sent|notification)\b", d, re.I):
            desc = d
            break
    if not desc:
        for r in e["rows"]:
            if r.get("label"):
                desc = re.sub(r"\s*\[.*?\]", "", r["label"]).strip()
                break
    if not desc:
        desc = humanize(e["name"])
    out = desc
    msg = [n for n in names if re.search(r"(msg|message)text$|^(alert|event)?(msg|message)$|description$|descr$", n, re.I)]
    if msg:
        out = out.rstrip(".") + ": {%s}" % msg[0]
    return out, issues, "description"


def carrier_vars(e):
    """(name variable, OID variable, value variable) of a trap that carries another object's OID and value, or None."""
    vbs = e["varbinds"]
    oids = [v["name"] for v in vbs if v.get("syntax") == "OBJECT IDENTIFIER"]
    if not oids or len(vbs) < 2:
        return None
    strs = [v["name"] for v in vbs if re.search(r"String|OCTET|Admin", v.get("syntax") or "")]
    nums = [v["name"] for v in vbs if re.search(r"Integer|Unsigned|Gauge|Counter", v.get("syntax") or "") or v.get("syntax") == "INTEGER"]
    return (strs[0] if strs else None, oids[0], nums[-1] if nums else None)


def propose_key(e, summary):
    vbs = e["varbinds"]
    car = carrier_vars(e)
    if car and not any(v.get("table_index") for v in vbs):
        return ".".join("{%s}" % x for x in car[:2] if x), "the object the trap carries"
    idx_cols = [v["name"] for v in vbs if v.get("table_index") and v["name"] in v["table_index"]]
    if idx_cols:
        return ".".join("{%s}" % n for n in idx_cols), "index variables"
    tabled = [v for v in vbs if v.get("table_index")]
    if tabled:
        return "{%s.instance}" % tabled[0]["name"], "instance of %s (%s)" % (tabled[0]["name"], ".".join(tabled[0]["table_index"]))
    used = [t for t in template_names(summary)]
    for n in used:
        if not n.startswith("$"):
            v = [x for x in vbs if x["name"] == n]
            if v and not v[0].get("enums") and not re.search(r"(text|descr|description|reason|message|msg|time|date|value)$", n, re.I):
                return "{%s}" % n, "first variable named in the summary"
    return "", "none: one alarm per node and group"


# ---------------------------------------------------------------- the generator
class Generator:
    def __init__(self, catalogue_md, out_dir, notes_path, standards=None):
        self.standards = standards if standards and os.path.exists(standards) else None
        self.catalogue_md = catalogue_md
        jpath = catalogue_md[:-3] + ".json" if catalogue_md.endswith(".md") else catalogue_md + ".json"
        if not os.path.exists(jpath):
            raise SystemExit("%s not found: run the catalogue task first" % jpath)
        self.cat = json.load(open(jpath, encoding="utf-8"))
        self.out_dir = out_dir
        self.notes_path = notes_path
        self.notes = catmod.read_notes(notes_path)
        self.items = []
        self.questions = []

    item = catmod.Catalogue.item
    value = catmod.Catalogue.value

    def build(self):
        cat = self.cat
        base = os.path.splitext(os.path.basename(cat["trap_list"]))[0]
        base = re.sub(r"[_ -]*v?\d+([._]\d+)*$", "", base)
        prop_name = catmod.slug(base)[:24] or "integration"
        facts = ["the rules are written under <out>/<name>/ and every include and table path is "
                 "$NC_RULES_HOME/<path>/...; the domain and probe folders are the owner's: follow the standards document, "
                 "and the report asks the owner to confirm",
                 "<out> is the --out folder of the command: %s" % self.out_dir]
        if self.standards:
            tree = [l.rstrip() for l in open(self.standards, encoding="utf-8", errors="replace").read().splitlines()
                    if re.search(r"[├└│]|\$NC_RULES_HOME", l)][:14]
            if tree:
                facts.append("the folder tree in %s:" % self.standards)
                facts += ["  " + re.sub(r"\s{2,}#.*$", "", l) for l in tree]

        def check_layout(d):
            m = re.match(r"^name ([a-z][a-z0-9_]*), path ([A-Za-z0-9_./-]+)$", d)
            return "" if m else "write: name <lower_case_word>, path <path under $NC_RULES_HOME>"
        domain = ""
        if self.standards:
            lines = open(self.standards, encoding="utf-8", errors="replace").read().splitlines()
            for i, l in enumerate(lines):
                if "$NC_RULES_HOME/probes" in l:
                    for l2 in lines[i + 1:i + 4]:
                        m = re.search(r"[└├]──\s*([a-z][\w-]*)/", l2)
                        if m:
                            domain = m.group(1)
                            break
                    break
        it = self.item("layout", "rules", facts, "name <word>, path <path under $NC_RULES_HOME>",
                       "name %s, path probes/%s%s" % (prop_name, domain + "/" if domain else "", prop_name), check_layout)
        m = re.match(r"^name ([a-z][a-z0-9_]*), path ([A-Za-z0-9_./-]+)$", self.value(it))
        self.name, self.home = (m.group(1), m.group(2).strip("/")) if m else (prop_name, "probes/" + prop_name)

        # entries and vendors
        self.entries = [e for e in cat["entries"]]
        self.agg = cat.get("aggregated")
        vendors = {}
        for e in self.entries:
            key = vendor_key(e)
            vendors.setdefault(key, []).append(e)
        self.vendors = vendors
        files = {}
        for key, es in sorted(vendors.items()):
            files[key] = proposed_file(key, es)
        facts = ["one rules file per vendor (traps that share an enterprise number share a file):"]
        for key, es in sorted(vendors.items()):
            mods = sorted(set(e["module"] or "(no MIB)" for e in es))
            facts.append("  %s.rules: %s, %d traps (%s)" % (files[key], key, len(es), ", ".join(mods)))
        names = set(files.values())

        def check_files(d):
            return "" if d == "as listed" or re.match(r"^[a-z][a-z0-9_.-]*$", d) else "write as listed, or a file name for one file under overrides"
        it = self.item("files", "rules", facts, "as listed (rename one: - <file>: <new name> under overrides)", "as listed", check_files)
        for k in it["overrides"]:
            if k not in names:
                it["error"] = "%s is not one of the files listed" % k
        self.files = {}
        for key, f in files.items():
            v = self.value(it, f)
            self.files[key] = v if v != "as listed" else f

        facts = ["ExpireTime in seconds for information events, and for problems that have no clear (0 = never)"]
        it = self.item("expiry", "rules", facts, "information <seconds>, no clear <seconds>", "information 1800, no clear 0",
                       lambda d: "" if re.match(r"^information \d+, no clear \d+$", d) else "write: information <seconds>, no clear <seconds>")
        m = re.match(r"^information (\d+), no clear (\d+)$", self.value(it))
        self.expire_info, self.expire_unpaired = (int(m.group(1)), int(m.group(2))) if m else (1800, 0)

        # keys and summaries
        self.plan = {}
        rows = []
        for e in self.entries:
            if e["aggregated"]:
                continue
            summ, issues, src = propose_summary(e)
            key, ksrc = propose_key(e, summ)
            self.plan[e["name"]] = {"summary": summ, "key": key, "issues": issues, "src": src, "ksrc": ksrc}
        # pairs share the key
        groups = {}
        for e in self.entries:
            if not e["aggregated"] and e["type"] in ("problem", "resolution"):
                groups.setdefault(e["group"], []).append(e)
        for g, es in groups.items():
            probs = [x for x in es if x["type"] == "problem"]
            if not probs:
                continue
            pk = self.plan[probs[0]["name"]]["key"]
            for x in es:
                p = self.plan[x["name"]]
                if p["key"] != pk:
                    vars_ok = all(n in [v["name"] for v in x["varbinds"]] or n.endswith(".instance") for n in template_names(pk))
                    if vars_ok:
                        p["key"], p["ksrc"] = pk, "same as %s (same group)" % probs[0]["name"]
        self.group_name = {}
        by_group = {}
        for e in self.entries:
            by_group.setdefault(e.get("group") or e["name"], []).append(e)
        self.group_raw = {}
        for g, es in by_group.items():
            es = sorted(es, key=lambda x: (x.get("type") != "problem", x["name"]))
            self.group_name[g] = group_label(es[0], strip=len(es) > 1)
            r0 = es[0].get("rows") or [{}]
            self.group_raw[g] = re.split(r"\s+-\s+", r0[0].get("label") or r0[0].get("description") or "")[0]
        alarm_groups = {}
        for a in self.cat.get("alarms", []):
            alarm_groups.setdefault(a["group"], []).append(a)
        for g, al in alarm_groups.items():
            al = sorted(al, key=lambda x: (x.get("type") != "problem", x["id"]))
            self.group_name[g] = clean_label(al[0]["label"] or humanize(al[0]["name"]), strip=len(al) > 1) or title_group(g.split(" / ")[-1])
        self.group_scope = {}
        self.group_module = {}
        for e in self.entries:
            self.group_scope[e.get("group") or e["name"]] = "traps"
            self.group_module[e.get("group") or e["name"]] = e["module"] or e.get("family") or ""
        for g in alarm_groups:
            self.group_scope[g] = "alarm IDs"
        self.unique_group_names()
        for e in self.entries:
            if e["aggregated"]:
                continue
            p = self.plan[e["name"]]
            rows.append("  %s: group %s; key %s; summary %s" % (e["name"], self.group_name[e.get("group") or e["name"]], p["key"] or "none", p["summary"]))
        facts = ["the AlertKey and Summary of each trap, as the script proposes them ({name} is a variable of the "
                 "trap, {n} the n-th variable, {name.instance} the index part of that variable's OID; key none = "
                 "empty). A problem and its clear must have the same key:"] + rows

        def check_fields(d):
            if d == "as listed":
                return ""
            if d and all(re.match(r"^(group|key|summary) \S", x.strip()) for x in d.split(";")):
                return ""
            return "write as listed, or for one trap: group <words>; key <template>; summary <template> (any of the three)"
        it = self.item("fields", "rules", facts, "as listed (one trap: - <trap>: group <words>; key <template>; summary <template>)", "as listed", check_fields)
        known = set(self.plan)
        for k, v in it["overrides"].items():
            if k not in known:
                it["error"] = "%s is not a trap of the catalogue" % k
                continue
            for part in v.split(";"):
                part = part.strip()
                if part.startswith("key "):
                    self.plan[k]["key"] = "" if part[4:].strip() == "none" else part[4:].strip()
                    self.plan[k]["ksrc"] = "decided in the notes"
                elif part.startswith("summary "):
                    self.plan[k]["summary"] = part[8:].strip()
                    self.plan[k]["src"] = "decided in the notes"
                    self.plan[k]["issues"] = []
                elif part.startswith("group "):
                    e = [x for x in self.entries if x["name"] == k][0]
                    self.group_name[e.get("group") or k] = part[6:].strip()
        ent_by_name = {e["name"]: e for e in self.entries}
        for name, p in sorted(self.plan.items()):
            if not p["issues"]:
                continue
            e = ent_by_name[name]
            texts = [r["text"] for r in e["rows"] if r.get("text")]
            facts = ["%s: %s" % (name, "; ".join(p["issues"]))]
            if texts:
                facts.append("the trap list's text: %s" % texts[0])
            facts.append("its variables: %s" % (", ".join("%d %s%s" % (v["n"], v["name"], (" (%s)" % v["about"].rstrip(".")) if v.get("about") else "")
                                                         for v in e["varbinds"]) or "none named"))
            wrong_word = any(i.startswith("the text says") for i in p["issues"])
            if wrong_word:
                facts.append("the text's words name other variables than its numbers: write the summary yourself")
            else:
                facts.append("proposed summary: %s" % p["summary"])
            it = self.item("text", name, facts, "summary <template>" if wrong_word else "as proposed | summary <template>", "" if wrong_word else "as proposed",
                           lambda d: "" if d.startswith("summary ") or d == "as proposed" else "write as proposed, or summary <template>")
            if wrong_word and it["raw"].lower() in catmod.ACCEPT:
                it["error"] = "no proposal here: write summary <template>"
            v = self.value(it)
            if v.startswith("summary "):
                p["summary"] = v[len("summary "):].strip()
                p["src"] = "decided in the notes"
        # templates must name variables of their trap
        self.template_errors = []
        for e in self.entries:
            if e["aggregated"]:
                continue
            p = self.plan[e["name"]]
            names = [v["name"] for v in e["varbinds"]]
            for part in ("key", "summary"):
                for tok in parse_template(p[part]):
                    if tok[0] == "var":
                        base = tok[1][:-len(".instance")] if tok[1].endswith(".instance") else tok[1]
                        if base not in names:
                            self.template_errors.append("%s: the %s names {%s}, which is not a variable of the trap (%s)" % (
                                e["name"], part, tok[1], ", ".join(names) or "none named"))
                        elif tok[1].endswith(".instance") and not [v for v in e["varbinds"] if v["name"] == base and v.get("oid")]:
                            self.template_errors.append("%s: {%s}: the OID of %s is not known" % (e["name"], tok[1], base))
                    if tok[0] == "n" and (tok[1] < 1 or (names and tok[1] > len(names))):
                        self.template_errors.append("%s: the %s names {%d}, but the trap has %d variables" % (e["name"], part, tok[1], len(names)))
        self.questions.append("The rules are placed under $NC_RULES_HOME/%s/ (named %s): is that the right folder in the "
                              "operator's tree (domain and probe)?" % (self.home, self.name))
        self.template_errors += self.group_clashes()
        if self.agg:
            self.questions.append("Alarms that arrive through %s: is @Node to stay the sender (the manager that forwards them), "
                                  "or become the device whose address is in the alarm's instance? The rules keep the sender and "
                                  "put the device address first in @AlertKey." % self.agg["trap"])
            self.questions.append("Alarms through %s carry their own severity variable; the rules take each alarm's severity "
                                  "from the trap list and use the variable only to see a clear: should the device's severity win?"
                                  % self.agg["trap"])
        self.questions.append("Which event field should carry the flag(s) of the trap list (%s)? The rules set them in "
                              "$flags only." % (", ".join(sorted(set(f for e in self.entries for f in e["flags"]))) or "none"))

    def unique_group_names(self):
        """Two clear groups of one scope (a vendor, or the alarm IDs) must not share an AlertGroup: a clear of one
        would clear the problems of the other on the same node and key."""
        for _ in range(3):
            seen = {}
            for g, name in self.group_name.items():
                seen.setdefault((self.group_scope.get(g), name.lower()), []).append(g)
            clashes = [gs for gs in seen.values() if len(gs) > 1]
            if not clashes:
                return
            for gs in clashes:
                mods = set(self.group_module.get(g, "") for g in gs)
                raw = {g: set(re.findall(r"[A-Za-z][\w-]*", re.sub(r"\[.*?\]", "", getattr(self, "group_raw", {}).get(g, "")))) for g in gs}
                own = {g: sorted(raw[g] - set().union(*[raw[h] for h in gs if h != g]), key=lambda w: self.group_raw[g].find(w)) for g in gs}
                short = all(len(getattr(self, "group_raw", {}).get(g, "")) <= 60 for g in gs)
                if _ == 0 and short and all(own[g] for g in gs):
                    for g in gs:
                        self.group_name[g] = "%s (%s)" % (self.group_name[g], " ".join(own[g][:3]))
                    continue
                for k, g in enumerate(sorted(gs)):
                    base = self.group_name[g]
                    if _ == 0:
                        stoks = g.split(" / ", 1)[-1].split() if " / " in g else []
                        if len(stoks) > 1 and re.match(r"^[a-z]{2,4}$", stoks[0]):
                            stoks = stoks[1:]
                        alt = title_group(" ".join(stoks)) if stoks else ""
                        extra = [w for w in alt.split() if w.lower() not in base.lower().split()
                                 and (len(w) > 2 or w.isdigit() or re.match(r"^[A-Za-z]\d+$", w))]
                        if extra:
                            self.group_name[g] = (base + " " + " ".join(extra)).strip()
                    elif _ == 1 and len(mods) == len(gs) and self.group_module.get(g):
                        self.group_name[g] = "%s (%s)" % (base, self.group_module[g])
                    elif _ == 2:
                        self.group_name[g] = "%s %d" % (base, k + 1)

    def group_clashes(self):
        seen = {}
        for g, name in self.group_name.items():
            seen.setdefault((self.group_scope.get(g), name.lower()), []).append(g)
        return ["clear groups %s share the AlertGroup '%s': a clear of one would clear the other" % (
            " and ".join(sorted(gs)), self.group_name[gs[0]]) for gs in seen.values() if len(gs) > 1]

    # -- writing
    def path(self, *parts):
        return "$NC_RULES_HOME/%s/%s" % (self.home, "/".join(parts))

    def write(self):
        root = os.path.join(self.out_dir, self.name)
        n = self.name
        self.written = {}
        enum_tables = {}
        stamp = "Generated by the trap-rules skill from %s on %s. Change the catalogue or the notes and generate again; do not edit by hand." % (
            self.catalogue_md, time.strftime("%Y-%m-%d"))

        def header(fname, purpose):
            return ["#" * 79, "#", "# %s" % fname, "#", "# %s" % purpose, "# %s" % stamp, "#", "#" * 79, ""]

        # transformation files
        trans = {}
        for key, es in sorted(self.vendors.items()):
            fname = self.files[key] + ".rules"
            lines = header(fname, "Traps of %s (%s): one case per trap; the data of each trap (severity, type, group, "
                                  "expiry, flags) comes from %s_traps.lookup." % (", ".join(sorted(set(e["module"] or "no MIB" for e in es))), key, n))
            generic = [e for e in es if e["generic"] != 6]
            specific = [e for e in es if e["generic"] == 6]
            if generic:
                fname_g = self.files[key] + ".generic.rules"
                gl = header(fname_g, "Standard traps (generic-trap 0 to 5) of %s: one case per generic-trap number." % ", ".join(sorted(set(e["module"] for e in generic))))
                for e in sorted(generic, key=lambda x: x["generic"]):
                    gl += self.case_lines(e, str(e["generic"]), indent=0, enum_tables=enum_tables)
                trans.setdefault("generic", []).append(fname_g)
                self.written[os.path.join("transformation_rules", fname_g)] = gl
            if specific:
                by_ent = {}
                for e in specific:
                    by_ent.setdefault(e["enterprise"], []).append(e)
                for ent, ees in sorted(by_ent.items()):
                    mods = sorted(set(x["module"] or "no MIB" for x in ees))
                    lines += ['case "%s": ### %s' % ("." + ent, ", ".join(mods)), ""]
                    lines += ['    $rules_file = "%s"' % fname,
                              '    log(DEBUG, "rules_file=" + $rules_file + " node=" + $Node + " enterprise=" + $enterprise + " specific=" + $specific-trap)', "",
                              "    switch($specific-trap)", "    {"]
                    for e in sorted(ees, key=lambda x: x["specific"]):
                        lines += self.case_lines(e, str(e["specific"]), indent=2, enum_tables=enum_tables)
                    lines += ["        default:",
                              '            $OS_EventId = "SNMPTRAP-%s-unknown"' % mods[0].replace(" ", "-"),
                              '            @Summary = "Trap not in the catalogue: enterprise " + $enterprise + " specific " + $specific-trap',
                              "    }", ""]
                trans.setdefault("specific", []).append(fname)
                self.written[os.path.join("transformation_rules", fname)] = lines

        # field normalization
        fl = header("field_normalization.rules", "Fields of every event: the trap's data from %s_traps.lookup, the clear, and @Identifier." % n)
        fl += ['$rules_file = "field_normalization.rules"', "",
               "@Node = $Node", "@NodeAlias = $IPaddress", "@FirstOccurrence = $ReceivedTime", "@LastOccurrence = $ReceivedTime",
               'if (match(@Manager, ""))', "{", '    @Manager = "SNMP trap probe on " + hostname()', "}", "",
               "[$event_name, $agent, $alert_group, $severity, $type, $expire_time, $flags] = lookup($OS_EventId, %s_traps)" % n,
               "@Agent = $agent", "@AlertGroup = $alert_group", "@Severity = $severity", "@ExpireTime = $expire_time",
               "if (match($clear, \"1\"))", "{", "    $type = \"2\"", "    @Severity = 1", "    @ExpireTime = 0", "}", "@Type = $type", "",
               '@Identifier = @Node + " " + @AlertKey + " " + @AlertGroup + " " + $type + " " + @Agent + " " + @Manager + " " + $OS_EventId',
               'log(DEBUG, "rules_file=" + $rules_file + " node=" + @Node + " event=" + $OS_EventId + " severity=" + $severity + " type=" + $type + " flags=" + $flags)', ""]
        self.written[os.path.join("transformation_rules", "field_normalization.rules")] = fl

        # lookups
        tl = []
        for e in self.entries:
            tl.append(self.lookup_row(event_id(e), e["name"], e["module"] or "SHEET", e))
        al = []
        if self.agg:
            mod = [e for e in self.entries if e["name"] == self.agg["trap"]][0]["module"]
            for a in self.cat["alarms"]:
                eid = alarm_event_id(mod, a["id"])
                al.append("%d\t%s\t%s" % (a["id"], eid, clean_tab(a["label"] or a["name"])))
                tl.append(self.lookup_row(eid, a["label"] or a["name"], mod, {
                    "group": a["group"], "type": a["type"], "severity": a["severity"], "flags": a["flags"],
                    "family": mod, "aggregated": False, "clear_when": None, "name": a["name"]}, alarm=a))
        self.written[os.path.join("lookups", "probe_specific", "%s_traps.lookup" % n)] = tl
        if al:
            self.written[os.path.join("lookups", "probe_specific", "%s_alarm_ids.lookup" % n)] = al

        # constants: enum maps
        cl = header("field_normalization.constant.rules", "Value maps of the enumerated variables that the summaries show.")
        for tname, (vbname, enums) in sorted(enum_tables.items()):
            cl += ["table %s =" % tname, "{"]
            items = sorted(enums.items(), key=lambda kv: int(kv[0]))
            for i, (k, v) in enumerate(items):
                cl.append('    {"%s","%s"}%s' % (k, v, "," if i < len(items) - 1 else ""))
            cl += ["}", 'default = "unknown"', ""]
        self.written[os.path.join("lookups", "constants", "field_normalization.constant.rules")] = cl

        # config
        il = header("%s.master.include.rules" % n, "Every table of the rules. Include it at the top of the probe's main rules file.")
        il += ["table %s_traps = \"%s\"" % (n, self.path("lookups", "probe_specific", "%s_traps.lookup" % n)),
               'default = {"Unknown", "%s", "Unknown", "2", "1", "0", ""}' % n, ""]
        if al:
            il += ["table %s_alarm_ids = \"%s\"" % (n, self.path("lookups", "probe_specific", "%s_alarm_ids.lookup" % n)),
                   'default = {"SNMPTRAP-%s-alarm-unknown", "Alarm not in the trap list"}' % mod, ""]
        il += ['include "%s"' % self.path("lookups", "constants", "field_normalization.constant.rules"), ""]
        self.written[os.path.join("config", "%s.master.include.rules" % n)] = il
        kl = header("%s.common.constants.rules" % n, "Values every event starts from.")
        kl += ['$OS_EventId = ""', '$clear = "0"', '$flags = ""', '@AlertKey = ""', '@Summary = ""', ""]
        self.written[os.path.join("config", "%s.common.constants.rules" % n)] = kl

        # master
        ml = header("%s.master.rules" % n, "Entry point: dispatch by trap, then the fields of the event. The tables are in "
                                          "config/%s.master.include.rules, which must be included at the top of the probe's main rules file." % n)
        ml += ['include "%s"' % self.path("config", "%s.common.constants.rules" % n), "",
               '$rules_file = "%s.master.rules"' % n,
               'log(DEBUG, "rules_file=" + $rules_file + " node=" + $Node + " enterprise=" + $enterprise + " generic=" + $generic-trap + " specific=" + $specific-trap)', "",
               'if (match($generic-trap, "6"))', "{", "    switch($enterprise)", "    {",
               '        case "dummy case statement": ### keeps the switch valid whatever files are included']
        for f in trans.get("specific", []):
            ml.append('        include "%s"' % self.path("transformation_rules", f))
        ml += ["        default:", '            $OS_EventId = "SNMPTRAP-unknown"',
               '            @Summary = "Trap not in the catalogue: enterprise " + $enterprise + " specific " + $specific-trap',
               "    }", "}", "else", "{", "    switch($generic-trap)", "    {",
               '        case "dummy case statement": ### keeps the switch valid whatever files are included']
        for f in trans.get("generic", []):
            ml.append('        include "%s"' % self.path("transformation_rules", f))
        ml += ["        default:", '            $OS_EventId = "SNMPTRAP-generic-unknown"',
               '            @Summary = "Standard trap " + $generic-trap + " not in the catalogue"', "    }", "}", "",
               'include "%s"' % self.path("transformation_rules", "field_normalization.rules"), ""]
        self.written["%s.master.rules" % n] = ml
        for rel, lines in self.written.items():
            full = os.path.join(root, rel)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8") as fh:
                fh.write("\n".join(lines).rstrip("\n") + "\n")
        return root

    def lookup_row(self, eid, name, agent, e, alarm=None):
        stem_text = e["group"].split(" / ", 1)[1] if " / " in (e.get("group") or "") else ""
        group = self.group_name.get(e.get("group") or e["name"])
        group = group or title_group(stem_text or catmod.stem(e["name"]))
        typ = e.get("type")
        sev = e.get("severity")
        if e.get("aggregated"):
            sev, typ = (1, "resolution") if self.agg and e["name"] == self.agg.get("cleared_by") else (sev or 3, typ or "problem")
        tnum = catmod.TYPES.get(typ or "problem", 1)
        if typ == "information":
            exp = self.expire_info
        elif typ == "problem" and not self.paired(e, alarm):
            exp = self.expire_unpaired
        else:
            exp = 0
        return "\t".join([eid, clean_tab(name), clean_tab(agent), clean_tab(group), str(sev if sev is not None else 2), str(tnum), str(exp), ",".join(e.get("flags", []))])

    def paired(self, e, alarm):
        if alarm is not None:
            return alarm.get("paired", False)
        if e.get("clear_when") or e.get("aggregated"):
            return True
        same = [x for x in self.entries if x.get("group") == e.get("group") and x["type"] == "resolution"]
        return bool(same)

    def case_lines(self, e, label, indent, enum_tables):
        pad = "    " * indent
        out = ['%scase "%s": ### %s' % (pad, label, e["name"])]
        body = pad + "    "
        vbs = e["varbinds"]
        if vbs:
            for v in vbs:
                out.append(body + "$%s = $%d" % (ident(v["name"]), v["n"]))
        if e["aggregated"] and self.agg:
            out += self.aggregated_lines(e, body)
            return out + [""]
        p = self.plan[e["name"]]
        used = set()
        for part in ("key", "summary"):
            for tok in parse_template(p[part]):
                if tok[0] == "var":
                    used.add((part, tok[1]))
        for part, name in sorted(used):
            if name.endswith(".instance"):
                v = [x for x in vbs if x["name"] == name[:-9]][0]
                out.append(body + '$%s_instance = extract($OID%d, "^\\.?%s\\.(.+)$")' % (ident(v["name"]), v["n"], re.escape(v["oid"]).replace("\\.", "\\.")))
        for part, name in sorted(used):
            if part == "summary" and not name.endswith(".instance"):
                v = [x for x in vbs if x["name"] == name][0]
                if v.get("enums"):
                    tname = "%s_%s" % (self.name, ident(v["name"]))
                    if tname in enum_tables and enum_tables[tname][1] != v["enums"]:
                        tname = "%s_%s_%s" % (self.name, ident(e["module"] or "x"), ident(v["name"]))
                    enum_tables[tname] = (v["name"], {str(k): val for k, val in v["enums"].items()})
                    out.append(body + "$%s_text = lookup($%s, %s)" % (ident(v["name"]), ident(v["name"]), tname))
        out.append(body + '$OS_EventId = "%s"' % event_id(e))
        out.append(body + "@AlertKey = " + self.expr(p["key"], vbs, summary=False))
        out.append(body + "@Summary = " + self.expr(p["summary"], vbs, summary=True))
        if e.get("clear_when"):
            var, val = e["clear_when"]
            out += [body + 'if (match($%s, "%s"))' % (ident(var), val), body + "{", body + '    $clear = "1"', body + "}"]
        return out + [""]

    def aggregated_lines(self, e, body):
        a = self.agg
        vbs = e["varbinds"]
        first = vbs[0]
        idx = a["index"]
        out = [body + "# the instance of each variable is %s" % ".".join(idx),
               body + '$alarm_instance = extract($OID1, "^\\.?%s\\.(.+)$")' % re.escape(first["oid"]).replace("\\.", "\\.")]
        for i, name in enumerate(idx):
            parts = ["[0-9]+"] * len(idx)
            parts[i] = "([0-9]+)"
            out.append(body + '$%s = extract($alarm_instance, "^%s$")' % (ident(name), "\\.".join(parts)))
        out.append(body + "[$OS_EventId, $alarm_name] = lookup($%s, %s_alarm_ids)" % (ident(a["alarm_index"]), self.name))
        key = [ident(x) for x in idx if x != a["alarm_index"]]
        out.append(body + "@AlertKey = " + ' + "." + '.join("$" + k for k in key))
        desc = [v for v in vbs if re.search(r"descr", v["name"], re.I)]
        sevv = [v for v in vbs if re.search(r"severity", v["name"], re.I)]
        if e["name"] == a.get("cleared_by"):
            out.append(body + '@Summary = $alarm_name + " cleared"')
            out.append(body + '$clear = "1"')
        else:
            out.append(body + "@Summary = $alarm_name" + ((' + ": " + $%s' % ident(desc[0]["name"])) if desc else ""))
            if sevv:
                clr = [k for k, v in sevv[0].get("enums", {}).items() if re.match(r"^clear", v, re.I)]
                if clr:
                    out += [body + 'if (match($%s, "%s"))' % (ident(sevv[0]["name"]), clr[0]), body + "{", body + '    $clear = "1"', body + "}"]
        return out

    def expr(self, template, vbs, summary):
        parts = []
        for tok in parse_template(template):
            if tok[0] == "text":
                if tok[1]:
                    parts.append(quote(tok[1]))
            elif tok[0] == "n":
                parts.append("$%d" % tok[1])
            else:
                name = tok[1]
                if name.endswith(".instance"):
                    parts.append("$%s_instance" % ident(name[:-9]))
                else:
                    v = [x for x in vbs if x["name"] == name]
                    parts.append("$%s%s" % (ident(name), "_text" if summary and v and v[0].get("enums") else ""))
        return " + ".join(parts) if parts else '""'


def clean_tab(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()


def vendor_key(e):
    oid = e["oid"]
    m = re.match(r"^(1\.3\.6\.1\.4\.1\.\d+)", oid)
    return m.group(1) if m else "standard"


def proposed_file(key, es):
    mods = sorted(set(e["module"] for e in es if e["module"] and (e["source"] != "SHEET" or e["module"].endswith("-MIB"))))
    if key == "standard":
        return "standard"
    if mods:
        pre = os.path.commonprefix(mods).rstrip("-")
        if len(pre) >= 3:
            return catmod.slug(pre).replace("_", "-")
        return catmod.slug(mods[0]).replace("_", "-")
    fams = sorted(set(e.get("family", "") for e in es))
    if len(fams) == 1 and fams[0] and not fams[0].lower().startswith(("appln", "sheet")):
        return catmod.slug(fams[0]).replace("_", "-")
    return "enterprise-" + key.rsplit(".", 1)[1]


# ---------------------------------------------------------------- notes and report
def write_notes(g, path):
    out = ["# Rules: notes", "",
           "Catalogue: `%s` (%d traps, %d alarm IDs). Rules folder: `%s`." % (g.catalogue_md, len(g.cat["entries"]), len(g.cat["alarms"]), g.out_dir), "",
           "Every block ends with `decision:`. Write `as proposed` (or `as listed`) to take the proposal, or one of its "
           "choices; for one trap or file that differs, add under `overrides:` a line `- <name>: <decision>`. Then run "
           "the same command again: it rewrites this file around your decisions.", ""]
    out += catmod.section_text(g.items, g.notes)
    for it in g.items:
        out.append("### %s %s" % (it["kind"], it["key"]))
        out += [("- " + f if not f.startswith("  ") else "  - " + f.strip()).replace("\n", " / ") for f in it["facts"]]
        out.append("choices: " + it["choices"])
        out.append("proposal: " + (it["proposal"] or "(none: decide)"))
        if it["error"] and it["raw"]:
            out.append("<!-- not accepted: %s -->" % it["error"])
        out.append("decision: " + it["raw"])
        if it["kind"] in ("files", "fields") or it["overrides"]:
            out.append("overrides:")
            for k, v in it["overrides"].items():
                out.append("- %s: %s" % (k, v))
        out.append("")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out).rstrip() + "\n")


def run(catalogue_md, out_dir, report, standards=None):
    import review
    notes = report[:-3] + ".notes.md" if report.endswith(".md") else report + ".notes.md"
    first = not os.path.exists(notes)
    os.makedirs(os.path.dirname(report) or ".", exist_ok=True)
    g = Generator(catalogue_md, out_dir, notes, standards)
    if not g.cat.get("gate"):
        return "The catalogue %s has not passed its gate: finish the catalogue task first.\nGate: not passed." % catalogue_md, False
    g.build()
    write_notes(g, notes)
    open_items = [it for it in g.items if it["error"]]
    if g.template_errors and not open_items:
        gate = "Gate: not passed. %d problem(s) in the decisions of %s; correct them there: %s" % (
            len(g.template_errors), notes, "; ".join(g.template_errors[:10]))
        with open(report, "w", encoding="utf-8") as fh:
            fh.write("# Rules generated\n\nNo rules written: the notes name variables the traps do not have.\n\n%s\n" % gate)
        return "Read %s: all %d blocks decided, but no rules written.\n%s" % (notes, len(g.items), gate), False
    if open_items:
        msg = ("Wrote %s: %d blocks to decide. Fill every `decision:` line, then run the same command again; the rules are "
               "written when every block is decided." % (notes, len(g.items)) if first else
               "Read %s: %d of %d blocks decided; the rules are written when every block is decided." % (notes, len(g.items) - len(open_items), len(g.items)))
        gate = "Gate: not passed. %d block(s) of the notes without a valid decision: %s" % (
            len(open_items), "; ".join("%s %s (%s)" % (i["kind"], i["key"], i["error"]) for i in open_items[:10]))
        with open(report, "w", encoding="utf-8") as fh:
            fh.write("# Rules generated\n\nNo rules written yet: %d block(s) of %s to decide.\n\n%s\n" % (len(open_items), notes, gate))
        return msg + "\n" + gate, False
    root = g.write()
    findings, checked = review.check(root, catalogue_md)
    lines = []
    lines.append("Read %s: all %d blocks decided." % (notes, len(g.items)))
    lines.append("Wrote %d files under %s (%s)." % (len(g.written), root, ", ".join("%s %d lines" % (k, len(v)) for k, v in sorted(g.written.items()) if k.endswith(".rules"))[:400]))
    problems = list(g.template_errors) + ["%s: %s" % (f["where"], f["what"]) for f in findings]
    write_report(g, report, root, open_items, problems, findings, checked)
    qs = g.questions + catmod.report_questions(g.cat)
    lines.append("Questions for the owner (also in %s):" % report)
    lines += ["  %d. %s" % (i, q) for i, q in enumerate(qs, 1)]
    if problems:
        gate = "Gate: not passed. %d problem(s) in the rules: %s" % (len(problems), "; ".join(problems[:10]))
    else:
        gate = "Gate: passed. Every block is decided and the check of the rules found nothing: %s." % checked
    lines.append(gate)
    return "\n".join(lines), not open_items and not problems


def write_report(g, path, root, open_items, problems, findings, checked):
    n = g.name
    out = ["# Rules generated", "",
           "From the catalogue `%s`, under `%s`. Every include and table path goes through `$NC_RULES_HOME/%s/`." % (g.catalogue_md, root, g.home), ""]
    out += ["## Files", "", "| File | Lines | What it holds |", "|---|---|---|"]
    what = [("master.include.rules", "every table declaration"), ("common.constants.rules", "values every event starts from"),
            ("master.rules", "entry point: dispatch by trap, then the fields"),
            ("field_normalization.rules", "fields from the catalogue lookup, the clear, @Identifier"),
            ("_traps.lookup", "event id -> name, agent, group, severity, type, expiry, flags"), ("_alarm_ids.lookup", "alarm ID -> event id, alarm name"),
            ("constant.rules", "value maps of enumerated variables")]
    for rel, lines in sorted(g.written.items()):
        w = next((v for k, v in what if rel.endswith(k)), "one case per trap")
        out.append("| %s | %d | %s |" % (rel, len(lines), w))
    out += ["", "## How to install", "",
            "1. Copy the folder `%s/` to `$NC_RULES_HOME/%s/`." % (n, g.home),
            "2. At the top of the probe's main rules file: `include \"$NC_RULES_HOME/%s/config/%s.master.include.rules\"`." % (g.home, n),
            "3. Where the probe's main rules file handles traps: `include \"$NC_RULES_HOME/%s/%s.master.rules\"`." % (g.home, n),
            "4. Check the syntax with the probe's rules syntax check (for example `nco_p_syntax`) before a restart.", ""]
    out += ["## Traps", "", "| Trap | File | Event id | AlertKey | Summary |", "|---|---|---|---|---|"]
    for e in g.entries:
        f = g.files[vendor_key(e)] + (".generic" if e["generic"] != 6 else "") + ".rules"
        if e["aggregated"]:
            out.append("| %s | %s | from the alarm ID | address and index of the alarm | the alarm's name and description |" % (e["name"], f))
            continue
        p = g.plan[e["name"]]
        out.append("| %s | %s | %s | %s | %s |" % (e["name"], f, event_id(e), catmod.esc(p["key"] or "(empty)"), catmod.esc(p["summary"])))
    out += ["", "## Decisions", "", "| Block | Decision | Overrides |", "|---|---|---|"]
    for it in g.items:
        dec = it["decision"] if not it["error"] else "**open: %s**" % it["error"]
        out.append("| %s %s | %s | %s |" % (it["kind"], catmod.esc(it["key"]), catmod.esc(dec), catmod.esc("; ".join("%s: %s" % kv for kv in it["overrides"].items()) or "-")))
    out += ["", "## Check of the rules", "", "Checked: %s." % checked, ""]
    out += ["- %s: %s" % (f["where"], f["what"]) for f in findings] or ["- No finding."]
    if g.template_errors:
        out += [""] + ["- %s" % t for t in g.template_errors]
    out += ["", "## Questions for the owner", ""]
    qs = g.questions + catmod.report_questions(g.cat)
    out += ["%d. %s" % (i, q) for i, q in enumerate(qs, 1)]
    out += ["", "## Not checked", "",
            "- The rules were not loaded by a probe: run the probe's rules syntax check (for example `nco_p_syntax`) on them, then send a test trap of each kind (for example with `snmptrap`) and compare the event with the Traps table above.",
            "- The dispatch keeps one case per trap number: each case builds its summary from its own variables; every value that is data is in a lookup.", ""]
    if open_items or problems:
        out.append("Gate: not passed. %d block(s) without a valid decision; %d problem(s) in the rules." % (len(open_items), len(problems)))
    else:
        out.append("Gate: passed.")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")
