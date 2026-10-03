"""Task 1: the trap catalogue. The trap list's rows matched to the MIBs, with Bob's decisions.

First run writes <report>.notes.md: the facts, and one block per open item with the script's
proposal and an empty `decision:`. Each later run applies the decisions, writes the report
and <report>.json (what the rules are generated from), and prints the gate.
"""
import json
import os
import re

import mib as mibmod
import sheet as sheetmod

STATE = ["down", "up", "failed", "failure", "fail", "degraded", "ok", "on", "off", "lost", "restored",
         "repaired", "rising", "falling", "set", "clear", "cleared", "unreachable", "reachable",
         "error", "started", "stopped", "missing", "insertion", "removal", "inserted", "removed",
         "online", "offline", "overload", "overloaded", "resumed", "recovered", "recovery", "alarm",
         "raise", "raised", "warning", "critical", "major", "minor", "normal", "good", "bad",
         "start", "stop", "begin", "end", "active", "inactive", "available", "unavailable",
         "expired", "fault", "faled"]
RESOLVING = {"up", "ok", "on", "restored", "repaired", "falling", "clear", "cleared", "reachable",
             "stopped", "insertion", "inserted", "online", "resumed", "recovered", "recovery", "normal",
             "good", "available", "end", "stop"}
SEVERITY_DEFAULT = {
    "critical": "5 problem", "major": "4 problem", "minor": "3 problem", "warning": "2 problem",
    "error": "3 problem", "indeterminate": "1 problem", "info": "2 information",
    "informational": "2 information", "information": "2 information", "notice": "2 information",
    "cleared": "1 resolution", "clear": "1 resolution", "normal": "1 resolution",
}
TYPES = {"problem": 1, "resolution": 2, "information": 13}
ID_RE = re.compile(r"\[\s*ID\s*=\s*(\d+)\s*\]", re.I)


# ---------------------------------------------------------------- helpers
def slug(text):
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def tokens(name):
    name = re.sub(r"\[.*?\]", "", name)
    return re.findall(r"[A-Z]+(?=[A-Z][a-z]|\d|\b)|[A-Z]?[a-z]+|[A-Z]+|\d+", name)


SMALL_WORDS = {"is", "are", "the", "to", "has", "have", "been", "was", "a", "an", "of", "now"}


def stem(name):
    """The name without its state words: the members of a problem/clear pair share it."""
    out = []
    for t in tokens(name):
        low = t.lower()
        if low in STATE or (low in SMALL_WORDS and " " in name):
            continue
        for w in sorted(STATE, key=len, reverse=True):
            if len(w) >= 4 and len(low) > len(w) + 3 and low.startswith(w) and w in RESOLVING:
                low = low[len(w):]
                break
        for w in sorted(STATE, key=len, reverse=True):
            if len(w) >= 4 and len(low) > len(w) + 3 and low.endswith(w):
                low = low[:-len(w)]
                break
        out.append(low)
    return " ".join(out)


def resolving_name(name):
    return any(t.lower() in RESOLVING for t in tokens(name)) or name.lower().startswith("clear")


def words(text):
    return set(w for w in re.findall(r"[a-z]{3,}", (text or "").lower()) if w not in
               {"the", "this", "that", "has", "been", "trap", "sent", "will", "for", "and", "with", "from", "set"})


def overlap(a, b):
    wa, wb = words(a), words(b)
    return len(wa & wb) / max(1, len(wa))


def near_oids(oid, known):
    """Known OIDs that differ from oid in exactly one sub-identifier."""
    parts = oid.split(".")
    out = []
    for k in known:
        kp = k.split(".")
        if len(kp) == len(parts) and sum(1 for x, y in zip(kp, parts) if x != y) == 1:
            out.append(k)
    return out


def is_pseudo(oid):
    return not oid.startswith("1.3.6.1.")


def trap_text(t):
    return " ".join([t.get("description", ""), t.get("hints", {}).get("SUMMARY", ""), t["name"]])


def sev_word(w):
    return re.sub(r"\s+", " ", (w or "").strip().lower())


# ---------------------------------------------------------------- rows
def read_rows(trap_list, mibs):
    sheets = sheetmod.read(trap_list)
    tables = sheetmod.tables(sheets)
    known_oids = set(mibs.trap_by_oid) | set(mibmod.GENERIC)
    out_tables = []
    for t in tables:
        tid = "%s@%d" % (t["sheet"], t["header_row"])
        c = t["columns"]
        rows = []
        for rn, cells in t["rows"]:
            g = lambda k: sheetmod.cell(cells, c.get(k))
            r = {"table": tid, "row": rn, "name": g("name").strip(), "oid": g("oid").strip().lstrip("."),
                 "severity": g("severity").strip(), "component": g("component"), "label": g("label"),
                 "description": g("description"), "text": g("text"), "module": g("module"),
                 "other": [x for i, x in enumerate(cells) if x and i not in c.values()],
                 "cells": [x for x in cells if x]}
            m = ID_RE.search(r["name"]) or ID_RE.search(r["label"])
            r["alarm_id"] = int(m.group(1)) if m else None
            r["clean_name"] = re.sub(r"\s*\[.*?\]\s*", "", r["name"]).strip()
            classify(r, mibs, known_oids)
            rows.append(r)
        out_tables.append({"id": tid, "sheet": t["sheet"], "header_row": t["header_row"],
                           "columns": {k: t["header"][v] for k, v in c.items()}, "rows": rows})
    return sheets, out_tables


def classify(r, mibs, known_oids):
    oid, name = r["oid"], r["clean_name"]
    r["cands"] = {}
    if not sheetmod.OID_RE.match(oid or ""):
        r["kind"] = "text"
        return
    by_oid = mibs.trap_by_oid.get(oid) or mibmod.builtin_trap(oid)
    by_name = [t for t in mibs.trap_by_name.get(name.lower(), [])] if name else []
    if not by_name and name:
        b = [mibmod.builtin_trap(o) for o, (g, n) in mibmod.GENERIC.items() if n.lower() == name.lower()]
        by_name = [x for x in b if x]
    obj = mibs.by_oid.get(oid)
    if by_oid and (not name or by_oid["name"].lower() == name.lower()):
        r["kind"], r["trap"] = "match", by_oid
        return
    if by_oid:
        if by_name and by_name[0]["oid"] != oid:
            r["kind"] = "disagree"
            r["cands"] = {"oid": by_oid, "name": by_name[0]}
        else:
            r["kind"] = "name"
            r["cands"] = {"mib": by_oid}
        return
    near = [mibs.trap_by_oid.get(o) or mibmod.builtin_trap(o) for o in near_oids(oid, known_oids)]
    if by_name:
        if any(n["oid"] == by_name[0]["oid"] for n in near):
            r["kind"] = "oid"
            r["cands"] = {"mib": by_name[0]}
        elif len(near) == 1:
            r["kind"] = "disagree"
            r["cands"] = {"oid": near[0], "name": by_name[0]}
        else:
            r["kind"] = "oid"
            r["cands"] = {"mib": by_name[0]}
        return
    named_obj = mibs.objects.get(name) if name else None
    if (obj and obj.get("kind") not in ("NOTIFICATION-TYPE", "TRAP-TYPE")) or named_obj or (not name and not near):
        r["kind"] = "object"
        r["object"] = (obj or named_obj or {}).get("name", "")
        return
    if is_pseudo(oid) and r["alarm_id"] is not None:
        r["kind"] = "alarm"
        return
    if len(near) == 1:
        r["kind"] = "oid"
        r["cands"] = {"mib": near[0]}
        return
    r["kind"] = "missing"


# ---------------------------------------------------------------- notes
BLOCK_RE = re.compile(r"(?m)^### +(\S+) +(.+?)\s*$")


SECTION = "## Your decisions"
SECTION_HELP = ("Write your decisions here in one edit, one line per block: `- <block title>: <decision>`, where the "
                "block title is what follows `### ` (for example `- severity major: as proposed`); for one trap or file of "
                "a block: `- <block title> > <name>: <decision>`. The next run moves each line onto its block. A decision "
                "on a block's own `decision:` line counts too.")


def section_lines(text):
    """The '- <title>[ > name]: decision' lines of the Your decisions section."""
    i = text.find(SECTION)
    if i < 0:
        return []
    body = text[i + len(SECTION):]
    j = body.find("\n### ")
    k = body.find("\n## ")
    end = min(x for x in (j, k, len(body)) if x >= 0)
    out = []
    for line in body[:end].splitlines():
        m = re.match(r"^\s*-\s+(.+?)\s*:\s+(.+?)\s*$", line)
        if m and not m.group(1).startswith("`"):
            title, name = (m.group(1).split(" > ", 1) + [None])[:2]
            out.append((title.strip(), name.strip() if name else None, m.group(2)))
    return out


def read_notes(path):
    """{(kind, key): {"decision": str, "overrides": {name: decision}}}"""
    out = {}
    if not os.path.exists(path):
        return out
    text = open(path, encoding="utf-8").read()
    marks = list(BLOCK_RE.finditer(text))
    for i, m in enumerate(marks):
        body = text[m.end(): marks[i + 1].start() if i + 1 < len(marks) else len(text)]
        body = body.split("\n## ")[0]
        d = {"decision": "", "overrides": {}, "fields": {}}
        in_over = False
        for line in body.splitlines():
            s = line.strip()
            if s.lower().startswith("decision:"):
                d["decision"] = s.split(":", 1)[1].strip()
                in_over = True
            elif s.lower().startswith("overrides:"):
                in_over = True
            elif in_over and s.startswith("- ") and ":" in s:
                k, v = s[2:].split(":", 1)
                d["overrides"][k.strip()] = v.strip()
            elif re.match(r"^[a-z][a-z ]+:", s):
                k, v = s.split(":", 1)
                d["fields"][k.strip().lower()] = v.strip()
        out[(m.group(1), m.group(2).strip())] = d
    for title, name, dec in section_lines(text):
        kind, _, key = title.partition(" ")
        d = out.setdefault((kind, key.strip()), {"decision": "", "overrides": {}, "fields": {}, "orphan": True})
        if name:
            d["overrides"][name] = dec
        else:
            d["decision"] = dec
    return out


def section_text(items, notes):
    """The section, empty but for the lines that name no block."""
    titles = set("%s %s" % (it["kind"], it["key"]) for it in items)
    left = ["- %s%s: %s" % (k[0] + " " + k[1], "", v["decision"]) for k, v in notes.items()
            if v.get("orphan") and "%s %s" % k not in titles and v["decision"]]
    out = [SECTION, "", SECTION_HELP, ""]
    if left:
        out += ["<!-- these lines name no block: check the title -->"] + left + [""]
    return out


ACCEPT = ("proposal", "as proposed", "accept", "accepted", "agreed", "yes")


def accepted(dec, proposal):
    if dec.lower() in ACCEPT:
        return proposal
    return dec


# ---------------------------------------------------------------- the catalogue
class Catalogue:
    def __init__(self, trap_list, mib_paths, notes_path):
        self.trap_list, self.mib_paths, self.notes_path = trap_list, mib_paths, notes_path
        self.mibs = mibmod.load(mib_paths)
        self.sheets, self.tables = read_rows(trap_list, self.mibs)
        self.notes = read_notes(notes_path)
        self.items = []          # open items: dict(kind, key, title, facts, choices, proposal, decision, error)
        self.questions = []
        self.facts = []

    # -- items
    def item(self, kind, key, facts, choices, proposal, check, group=None, suggested=None):
        n = self.notes.get((kind, key), {"decision": "", "overrides": {}, "fields": {}})
        dec = accepted(n["decision"], proposal)
        it = {"kind": kind, "key": key, "facts": facts, "choices": choices, "proposal": proposal,
              "decision": dec, "raw": n["decision"], "overrides": n["overrides"], "error": "", "group": group,
              "suggested": suggested or {}}
        if not n["decision"]:
            it["error"] = "no decision"
        else:
            err = check(dec)
            if err:
                it["error"] = err
            for k, v in n["overrides"].items():
                e = check(accepted(v, proposal))
                if e:
                    it["error"] = "%s: %s" % (k, e)
        self.items.append(it)
        return it

    def value(self, it, name=None):
        if name and name in it["overrides"]:
            return accepted(it["overrides"][name], it["proposal"])
        sug = it.get("suggested", {})
        if name and name in sug and (it["error"] or it["raw"].lower() in ACCEPT):
            return sug[name]
        return it["decision"] if not it["error"] else it["proposal"]

    # -- build
    def build(self):
        self.decide_tables()
        self.decide_rows()
        self.decide_severities()
        self.make_entries()
        self.decide_aggregated()
        self.decide_conflicts()
        self.decide_pairs()
        self.finish()

    def decide_tables(self):
        keyset = {}
        for t in self.tables:
            keyset[t["id"]] = set(r["oid"] if r["kind"] != "alarm" else "id%s" % r["alarm_id"]
                                  for r in t["rows"] if r["kind"] not in ("text", "object"))
        carriers = [x for x in self.mibs.traps if any(vb["syntax"] == "OBJECT IDENTIFIER" for vb in x["varbinds"])
                    and len(x["varbinds"]) >= 2]
        self.roles, self.carried = {}, {}
        for t in self.tables:
            kinds = [r["kind"] for r in t["rows"]]
            n_obj, n_trap = kinds.count("object"), sum(1 for k in kinds if k not in ("text", "object"))
            sup = [o["id"] for o in self.tables if o["id"] != t["id"] and keyset[t["id"]] and
                   keyset[t["id"]] <= keyset[o["id"]] and len(keyset[o["id"]]) > len(keyset[t["id"]])]
            facts = ["%d trap rows, %d object rows (variables, not traps), %d other rows; columns: %s" % (
                n_trap, n_obj, kinds.count("text"), ", ".join("%s=%s" % (k, v) for k, v in t["columns"].items()))]
            trap_rows = [r for r in t["rows"] if r["kind"] not in ("text", "object")]
            if 0 < len(trap_rows) <= 5:
                facts.append("its trap rows: %s" % ", ".join("%s (%s)" % (r["clean_name"] or r["oid"], r["oid"]) for r in trap_rows))
            if n_obj and n_trap:
                facts.append("the decision applies to its trap rows; its object rows are variables and are left out")
            var_of = {}
            for r in t["rows"]:
                if r["kind"] == "object" and r.get("object"):
                    for x in self.mibs.traps:
                        if any(vb["name"] == r["object"] for vb in x["varbinds"]):
                            var_of.setdefault(r["object"], x["name"])
                            break
            if sup:
                facts.append("every trap row is also in table %s: this table marks some of its traps" % sup[0])
                proposal = "flag " + slug(t["sheet"])
            elif n_obj and n_obj >= n_trap:
                proposal = "objects"
                if var_of and len(var_of) >= n_obj / 2:
                    facts.append("%d of its objects are variables of MIB traps (for example %s of %s): it describes their variables"
                                 % (len(var_of), list(var_of)[0], list(var_of.values())[0]))
                elif carriers:
                    facts.append("MIB traps that carry another object's OID and value (objects can arrive in them): %s"
                                 % ", ".join("%s (%s)" % (x["name"], x["module"]) for x in carriers[:6]))
                    std = [x["name"] for x in carriers if x["module"] == "DISMAN-EVENT-MIB" and re.match(r"^mteTrigger(Fired|Rising|Falling)$", x["name"])]
                    if std:
                        proposal = "objects in " + ", ".join(sorted(std, key=lambda n: ["mteTriggerFired", "mteTriggerRising", "mteTriggerFalling"].index(n)))
                        facts.append("the proposal: threshold monitors send these values in the standard event MIB's triggers")
            elif n_trap == 0:
                proposal = "skip"
            else:
                proposal = "traps"
            texts = [r for r in t["rows"] if r["kind"] == "text"]
            if texts:
                facts.append("other rows (read them, they may say how the traps are sent):")
                for r in texts[:40]:
                    facts.append("  row %d: %s" % (r["row"], " | ".join(r["cells"])[:300]))

            def check(d):
                if re.match(r"^(traps|objects|skip)$", d) or re.match(r"^flag [a-z0-9_]+$", d):
                    return ""
                m = re.match(r"^objects in ([\w-]+(?:, *[\w-]+)*)$", d)
                if m:
                    bad = [n for n in re.split(r", *", m.group(1)) if not self.mibs.trap_by_name.get(n.lower())]
                    return ("not traps in the MIBs: " + ", ".join(bad)) if bad else ""
                return "choose traps, objects, objects in <trap>[, <trap>], skip or flag <word>"
            it = self.item("table", t["id"], facts, "traps | objects | objects in <trap>[, <trap>] | skip | flag <word>", proposal, check)
            role = self.value(it)
            if role.startswith("objects in "):
                self.carried[t["id"]] = re.split(r", *", role[len("objects in "):])
                role = "objects"
            self.roles[t["id"]] = role

    def decide_rows(self):
        """One block per sheet trap (name and OID) that does not match the MIBs, whatever tables list it."""
        self.row_choice = {}
        seen = {}
        for t in self.tables:
            if self.roles[t["id"]] in ("skip", "objects"):
                continue
            for r in t["rows"]:
                if r["kind"] in ("name", "oid", "disagree"):
                    seen.setdefault((r["kind"], r["clean_name"], r["oid"]), []).append(r)
        for (k, name, oid), rows in seen.items():
            r = rows[0]
            key = "%s %s" % (name or oid, oid)
            where = "; ".join("%s row %d" % (x["table"], x["row"]) for x in rows)
            facts = ["sheet (%s): %s %s, severity %s, description: %s" % (where, name, oid, r["severity"] or "-", (r["description"] or r["label"] or "-")[:160])]
            if k == "name":
                c = r["cands"]["mib"]
                facts.append("MIB at that OID: %s (%s): %s" % (c["name"], c["module"], trap_text(c)[:160]))
                it = self.item("row", key, facts, "mib | drop", "mib", lambda d: "" if d in ("mib", "drop") else "choose mib or drop")
            elif k == "oid":
                c = r["cands"]["mib"]
                facts.append("MIB: %s is %s (%s): %s" % (c["name"], c["oid"], c["module"], trap_text(c)[:160]))
                it = self.item("row", key, facts, "mib | sheet | drop", "mib", lambda d: "" if d in ("mib", "sheet", "drop") else "choose mib, sheet or drop")
            else:
                a, b = r["cands"]["oid"], r["cands"]["name"]
                facts.append("MIB at (or one digit from) the sheet's OID: %s %s (%s): %s" % (a["name"], a["oid"], a["module"], trap_text(a)[:160]))
                facts.append("MIB under the sheet's name: %s %s: %s" % (b["name"], b["oid"], trap_text(b)[:160]))
                desc = r["description"] or r["label"] or r["text"]
                prop = "oid" if overlap(desc, trap_text(a)) >= overlap(desc, trap_text(b)) else "name"
                facts.append("the sheet's description matches the trap at the %s better" % ("OID" if prop == "oid" else "name"))
                it = self.item("row", key, facts, "oid | name | drop", prop, lambda d: "" if d in ("oid", "name", "drop") else "choose oid, name or drop")
                ch = self.value(it)
                if ch in ("oid", "name"):
                    other = b if ch == "oid" else a
                    self.questions.append("The trap list names %s with the OID %s; in the MIB these are two traps, %s (%s) and %s (%s). "
                                          "The rules use %s: is that the one the device sends?" % (
                                              name, oid, b["name"], b["oid"], a["name"], a["oid"], r["cands"][ch]["name"]))
            for x in rows:
                self.row_choice[(x["table"], x["row"])] = self.value(it)
        missing = {}
        for t in self.tables:
            if self.roles[t["id"]] in ("skip", "objects"):
                continue
            for r in t["rows"]:
                if r["kind"] == "missing":
                    missing.setdefault((r["clean_name"], r["oid"]), []).append(r)
        if missing:
            facts = ["no MIB read defines these OIDs or names. Keep them from the sheet (their variables are not named "
                     "or checked) or drop them; a decision for one trap goes under overrides as - <name>: sheet|drop:"]
            for (name, oid), rows in sorted(missing.items(), key=lambda x: x[0][1]):
                r = rows[0]
                src = sheetmod.cell(r["cells"], 0) if False else ""
                facts.append("  %s %s %s (%s)" % (name, oid, r["severity"] or "-", "; ".join("%s row %d" % (x["table"], x["row"]) for x in rows)))
            it = self.item("missing", "traps", facts, "sheet | drop", "sheet", lambda d: "" if d in ("sheet", "drop") else "choose sheet or drop")
            kept = []
            for (name, oid), rows in missing.items():
                v = self.value(it, name)
                for x in rows:
                    self.row_choice[(x["table"], x["row"])] = v
                if v == "sheet":
                    kept.append((name, oid))

        for t in self.tables:
            if self.roles[t["id"]] in ("skip", "objects"):
                continue
            rem = []
            last_text = ""
            for r in t["rows"]:
                if r["kind"] != "text":
                    continue
                names = [c for c in r["cells"] if self.known_name(c)]
                text = " ".join(c for c in r["cells"] if c not in names)
                if names:
                    rem.append((r, names, text or ("(no text of its own; the row above says: %s)" % last_text if last_text else "")))
                    last_text = text or last_text
            if rem:
                facts = ["rows after the table that name traps and say something about them:"]
                facts += ["  row %d: %s: %s" % (r["row"], ", ".join(n), tx or "(no text)") for r, n, tx in rem]
                it = self.item("remark", t["id"], facts, "drop | keep (one trap: - <name>: drop|keep under overrides)", "drop",
                               lambda d: "" if d in ("drop", "keep") else "choose drop or keep")
                self.dropped_names = getattr(self, "dropped_names", set())
                for r, names, tx in rem:
                    for n in names:
                        if self.value(it, n) == "drop":
                            self.dropped_names.add(re.sub(r"\s*\[.*?\]", "", n).strip().lower())

    def known_name(self, name):
        n = re.sub(r"\s*\[.*?\]", "", name).strip().lower()
        return bool(n) and (bool(self.mibs.trap_by_name.get(n)) or any(r["clean_name"].lower() == n for t in self.tables for r in t["rows"] if r["kind"] != "text"))

    def decide_severities(self):
        self.sev_override = {}
        seen = {}
        for t in self.tables:
            if self.roles[t["id"]] != "traps":
                continue
            for r in t["rows"]:
                if r["kind"] in ("text", "object") or not r["severity"]:
                    continue
                seen.setdefault(sev_word(r["severity"]), []).append(r)
        self.sevmap = {}
        for w, rows in sorted(seen.items()):
            facts = ["%d rows, e.g. %s" % (len(rows), ", ".join(sorted(set(r["clean_name"] for r in rows))[:5]))]

            def check(d):
                m = re.match(r"^([0-5]) (problem|resolution|information)$", d)
                return "" if m else "write <severity 0-5> problem|resolution|information"
            it = self.item("severity", w, facts, "<0-5> problem | <0-5> resolution | <0-5> information (one trap: - <trap>: <0-5> <type> under overrides)",
                           SEVERITY_DEFAULT.get(w, ""), check)
            v = self.value(it)
            m = re.match(r"^([0-5]) (problem|resolution|information)$", v or "")
            self.sevmap[w] = (int(m.group(1)), m.group(2)) if m else None
            for name, ov in it["overrides"].items():
                mo = re.match(r"^([0-5]) (problem|resolution|information)$", accepted(ov, it["proposal"]))
                if mo:
                    self.sev_override[name.lower()] = (int(mo.group(1)), mo.group(2))

    def make_entries(self):
        self.entries, self.alarms = {}, {}
        dropped = getattr(self, "dropped_names", set())
        for t in self.tables:
            role = self.roles[t["id"]]
            if role in ("skip", "objects"):
                continue
            for r in t["rows"]:
                if r["kind"] in ("text", "object"):
                    continue
                if r["clean_name"].lower() in dropped:
                    continue
                choice = self.row_choice.get((t["id"], r["row"]))
                trap = None
                if r["kind"] == "match":
                    trap = r["trap"]
                elif r["kind"] in ("name", "oid") and choice == "mib":
                    trap = r["cands"]["mib"]
                elif r["kind"] == "disagree" and choice in ("oid", "name"):
                    trap = r["cands"][choice]
                elif choice == "sheet":
                    ent, gen, spec = mibmod.v1_form(r["oid"])
                    trap = {"name": r["clean_name"] or r["oid"], "module": self.sheet_module(t, r), "kind": "SHEET", "oid": r["oid"],
                            "enterprise": ent, "generic": gen, "specific": spec, "varbinds": [],
                            "description": r["description"], "hints": {}, "status": ""}
                elif choice == "drop":
                    continue
                if role.startswith("flag "):
                    flag = role.split(" ", 1)[1]
                    key = trap["oid"] if trap else ("alarm:%s" % r["alarm_id"] if r["alarm_id"] is not None else None)
                    self.flags = getattr(self, "flags", [])
                    self.flags.append((flag, key, r))
                    continue
                if r["alarm_id"] is not None:
                    self.alarms.setdefault(r["alarm_id"], []).append((r, trap))
                if trap is None:
                    continue
                e = self.entries.setdefault(trap["oid"], {"trap": trap, "rows": []})
                e["rows"].append(r)
        for tid, names in getattr(self, "carried", {}).items():
            for n in names:
                tr = self.mibs.trap_by_name[n.lower()][0]
                e = self.entries.setdefault(tr["oid"], {"trap": tr, "rows": []})
                e.setdefault("carries", []).append(tid)
        # flags mark entries and alarms
        for flag, key, r in getattr(self, "flags", []):
            hit = False
            if key in self.entries:
                self.entries[key].setdefault("flags", set()).add(flag)
                hit = True
            if r["alarm_id"] is not None and r["alarm_id"] in self.alarms:
                self.alarm_flags = getattr(self, "alarm_flags", {})
                self.alarm_flags.setdefault(r["alarm_id"], set()).add(flag)
                hit = True
            if not hit:
                self.facts.append("table %s row %d (%s) marks a trap that is in no trap table" % (r["table"], r["row"], r["clean_name"]))

    def decide_conflicts(self):
        for oid, e in sorted(self.entries.items()):
            if e.get("aggregated"):
                continue
            sevs = {}
            for r in e["rows"]:
                if r["severity"]:
                    sevs.setdefault(sev_word(r["severity"]), []).append(r)
            mapped = set(self.sevmap.get(w) for w in sevs)
            if len(mapped) > 1:
                facts = ["%s %s is listed with %d severities:" % (e["trap"]["name"], oid, len(sevs))]
                for w, rs in sevs.items():
                    for r in rs:
                        facts.append("  %s: %s row %d: %s" % (w, r["table"], r["row"], " | ".join(
                            x for x in (re.sub(r"\s+", " ", r["label"] or ""), re.sub(r"\s+", " ", r["description"] or "")[:120], r["text"] or "") if x) or "(no text)"))
                res = [w for w in sevs if (self.sevmap.get(w) or (0, ""))[1] == "resolution"]
                prop = res[0] if res else max(sevs, key=lambda w: (self.sevmap.get(w) or (0, ""))[0])
                it = self.item("conflict", e["trap"]["name"], facts, " | ".join(sevs), prop,
                               lambda d, s=sevs: "" if d in s else "choose one of: " + ", ".join(s))
                e["severity_word"] = self.value(it)
                self.questions.append("%s has severity %s in different tables; the rules use %s: is that right?" % (
                    e["trap"]["name"], " and ".join(sevs), e["severity_word"]))
            elif sevs:
                e["severity_word"] = list(sevs)[0]
            else:
                e["severity_word"] = ""
            if not e["severity_word"]:
                t = e["trap"]
                hint = sev_word(t.get("hints", {}).get("SEVERITY", ""))
                prop = hint if hint in self.sevmap else ("cleared" if resolving_name(t["name"]) and "cleared" in self.sevmap else "")
                facts = ["%s (%s) has no severity in the trap list%s%s" % (
                    t["name"], t.get("module", ""), (": it carries the objects of table %s" % ", ".join(e["carries"])) if e.get("carries") else "",
                    ("; its MIB says %s" % hint) if hint else "")]
                it = self.item("severity-of", t["name"], facts, " | ".join(sorted(w for w in self.sevmap if self.sevmap[w])), prop,
                               lambda d: "" if self.sevmap.get(d) else "choose one of the severity words above")
                e["severity_word"] = self.value(it) if self.sevmap.get(self.value(it)) else ""
            sm = self.sevmap.get(e["severity_word"]) if e["severity_word"] else None
            names = [e["trap"]["name"].lower()] + [r["clean_name"].lower() for r in e["rows"]]
            for n in names:
                if n in self.sev_override:
                    sm = self.sev_override[n]
                    e["severity_word"] = "%s (decided for this trap)" % e["severity_word"]
                    break
            e["severity"], e["type"] = (sm if sm else (None, None))

    def decide_aggregated(self):
        """Rows whose OID is an alarm ID arrive inside a trap that carries many alarms."""
        alarm_rows = [r for t in self.tables if self.roles[t["id"]] == "traps" for r in t["rows"] if r["kind"] == "alarm"]
        self.aggregated = None
        if not alarm_rows:
            return
        cands = []
        for t in self.mibs.traps:
            idx = [i for vb in t["varbinds"] for i in vb.get("table_index", [])]
            hit = [i for i in idx if re.search(r"alarm.*(type|id)|alarm$", i, re.I)]
            if hit:
                cands.append((t, hit[0], idx))
        in_list = set(self.entries)
        cands.sort(key=lambda c: (c[0]["oid"] not in in_list, resolving_name(c[0]["name"]), c[0]["name"]))
        facts = ["%d rows have an alarm ID instead of an SNMP OID (e.g. %s)" % (
            len(alarm_rows), ", ".join("%s [ID=%d] %s" % (r["clean_name"], r["alarm_id"], r["oid"]) for r in alarm_rows[:4]))]
        prop = ""
        if cands:
            t, idxname, idx = cands[0]
            clear = [c[0]["name"] for c in cands if c[0] is not t and stem(c[0]["name"]) == stem(t["name"])]
            facts.append("MIB traps whose variables are indexed by an alarm ID: %s" % ", ".join(
                "%s (INDEX %s)" % (c[0]["name"], ", ".join(c[2][:len(c[2]) // max(1, len(c[0]['varbinds']))] or c[2])) for c in cands[:4]))
            prop = "%s, alarm id %s%s" % (t["name"], idxname, (", cleared by %s" % clear[0]) if clear else "")
        facts.append("every row of the trap tables that has an alarm ID goes into the alarm-ID lookup (%d IDs)" % len(self.alarms))

        def check(d):
            if d == "skip":
                return ""
            m = re.match(r"^([\w-]+), alarm id ([\w-]+)(?:, cleared by ([\w-]+))?$", d)
            if not m:
                return "write: <trap>, alarm id <index name>[, cleared by <trap>]"
            for n in (m.group(1), m.group(3)):
                if n and not self.mibs.trap_by_name.get(n.lower()):
                    return "%s is not a trap in the MIBs" % n
            return ""
        it = self.item("aggregated", "alarm IDs", facts, "<trap>, alarm id <index name>[, cleared by <trap>] | skip", prop, check)
        v = self.value(it)
        m = re.match(r"^([\w-]+), alarm id ([\w-]+)(?:, cleared by ([\w-]+))?$", v or "")
        if m:
            rising = self.mibs.trap_by_name[m.group(1).lower()][0]
            falling = self.mibs.trap_by_name[m.group(3).lower()][0] if m.group(3) else None
            idx = rising["varbinds"][0].get("table_index", []) if rising["varbinds"] else []
            self.aggregated = {"trap": rising["name"], "oid": rising["oid"], "alarm_index": m.group(2),
                               "index": idx, "cleared_by": falling["name"] if falling else None,
                               "cleared_by_oid": falling["oid"] if falling else None}
            for tr in [rising] + ([falling] if falling else []):
                e = self.entries.setdefault(tr["oid"], {"trap": tr, "rows": [], "severity_word": "", "severity": None, "type": None})
                e["aggregated"] = True
                if tr is falling:
                    e["severity"], e["type"] = 1, "resolution"
                elif e.get("severity") is None:
                    e["severity"], e["type"] = None, "problem"

    def sheet_module(self, t, r):
        """A module name for a trap no MIB defines: the MIB file the sheet names for it, else the MIB module that
        defines other traps of the same enterprise, else ENTERPRISE-<number>."""
        mods = [x.get("module") for x in t["rows"][:t["rows"].index(r) + 1] if x.get("module")]
        m = re.search(r"([A-Za-z][\w-]*)\.mib\b", mods[-1]) if mods else None
        if m:
            return m.group(1).upper() + ("" if m.group(1).upper().endswith("MIB") else "-MIB")
        ent = mibmod.v1_form(r["oid"])[0]
        same = sorted(set(x["module"] for x in self.mibs.traps if x["enterprise"] == ent))
        if len(same) == 1:
            return same[0]
        num = re.match(r"^1\.3\.6\.1\.4\.1\.(\d+)", r["oid"])
        return "ENTERPRISE-%s" % (num.group(1) if num else ent.replace(".", "-"))

    def family(self, e):
        t = e["trap"]
        if t.get("module"):
            return t["module"]
        r = e["rows"][0] if e["rows"] else None
        if r:
            return r["table"].split("@")[0].strip()[:48]
        return "sheet"

    def decide_pairs(self):
        fam = {}
        for oid, e in self.entries.items():
            if e.get("aggregated") or e.get("type") in (None, "information"):
                continue
            fam.setdefault(self.family(e), []).append(e)
        unpaired_p, unpaired_r = {}, {}
        for module, es in sorted(fam.items()):
            groups = {}
            for e in es:
                groups.setdefault(stem(e["trap"]["name"]), []).append(e)
            groups = split_opposites(groups)
            listed = {st: g for st, g in groups.items() if len(g) > 1}
            if listed:
                facts = ["groups found by name: a clear clears every problem of its group (same node and key):"]
                for st, g in sorted(listed.items()):
                    facts.append("  %s: %s" % (st, ", ".join("%s (%s)" % (x["trap"]["name"], x["type"]) for x in g)))
                names = set(x["trap"]["name"] for x in es)
                it = self.item("groups", module, facts, "as listed (one trap: - <trap>: group <words> under overrides)", "as listed",
                               lambda d, n=names: "" if d == "as listed" or re.match(r"^group [\w -]+$", d) else "write as listed, or group <words> for one trap")
                for k in it["overrides"]:
                    if k not in names:
                        it["error"] = "%s is not a trap of %s" % (k, module)
                proposed = {x["trap"]["name"]: st for st, g in groups.items() for x in g}
                regroup = {}
                for e in es:
                    v = self.value(it, e["trap"]["name"])
                    regroup.setdefault(v[6:].strip() if v.startswith("group ") else proposed[e["trap"]["name"]], []).append(e)
                groups = regroup
            for st, g in groups.items():
                probs = [e for e in g if e["type"] == "problem"]
                res = [e for e in g if e["type"] == "resolution"]
                for e in g:
                    e["group"] = "%s / %s" % (module, st)
                for e in probs if not res else []:
                    unpaired_p.setdefault(module, []).append(e)
                for e in res if not probs else []:
                    unpaired_r.setdefault(module, []).append(e)
        similar = {}
        for module, es in unpaired_p.items():
            similar.update(match_similar(es, unpaired_r.get(module, [])))
        self.similar = similar
        for module, es in sorted(unpaired_p.items()):
            facts = ["problems with no clearing trap found by name (each stays until cleared by hand unless "
                     "you name its clear):"]
            proposal_over = {}
            for e in es:
                t = e["trap"]
                cw = clear_value(t)
                why = ""
                if t["name"] in similar:
                    proposal_over[t["name"]] = "cleared by %s" % similar[t["name"]]
                    why = "; a clear with a similar name: %s (check that it undoes this problem)" % similar[t["name"]]
                elif cw:
                    proposal_over[t["name"]] = "clear when %s = %s" % (cw[0], cw[1])
                    why = "; variable %s %s" % (cw[0], cw[2])
                elif event_like(t["name"]):
                    proposal_over[t["name"]] = "information"
                    why = "; its name says it reports an event, not a state"
                facts.append("  %s (%s)%s" % (t["name"], e["severity_word"], why))

            def check(d, names=set(x["trap"]["name"] for x in self.entries.values())):
                if d in ("none", "information"):
                    return ""
                m = re.match(r"^cleared by ([\w-]+)$", d)
                if m:
                    return "" if m.group(1) in names else "%s is not in the catalogue" % m.group(1)
                if re.match(r"^clear when [\w-]+ = [\w.-]+$", d):
                    return ""
                return "choose none, information, cleared by <trap> or clear when <variable> = <value>"
            it = self.item("unpaired", module, facts, "none | information | cleared by <trap> | clear when <variable> = <value>",
                           "none", check, suggested=proposal_over)
            for e in es:
                v = self.value(it, e["trap"]["name"])
                e["clear"] = v
                if v == "information":
                    e["type"] = "information"
                elif v.startswith("cleared by "):
                    other = v.split(" ", 2)[2]
                    for o in self.entries.values():
                        if o["trap"]["name"] == other:
                            o["group"] = e["group"]
                elif v.startswith("clear when "):
                    m = re.match(r"^clear when ([\w-]+) = ([\w.-]+)$", v)
                    names = [vb["name"] for vb in e["trap"]["varbinds"]]
                    if m and m.group(1) not in names:
                        it["error"] = "%s: %s is not a variable of this trap (%s)" % (e["trap"]["name"], m.group(1), ", ".join(names) or "none named")
                    e["clear_when"] = (m.group(1), m.group(2)) if m else None
        rev = {v: k for k, v in similar.items()}
        for module, es in sorted(unpaired_r.items()):
            facts = ["clears with no problem found by name:"] + ["  %s (%s)%s" % (
                e["trap"]["name"], e["severity_word"], ("; a problem with a similar name: %s" % rev[e["trap"]["name"]]) if e["trap"]["name"] in rev else "")
                for e in es]
            sug = {e["trap"]["name"]: "clears %s" % rev[e["trap"]["name"]] for e in es if e["trap"]["name"] in rev}
            it = self.item("unpaired-clear", module, facts, "information | clears <trap>", "information",
                           lambda d: "" if d == "information" or re.match(r"^clears [\w-]+$", d) else "choose information or clears <trap>",
                           suggested=sug)
            for e in es:
                v = self.value(it, e["trap"]["name"])
                if v == "information":
                    e["type"] = "information"
                    e["severity"] = 2 if e["severity"] in (None, 1) else e["severity"]
                else:
                    other = v.split(" ", 1)[1]
                    for o in self.entries.values():
                        if o["trap"]["name"] == other:
                            e["group"] = o.get("group")

    def finish(self):
        # alarm-ID table
        self.alarm_rows = []
        flags = getattr(self, "alarm_flags", {})
        for aid, pairs in sorted(self.alarms.items()):
            r, trap = pairs[0]
            w = sev_word(r["severity"])
            sm = self.sev_override.get(r["clean_name"].lower()) or self.sevmap.get(w)
            self.alarm_rows.append({"id": aid, "name": r["clean_name"], "label": re.sub(r"\s*\[.*?\]", "", r["label"]).strip(),
                                    "severity_word": w, "severity": sm[0] if sm else None, "type": sm[1] if sm else None,
                                    "component": r["component"], "text": r["text"], "trap": trap["name"] if trap else "",
                                    "flags": sorted(flags.get(aid, set())), "rows": ["%s row %d" % (x[0]["table"], x[0]["row"]) for x in pairs]})
        fam = {}
        for a in self.alarm_rows:
            a["group"] = "alarm / " + (stem(a["label"] or a["name"]) or str(a["id"]))
            fam.setdefault(a["group"], set()).add(a["type"])
        for a in self.alarm_rows:
            a["paired"] = fam[a["group"]] >= {"problem", "resolution"}
        if self.alarm_rows and not self.aggregated:
            self.facts.append("alarm IDs are listed but no trap carries them (aggregated: skip)")
        for e in self.entries.values():
            e["flags"] = sorted(e.get("flags", set()))
        keys = {}
        for oid, e in self.entries.items():
            t = e["trap"]
            keys.setdefault((t["enterprise"], t["generic"], t["specific"]), []).append(t["name"])
        for k, names in keys.items():
            if len(names) > 1:
                self.facts.append("two traps arrive as the same enterprise/generic/specific %s: %s" % (k, ", ".join(names)))
        sheet_only = sorted(e["trap"]["name"] for e in self.entries.values() if e["trap"]["kind"] == "SHEET")
        if sheet_only:
            prefixes = sorted(set(e["trap"]["enterprise"] for e in self.entries.values() if e["trap"]["kind"] == "SHEET"))
            self.questions.insert(0, "No MIB was supplied for %d trap(s) of the catalogue (%s; enterprises %s): can the MIBs be "
                                     "sent, so that their variables are named and checked?" % (
                                         len(sheet_only), ", ".join(sheet_only[:6]) + (", ..." if len(sheet_only) > 6 else ""), ", ".join(prefixes[:6])))
        missing_sev = [e["trap"]["name"] for e in self.entries.values() if e.get("severity") is None and not e.get("aggregated")]
        if missing_sev:
            self.facts.append("no severity in the list for: %s" % ", ".join(sorted(missing_sev)))

    # -- output
    def gate(self):
        open_items = [it for it in self.items if it["error"]]
        problems = []
        for e in self.entries.values():
            if e.get("severity") is None and not e.get("aggregated"):
                problems.append("%s has no severity" % e["trap"]["name"])
        if self.alarm_rows and self.aggregated:
            for a in self.alarm_rows:
                if a["severity"] is None:
                    problems.append("alarm ID %d has no severity" % a["id"])
        return open_items, problems

    def data(self):
        def entry(oid, e):
            t = e["trap"]
            return {"name": t["name"], "module": t.get("module", ""), "oid": oid, "source": t["kind"],
                    "enterprise": t["enterprise"], "generic": t["generic"], "specific": t["specific"],
                    "varbinds": [dict({k: v for k, v in vb.items() if k != "description"},
                                      about=re.sub(r"\s+", " ", vb.get("description") or "").split(". ")[0][:80]) for vb in t["varbinds"]],
                    "description": t.get("description", ""), "summary_hint": t.get("hints", {}).get("SUMMARY", ""), "type_hint": t.get("hints", {}).get("TYPE", ""),
                    "summary_args": [int(x) for x in re.findall(r"\d+", t.get("hints", {}).get("ARGUMENTS", ""))],
                    "severity_word": e.get("severity_word", ""), "severity": e.get("severity"), "type": e.get("type"),
                    "group": e.get("group", ""), "family": self.family(e), "clear_when": e.get("clear_when"), "flags": e.get("flags", []),
                    "aggregated": bool(e.get("aggregated")),
                    "rows": [{k: r[k] for k in ("table", "row", "name", "oid", "severity", "component", "label", "description", "text", "alarm_id")} for r in e["rows"]]}
        return {"trap_list": self.trap_list, "mibs": self.mib_paths,
                "entries": [entry(oid, e) for oid, e in sorted(self.entries.items(), key=lambda x: (x[1]["trap"].get("module", ""), x[1]["trap"]["name"]))],
                "alarms": self.alarm_rows, "aggregated": self.aggregated, "questions": self.questions, "facts": self.facts}


OPPOSITES = [("removal", "insertion"), ("removed", "inserted"), ("offline", "online"), ("off", "on"), ("down", "up"),
             ("lost", "restored"), ("lost", "established"), ("unreachable", "reachable"), ("rising", "falling"),
             ("set", "clear"), ("start", "stop"), ("started", "stopped"), ("unavailable", "available"), ("inactive", "active")]
EVENT_WORDS = {"start", "restart", "boot", "change", "changed", "conf", "config", "configuration", "update", "updated",
               "login", "logged", "logout", "add", "added", "delete", "deleted", "export", "import", "registered", "info"}


def state_words(name):
    return [t.lower() for t in tokens(name) if t.lower() in STATE]


def split_opposites(groups):
    """Split a group that holds several problems and clears when each problem has its own opposite clear
    (Removal/Insertion, Offline/Online); what has no opposite stays in the group."""
    out = {}
    for st, g in groups.items():
        probs = [e for e in g if e["type"] == "problem"]
        res = [e for e in g if e["type"] == "resolution"]
        if len(probs) < 2 and len(res) < 2:
            out[st] = g
            continue
        left = list(g)
        for p in probs:
            ps = state_words(p["trap"]["name"])
            for r in res:
                if r not in left:
                    continue
                rs = state_words(r["trap"]["name"])
                pair = [a for a, b in OPPOSITES if a in ps and b in rs]
                if pair:
                    out.setdefault("%s %s" % (st, pair[0]), []).extend([p, r])
                    left.remove(p)
                    left.remove(r)
                    break
        if left:
            out.setdefault(st, []).extend(left)
    return out


def name_words(name, side=None):
    """The words of a name without its state words; a word that ends in a state (Poff, Pon) keeps only its stem."""
    out = set()
    for t in tokens(name):
        low = t.lower()
        if low in STATE or low == "trap":
            continue
        for a, b in OPPOSITES:
            w = a if side == "problem" else b if side == "clear" else None
            if w and len(low) > len(w) and low.endswith(w):
                low = low[:-len(w)] + "~"
                break
        out.add(low)
    return out


def similarity(p, r):
    pw, rw = name_words(p["trap"]["name"], "problem"), name_words(r["trap"]["name"], "clear")
    return len(pw & rw) / len(pw | rw) if pw and rw else 0


def match_similar(problems, clears):
    """Pairs of a problem and a clear whose names are most alike, each one in one pair at most, with no tie."""
    out = {}
    for r in clears:
        scored = sorted(((similarity(p, r), p) for p in problems), key=lambda x: -x[0])
        if not scored or scored[0][0] < 0.6 or (len(scored) > 1 and scored[1][0] == scored[0][0]):
            continue
        p = scored[0][1]
        others = sorted((similarity(p, r2) for r2 in clears if r2 is not r), reverse=True)
        if others and others[0] >= scored[0][0]:
            continue
        out[p["trap"]["name"]] = r["trap"]["name"]
    return out


def event_like(name):
    return bool(set(t.lower() for t in tokens(name)) & EVENT_WORDS)


def clear_value(trap):
    """A variable value that says the trap is a clear: (variable, value, why), or None."""
    for vb in trap["varbinds"]:
        for num, label in sorted(vb.get("enums", {}).items()):
            if re.match(r"^(clear|cleared|normal|ok|recovery|recovered|up|good)$", label, re.I):
                return (vb["name"], str(num), "= %s(%s)" % (label, num))
        m = re.search(r"\b(recovery|cleared|clear)\s*\(\s*(\d+)\s*\)", vb.get("description", ""), re.I)
        if m:
            return (vb["name"], m.group(2), "%s(%s) in its description" % (m.group(1), m.group(2)))
    return None


# ---------------------------------------------------------------- files
SECTIONS = [("table", "Tables of the trap list"), ("row", "Rows whose name or OID does not match the MIBs"),
            ("missing", "Traps no MIB defines"), ("remark", "Remarks in the trap list"),
            ("groups", "Problem and clear groups"),
            ("severity", "Severity words"), ("severity-of", "Traps without a severity"),
            ("conflict", "Traps listed with different severities"), ("aggregated", "Alarm IDs"),
            ("unpaired", "Problems without a clear"), ("unpaired-clear", "Clears without a problem")]


def write_notes(cat, path):
    m = cat.mibs
    out = ["# Trap catalogue: notes", "",
           "Trap list: `%s`. MIBs: %s (%d files, %d modules, %d traps)." % (
               cat.trap_list, ", ".join("`%s`" % p for p in cat.mib_paths), len(m.files), len(m.modules), len(m.traps)), "",
           "Every block ends with `decision:`. Write `as proposed` to take the proposal, or one of its choices. "
           "A block that lists several traps takes one decision for all; for a trap that differs, add under "
           "`overrides:` a line `- <trap name>: <decision>`. Then run the same command again: it rewrites this "
           "file around your decisions, so write only on the `decision:` and `overrides:` lines.", ""]
    out += section_text(cat.items, cat.notes)
    if m.problems:
        out += ["## What the MIBs could not give", ""] + ["- %s" % p for p in m.problems] + [""]
    for kind, title in SECTIONS:
        its = [it for it in cat.items if it["kind"] == kind]
        if not its:
            continue
        out += ["## " + title, ""]
        for it in its:
            out.append("### %s %s" % (kind, it["key"]))
            out += [("- " + f if not f.startswith("  ") else "  - " + f.strip()).replace("\n", " / ") for f in it["facts"]]
            out.append("choices: " + it["choices"])
            prop = it["proposal"] or "(none: decide)"
            if it.get("suggested"):
                prop += ", except:"
            out.append("proposal: " + prop)
            for k, v in sorted(it.get("suggested", {}).items()):
                out.append("  - %s: %s" % (k, v))
            if it["error"] and it["raw"]:
                out.append("<!-- not accepted: %s -->" % it["error"])
            out.append("decision: " + it["raw"])
            if it["overrides"] or it.get("suggested") or kind in ("missing", "unpaired", "unpaired-clear", "remark", "groups"):
                out.append("overrides:")
                for k, v in it["overrides"].items():
                    out.append("- %s: %s" % (k, v))
            out.append("")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out).rstrip() + "\n")


def esc(x):
    return str(x if x is not None else "").replace("|", "\\|").replace("\n", " ")


def write_report(cat, path, data, open_items, problems):
    ents = data["entries"]
    by_src = {}
    for e in ents:
        by_src[e["source"]] = by_src.get(e["source"], 0) + 1
    groups = {}
    for e in ents:
        if e["group"] and e["type"] in ("problem", "resolution"):
            groups.setdefault(e["group"], set()).add(e["type"])
    paired = sum(1 for g in groups.values() if g == {"problem", "resolution"})
    unp = [e["name"] for e in ents if e["type"] == "problem" and groups.get(e["group"]) != {"problem", "resolution"} and not e["clear_when"] and not e["aggregated"]]
    agg = data["aggregated"]
    out = ["# Trap catalogue", "",
           "Trap list: `%s`. MIBs: %s." % (cat.trap_list, ", ".join("`%s`" % p for p in cat.mib_paths)), "",
           "%d traps in the catalogue: %d defined in the MIBs, %d standard traps whose MIB was not given, %d from the trap list only (no MIB). "
           "%s%d problem/clear groups; %d problems clear by a variable's value; %d problems have no clear." % (
               len(ents), by_src.get("NOTIFICATION-TYPE", 0) + by_src.get("TRAP-TYPE", 0), by_src.get("BUILTIN", 0),
               by_src.get("SHEET", 0),
               ("%d alarm IDs arrive inside %s%s. " % (len(data["alarms"]), agg["trap"], (" and clear with " + agg["cleared_by"]) if agg.get("cleared_by") else "")) if agg else "",
               paired, sum(1 for e in ents if e["clear_when"]), len(unp)), ""]
    out += ["## Traps", "",
            "| # | Trap | Module | OID | Arrives as (enterprise, generic, specific) | Severity | Type | Group | Clears when | Flags | Trap list rows |",
            "|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, e in enumerate(ents, 1):
        out.append("| %d | %s | %s | %s | .%s, %s, %s | %s (%s) | %s | %s | %s | %s | %s |" % (
            i, esc(e["name"]), esc(e["module"] or "-"), e["oid"], e["enterprise"], e["generic"], e["specific"],
            esc(e["severity"]), esc(e["severity_word"] or "-"), esc(e["type"]), esc(e["group"]),
            esc("%s = %s" % tuple(e["clear_when"]) if e["clear_when"] else ("by " + agg["cleared_by"] if e["aggregated"] and agg and e["name"] == agg["trap"] else "-")),
            esc(", ".join(e["flags"]) or "-"), esc("; ".join("%s row %s" % (r["table"], r["row"]) for r in e["rows"]) or "-")))
    if data["alarms"]:
        out += ["", "## Alarm IDs", "",
                "Carried by %s in the alarm ID of its variables' instance (%s)." % (agg["trap"], agg["alarm_index"]) if agg else "Not carried by any trap (aggregated: skip).", "",
                "| ID | Name | Severity | Type | Component | Direct trap | Flags |", "|---|---|---|---|---|---|---|"]
        for a in data["alarms"]:
            out.append("| %d | %s | %s (%s) | %s | %s | %s | %s |" % (a["id"], esc(a["label"] or a["name"]), esc(a["severity"]), esc(a["severity_word"]),
                                                               esc(a["type"]), esc(a["component"]), esc(a["trap"] or "-"), esc(", ".join(a["flags"]) or "-")))
    out += ["", "## Decisions", "", "| Block | Decision | Overrides |", "|---|---|---|"]
    for it in cat.items:
        dec = it["decision"] if not it["error"] else "**open: %s**" % it["error"]
        ov = dict(it.get("suggested", {})) if it["raw"].lower() in ACCEPT else {}
        ov.update(it["overrides"])
        out.append("| %s %s | %s | %s |" % (it["kind"], esc(it["key"]), esc(dec), esc("; ".join("%s: %s" % kv for kv in ov.items()) or "-")))
    diffs = [it for it in cat.items if it["kind"] in ("row", "missing", "remark", "conflict")]
    out += ["", "## Where the trap list and the MIBs differ", ""]
    out += ["- %s %s: %s" % (it["kind"], it["key"], " ".join(f.strip() for f in it["facts"][:2])[:300]) for it in diffs] or ["- none"]
    if cat.facts:
        out += ["", "## Facts", ""] + ["- " + f for f in cat.facts]
    out += ["", "## Questions for the owner", ""]
    qs = report_questions(data)
    out += ["%d. %s" % (i, q) for i, q in enumerate(qs, 1)] or ["- none"]
    out += ["", "## Not checked", "",
            "- That the devices send these traps, with these variables, to the probe: only a trap capture shows it.",
            "- The trap list's severities are taken as the owner's choice; only their conflicts are raised. Its texts are checked against the MIB's variables in the generate task.", ""]
    gate = gate_line(open_items, problems)
    out += [gate, ""]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out))
    return gate


def report_questions(data):
    ents = data["entries"]
    groups = {}
    for e in ents:
        if e["group"] and e["type"] in ("problem", "resolution"):
            groups.setdefault(e["group"], set()).add(e["type"])
    unp = [e["name"] for e in ents if e["type"] == "problem" and groups.get(e["group"]) != {"problem", "resolution"}
           and not e["clear_when"] and not e["aggregated"]]
    qs = list(data["questions"])
    if unp:
        qs.append("%d problems have no clearing trap and stay open until cleared by hand (%s): should they expire instead?" % (
            len(unp), ", ".join(unp[:6]) + (", ..." if len(unp) > 6 else "")))
    return qs


def gate_line(open_items, problems):
    if not open_items and not problems:
        return "Gate: passed. Every block of the notes has a valid decision and every trap has a severity."
    parts = []
    if open_items:
        parts.append("%d block(s) of the notes without a valid decision: %s" % (
            len(open_items), "; ".join("%s %s (%s)" % (it["kind"], it["key"], it["error"]) for it in open_items[:12])))
    if problems:
        parts.append("; ".join(problems[:10]))
    return "Gate: not passed. " + " ".join(parts)


def run(trap_list, mib_paths, out):
    notes = out[:-3] + ".notes.md" if out.endswith(".md") else out + ".notes.md"
    first = not os.path.exists(notes)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    cat = Catalogue(trap_list, mib_paths, notes)
    cat.build()
    write_notes(cat, notes)
    open_items, problems = cat.gate()
    data = cat.data()
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    jpath = out[:-3] + ".json" if out.endswith(".md") else out + ".json"
    data["gate"] = not open_items and not problems
    with open(jpath, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, default=list)
    gate = write_report(cat, out, data, open_items, problems)
    lines = []
    if first:
        lines.append("Wrote %s: %d blocks to decide (facts and a proposal in each). Fill every `decision:` line, then run the same command again." % (notes, len(cat.items)))
    else:
        lines.append("Read %s: %d of %d blocks decided." % (notes, len(cat.items) - len(open_items), len(cat.items)))
    lines.append("Wrote %s and %s: %d traps, %d alarm IDs." % (out, jpath, len(data["entries"]), len(data["alarms"])))
    if data["gate"]:
        lines.append("Questions for the owner (also in %s):" % out)
        lines += ["  %d. %s" % (i, q) for i, q in enumerate(report_questions(data), 1)]
    lines.append(gate)
    return "\n".join(lines), data["gate"]
