"""Read MIB files: objects, notifications (SMIv2) and traps (SMIv1), with their OIDs.

load(paths) returns a Mibs object:
  .modules   module name -> {"file", "imports": {name: module}}
  .defs      list of definitions: {"name", "module", "kind", "oid", ...}
  .traps     the notifications and traps, each with "varbinds", "description",
             "enterprise", "specific", "generic" (the SNMPv1 form, RFC 3584)
  .by_oid / .by_name lookups, and .problems (what could not be read or resolved)
"""
import os
import re

ROOTS = {
    "ccitt": "0", "iso": "1", "joint-iso-ccitt": "2", "zeroDotZero": "0.0",
    "org": "1.3", "dod": "1.3.6", "internet": "1.3.6.1",
    "directory": "1.3.6.1.1", "mgmt": "1.3.6.1.2", "mib-2": "1.3.6.1.2.1",
    "system": "1.3.6.1.2.1.1", "interfaces": "1.3.6.1.2.1.2",
    "transmission": "1.3.6.1.2.1.10", "snmp": "1.3.6.1.2.1.11",
    "experimental": "1.3.6.1.3", "private": "1.3.6.1.4",
    "enterprises": "1.3.6.1.4.1", "security": "1.3.6.1.5", "snmpV2": "1.3.6.1.6",
    "snmpDomains": "1.3.6.1.6.1", "snmpProxys": "1.3.6.1.6.2",
    "snmpModules": "1.3.6.1.6.3",
}

# The standard traps (SNMPv2-MIB, IF-MIB): their SNMPv1 form is a generic trap.
GENERIC = {
    "1.3.6.1.6.3.1.1.5.1": (0, "coldStart"),
    "1.3.6.1.6.3.1.1.5.2": (1, "warmStart"),
    "1.3.6.1.6.3.1.1.5.3": (2, "linkDown"),
    "1.3.6.1.6.3.1.1.5.4": (3, "linkUp"),
    "1.3.6.1.6.3.1.1.5.5": (4, "authenticationFailure"),
    "1.3.6.1.6.3.1.1.5.6": (5, "egpNeighborLoss"),
}
# Their variables, for when the MIB that defines them is not supplied.
GENERIC_VARBINDS = {
    "linkDown": ["ifIndex", "ifAdminStatus", "ifOperStatus"],
    "linkUp": ["ifIndex", "ifAdminStatus", "ifOperStatus"],
    "egpNeighborLoss": ["egpNeighAddr"],
}

MACROS = ("OBJECT IDENTIFIER", "MODULE-IDENTITY", "OBJECT-IDENTITY", "OBJECT-TYPE",
          "NOTIFICATION-TYPE", "TRAP-TYPE", "OBJECT-GROUP", "NOTIFICATION-GROUP",
          "MODULE-COMPLIANCE", "AGENT-CAPABILITIES")
DEF_RE = re.compile(r"(?m)^[ \t]*([a-z][\w-]*)[ \t\r\n]+(%s)\b" % "|".join(
    m.replace(" ", r"\s+") for m in MACROS))
TC_RE = re.compile(r"(?m)^[ \t]*([A-Z][\w-]*)[ \t]*::=[ \t\r\n]*(TEXTUAL-CONVENTION\b|INTEGER\b|BITS\b)")
MODULE_RE = re.compile(r"(?m)^[ \t]*([A-Za-z][\w-]*)\s+(?:DEFINITIONS)\s*(?:[A-Z ]*TAGS\s*)?::=\s*BEGIN\b")
HINT_RE = re.compile(r"--#(TYPE|SUMMARY|SEVERITY|ARGUMENTS)\s+(.*)")


def mask(text):
    """Blank out strings and comments, keeping offsets; return (masked, strings by start)."""
    out, strings, i, n = [], {}, 0, len(text)
    while i < n:
        c = text[i]
        if c == '"':
            j = i + 1
            while j < n:
                if text[j] == '"':
                    if j + 1 < n and text[j + 1] == '"':
                        j += 2
                        continue
                    break
                j += 1
            strings[i] = text[i + 1:j].replace('""', '"')
            out.append('"' + re.sub(r"[^\n]", " ", text[i + 1:j]) + '"')
            i = j + 1
        elif c == "-" and text.startswith("--", i):
            j = i + 2
            while j < n and text[j] != "\n" and not text.startswith("--", j):
                j += 1
            if text.startswith("--", j):
                j += 2
            out.append(re.sub(r"[^\n]", " ", text[i:j]))
            i = j
        else:
            out.append(c)
            i += 1
    return "".join(out), strings


def braces(masked, start):
    """Text between the brace at or after start and its partner, and the end offset."""
    i = masked.index("{", start)
    depth = 0
    for j in range(i, len(masked)):
        if masked[j] == "{":
            depth += 1
        elif masked[j] == "}":
            depth -= 1
            if depth == 0:
                return masked[i + 1:j], j + 1
    return masked[i + 1:], len(masked)


def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


def enums(body):
    """{ up(1), down(2) } -> {1: "up", 2: "down"}"""
    return {int(v): k for k, v in re.findall(r"([a-zA-Z][\w-]*)\s*\(\s*(-?\d+)\s*\)", body)}


def string_after(masked, strings, key, start, end):
    m = re.compile(r"\b%s\s+\"" % key).search(masked, start, end)
    if not m:
        return ""
    return strings.get(m.end() - 1, "")


def parse_text(text, path):
    """Definitions of every module in one file."""
    masked, strings = mask(text)
    hints = [(m.start(), m.group(1), m.group(2).strip()) for m in HINT_RE.finditer(text)]
    modules, defs, problems = [], [], []
    starts = [(m.start(), m.group(1)) for m in MODULE_RE.finditer(masked)]
    if not starts:
        problems.append("%s: no module (DEFINITIONS ::= BEGIN) found" % path)
        return modules, defs, problems
    for k, (pos, module) in enumerate(starts):
        end = starts[k + 1][0] if k + 1 < len(starts) else len(masked)
        m_end = re.compile(r"(?m)^\s*END\s*$").search(masked, pos, end)
        end = m_end.end() if m_end else end
        imports = {}
        m_imp = re.compile(r"\bIMPORTS\b").search(masked, pos, end)
        body_from = pos
        if m_imp:
            semi = masked.index(";", m_imp.end()) if ";" in masked[m_imp.end():end] else m_imp.end()
            names = []
            for tok in re.findall(r"[\w-]+|FROM", masked[m_imp.end():semi]):
                if tok == "FROM":
                    continue
                names.append(tok)
            for grp in re.finditer(r"((?:[\w-]+\s*,?\s*)+?)\s*FROM\s+([\w-]+)", masked[m_imp.end():semi]):
                for nm in re.findall(r"[\w-]+", grp.group(1)):
                    imports[nm] = grp.group(2)
            body_from = semi + 1
        modules.append({"name": module, "file": path, "imports": imports})
        region = masked[body_from:end]
        base = body_from
        for m in TC_RE.finditer(region):
            name = m.group(1)
            s = base + m.end()
            m_syn = re.compile(r"\bSYNTAX\s+").search(masked, s, end) if m.group(2).startswith("TEXTUAL") else None
            at = m_syn.end() if m_syn else base + m.start(2)
            m_type = re.compile(r"(INTEGER|BITS|Integer32|Unsigned32|OCTET\s+STRING|[A-Z][\w-]*)\s*(\{)?").match(masked, at)
            vals = {}
            if m_type and m_type.group(2):
                b, _ = braces(masked, m_type.start(2))
                vals = enums(b)
            defs.append({"name": name, "module": module, "kind": "TYPE",
                         "syntax": clean(m_type.group(1)) if m_type else "", "enums": vals})
        matches = list(DEF_RE.finditer(region))
        for i, m in enumerate(matches):
            name, kind = m.group(1), re.sub(r"\s+", " ", m.group(2))
            s = base + m.end()
            nxt = base + matches[i + 1].start() if i + 1 < len(matches) else end
            m_val = re.compile(r"::=\s*(\{|\d+)").search(masked, s, nxt)
            if not m_val:
                if kind != "OBJECT IDENTIFIER":
                    problems.append("%s: %s %s has no ::= value" % (path, name, kind))
                continue
            stop = m_val.start()
            if m_val.group(1) == "{":
                value, _ = braces(masked, m_val.start(1))
            else:
                value = m_val.group(1)
            d = {"name": name, "module": module, "kind": kind, "value": clean(value), "file": path,
                 "line": text.count("\n", 0, base + m.start()) + 1}
            d["description"] = clean(string_after(masked, strings, "DESCRIPTION", s, stop))
            if kind == "OBJECT-TYPE":
                m_syn = re.compile(r"\bSYNTAX\s+").search(masked, s, stop)
                if m_syn:
                    m_type = re.compile(r"(SEQUENCE\s+OF\s+[\w-]+|OCTET\s+STRING|OBJECT\s+IDENTIFIER|[\w-]+)\s*(\{|\()?").match(masked, m_syn.end())
                    d["syntax"] = clean(m_type.group(1)) if m_type else ""
                    if m_type and m_type.group(2) == "{":
                        b, _ = braces(masked, m_type.start(2))
                        d["enums"] = enums(b)
                m_idx = re.compile(r"\bINDEX\s*\{").search(masked, s, stop)
                if m_idx:
                    b, _ = braces(masked, m_idx.end() - 1)
                    d["index"] = [x for x in re.findall(r"[\w-]+", b) if x != "IMPLIED"]
                m_acc = re.compile(r"\b(?:MAX-)?ACCESS\s+([\w-]+)").search(masked, s, stop)
                d["access"] = m_acc.group(1) if m_acc else ""
            if kind in ("NOTIFICATION-TYPE", "TRAP-TYPE"):
                key = "OBJECTS" if kind == "NOTIFICATION-TYPE" else "VARIABLES"
                m_obj = re.compile(r"\b%s\s*\{" % key).search(masked, s, stop)
                d["varbinds"] = re.findall(r"[\w-]+", braces(masked, m_obj.end() - 1)[0]) if m_obj else []
                m_st = re.compile(r"\bSTATUS\s+([\w-]+)").search(masked, s, stop)
                d["status"] = m_st.group(1) if m_st else ""
                if kind == "TRAP-TYPE":
                    m_ent = re.compile(r"\bENTERPRISE\s+([\w-]+)").search(masked, s, stop)
                    d["enterprise_name"] = m_ent.group(1) if m_ent else ""
                d["hints"] = {h: v.strip('"') for p, h, v in hints if base + m.start() <= p < (nxt if nxt > stop else stop + 400)}
            defs.append(d)
    return modules, defs, problems


class Mibs:
    def __init__(self):
        self.modules, self.defs, self.problems, self.files = {}, [], [], []
        self.traps, self.by_oid, self.by_name, self.objects = [], {}, {}, {}

    def find(self, name, module=None):
        """The definition of name as seen from module: its own, then imported, then any."""
        cands = self._names.get(name, [])
        if not cands:
            return None
        if module:
            for d in cands:
                if d["module"] == module:
                    return d
            src = self.modules.get(module, {}).get("imports", {}).get(name)
            for d in cands:
                if d["module"] == src:
                    return d
        return cands[0]

    def oid_of(self, name, module=None, seen=None):
        d = self.find(name, module)
        if d is None:
            if name in ROOTS:
                return ROOTS[name]
            return None
        if "oid" in d:
            return d["oid"]
        seen = seen or set()
        if id(d) in seen:
            return None
        seen.add(id(d))
        if d["kind"] == "TRAP-TYPE":
            ent = self.oid_of(d.get("enterprise_name", ""), d["module"], seen)
            d["oid"] = (ent + ".0." + d["value"]) if ent and d["value"].isdigit() else None
            return d["oid"]
        parts = d["value"].replace(",", " ").split()
        out = []
        for k, tok in enumerate(parts):
            m = re.match(r"^([a-zA-Z][\w-]*)?\(?(\d+)?\)?$", tok)
            if tok.isdigit():
                out.append(tok)
            elif m and m.group(2):
                out.append(m.group(2))
            elif k == 0:
                parent = self.oid_of(tok, d["module"], seen)
                if parent is None:
                    d["oid"] = None
                    return None
                out.append(parent)
            else:
                d["oid"] = None
                return None
        d["oid"] = ".".join(out) if out else None
        return d["oid"]


def v1_form(oid):
    """(enterprise, generic, specific) of a notification OID, as RFC 3584 maps it."""
    if oid in GENERIC:
        return "1.3.6.1.6.3.1.1.5", GENERIC[oid][0], 0
    parts = oid.split(".")
    if len(parts) >= 3 and parts[-2] == "0":
        return ".".join(parts[:-2]), 6, int(parts[-1])
    return ".".join(parts[:-1]), 6, int(parts[-1])


def mib_files(paths):
    out = []
    for p in paths:
        if os.path.isdir(p):
            for root, dirs, files in os.walk(p):
                dirs.sort()
                for f in sorted(files):
                    full = os.path.join(root, f)
                    if f.lower().endswith((".mib", ".my", ".txt", ".smi", ".mi2")) or "." not in f or f.lower().endswith("_l"):
                        out.append(full)
        else:
            out.append(p)
    return out


def load(paths):
    mibs = Mibs()
    for path in mib_files(paths):
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError as e:
            mibs.problems.append("%s: %s" % (path, e))
            continue
        if "DEFINITIONS" not in text:
            continue
        mibs.files.append(path)
        modules, defs, problems = parse_text(text, path)
        for m in modules:
            if m["name"] in mibs.modules:
                mibs.problems.append("module %s is defined twice: %s and %s (the first is used)"
                                     % (m["name"], mibs.modules[m["name"]]["file"], path))
                defs = [d for d in defs if d["module"] != m["name"]]
                continue
            mibs.modules[m["name"]] = m
        mibs.defs.extend(defs)
        mibs.problems.extend(problems)
    mibs._names = {}
    for d in mibs.defs:
        mibs._names.setdefault(d["name"], []).append(d)
    for d in mibs.defs:
        if d["kind"] == "TYPE":
            continue
        oid = mibs.oid_of(d["name"], d["module"])
        if oid is None:
            if d["kind"] in ("NOTIFICATION-TYPE", "TRAP-TYPE", "OBJECT-TYPE"):
                mibs.problems.append("%s::%s: OID not resolved (%s)" % (d["module"], d["name"], d["value"]))
            continue
        mibs.by_oid.setdefault(oid, d)
        mibs.by_name.setdefault(d["name"], []).append(d)
        if d["kind"] == "OBJECT-TYPE":
            mibs.objects[d["name"]] = d
    types = {d["name"]: d for d in mibs.defs if d["kind"] == "TYPE"}
    for d in mibs.defs:
        if d["kind"] not in ("NOTIFICATION-TYPE", "TRAP-TYPE") or not d.get("oid"):
            continue
        ent, gen, spec = v1_form(d["oid"])
        if d["kind"] == "TRAP-TYPE":
            ent = d["oid"][:-len(".0." + d["value"])]
            gen, spec = 6, int(d["value"])
        vbs = []
        for n, vname in enumerate(d.get("varbinds", []), 1):
            o = mibs.find(vname, d["module"])
            vb = {"n": n, "name": vname, "oid": (o or {}).get("oid"), "syntax": (o or {}).get("syntax", ""),
                  "enums": dict((o or {}).get("enums", {})), "description": (o or {}).get("description", "")}
            if not vb["enums"] and vb["syntax"] in types:
                vb["enums"] = dict(types[vb["syntax"]].get("enums", {}))
            if o is None:
                mibs.problems.append("%s::%s: variable %s is not defined in the MIBs read" % (d["module"], d["name"], vname))
            else:
                vb["table_index"] = table_index(mibs, o)
            vbs.append(vb)
        trap = {"name": d["name"], "module": d["module"], "kind": d["kind"], "oid": d["oid"],
                "enterprise": ent, "generic": gen, "specific": spec, "varbinds": vbs,
                "description": d.get("description", ""), "status": d.get("status", ""),
                "hints": d.get("hints", {}), "file": d.get("file"), "line": d.get("line")}
        mibs.traps.append(trap)
    mibs.trap_by_oid = {}
    mibs.trap_by_name = {}
    for t in mibs.traps:
        mibs.trap_by_oid.setdefault(t["oid"], t)
        mibs.trap_by_name.setdefault(t["name"].lower(), []).append(t)
    return mibs


def table_index(mibs, obj):
    """The INDEX of the table row an object belongs to (empty for a scalar)."""
    oid = obj.get("oid") or ""
    parent = oid.rsplit(".", 1)[0] if "." in oid else ""
    row = mibs.by_oid.get(parent)
    if row and row.get("kind") == "OBJECT-TYPE" and row.get("index"):
        return list(row["index"])
    return []


def builtin_trap(oid):
    """A standard trap the MIBs did not define (coldStart, linkDown, ...)."""
    if oid not in GENERIC:
        return None
    gen, name = GENERIC[oid]
    return {"name": name, "module": "SNMPv2-MIB" if gen in (0, 1, 4) else "IF-MIB", "kind": "BUILTIN",
            "oid": oid, "enterprise": "1.3.6.1.6.3.1.1.5", "generic": gen, "specific": 0,
            "varbinds": [{"n": i, "name": v, "oid": None, "syntax": "", "enums": {}, "description": "", "table_index": []}
                         for i, v in enumerate(GENERIC_VARBINDS.get(name, []), 1)],
            "description": "", "status": "current", "hints": {}, "file": None, "line": None}
