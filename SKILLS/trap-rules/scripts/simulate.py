"""Send test traps through a rules folder, without a probe.

A small interpreter for the part of the probe rules language the generator writes: include, table
(inline or from a lookup file) with default, assignments to @fields and $variables, [$a, $b] =
lookup(), if/else, switch/case/default, log, and the functions match, nmatch, regmatch, extract,
lookup, lower, upper, length. Strings concatenate with +.

run_catalogue(root, catalogue) sends one trap per catalogue trap (and one per alarm ID through the
trap that carries them) with test values, and for each problem/clear pair a problem then its clear,
and returns (findings, summary).
"""
import json
import os
import re

TOKEN = re.compile(r'''\s*(?:(\#[^\n]*)|("(?:\\.|[^"\\])*")|(\[|\]|\{|\}|\(|\)|,|\+|==|=|:)|(@[A-Za-z_]\w*)|(\$\*|\$[A-Za-z_][\w-]*|\$\d+)|([A-Za-z_][\w.-]*)|(-?\d+))''')


class RulesError(Exception):
    pass


def unquote(s):
    body = s[1:-1]
    return re.sub(r'\\(["\\])', r"\1", body)


def tokenize(text):
    toks, pos = [], 0
    while pos < len(text):
        if text[pos].isspace():
            pos += 1
            continue
        m = TOKEN.match(text, pos)
        if not m or m.end() == pos:
            raise RulesError("cannot read %r" % text[pos:pos + 30])
        pos = m.end()
        if m.group(1):
            continue
        if m.group(2):
            toks.append(("str", unquote(m.group(2))))
        elif m.group(3):
            toks.append(("op", m.group(3)))
        elif m.group(4):
            toks.append(("field", m.group(4)[1:]))
        elif m.group(5):
            toks.append(("var", m.group(5)[1:]))
        elif m.group(6):
            toks.append(("name", m.group(6)))
        else:
            toks.append(("num", m.group(7)))
    return toks


class Parser:
    def __init__(self, toks):
        self.t, self.i = toks, 0

    def peek(self, k=0):
        return self.t[self.i + k] if self.i + k < len(self.t) else (None, None)

    def take(self, kind=None, val=None):
        tok = self.peek()
        if tok[0] is None or (kind and tok[0] != kind) or (val is not None and tok[1] != val):
            raise RulesError("expected %s %s, found %s" % (kind, val or "", tok))
        self.i += 1
        return tok

    def block(self, stop=("}",)):
        out = []
        while True:
            k, v = self.peek()
            if k is None or (k == "op" and v in stop) or (k == "name" and v in ("case", "default")):
                return out
            out.append(self.statement())

    def statement(self):
        k, v = self.peek()
        if k == "name" and v == "if":
            self.take()
            self.take("op", "(")
            cond = self.expr()
            self.take("op", ")")
            self.take("op", "{")
            then = self.block()
            self.take("op", "}")
            other = []
            if self.peek() == ("name", "else"):
                self.take()
                if self.peek() == ("name", "if"):
                    other = [self.statement()]
                else:
                    self.take("op", "{")
                    other = self.block()
                    self.take("op", "}")
            return ("if", cond, then, other)
        if k == "name" and v == "switch":
            self.take()
            self.take("op", "(")
            sel = self.expr()
            self.take("op", ")")
            self.take("op", "{")
            cases, default = [], None
            while True:
                k2, v2 = self.peek()
                if k2 == "op" and v2 == "}":
                    self.take()
                    break
                if k2 == "name" and v2 == "case":
                    self.take()
                    labels = [self.take("str")[1]]
                    while self.peek() == ("op", "|"):
                        self.take()
                        labels.append(self.take("str")[1])
                    self.take("op", ":")
                    cases.append((labels, self.block()))
                elif k2 == "name" and v2 == "default":
                    self.take()
                    self.take("op", ":")
                    default = self.block()
                else:
                    raise RulesError("expected case, default or } in a switch, found %s %s" % (k2, v2))
            return ("switch", sel, cases, default)
        if k == "name" and v == "table":
            self.take()
            name = self.take("name")[1]
            self.take("op", "=")
            if self.peek()[0] == "str":
                src = ("file", self.take()[1])
            else:
                src = ("rows", self.literal_rows())
            default = None
            if self.peek() == ("name", "default"):
                self.take()
                self.take("op", "=")
                default = self.literal_rows() if self.peek() == ("op", "{") else self.take("str")[1]
            return ("table", name, src, default)
        if k == "op" and v == "[":
            self.take()
            targets = [self.target()]
            while self.peek() == ("op", ","):
                self.take()
                targets.append(self.target())
            self.take("op", "]")
            self.take("op", "=")
            return ("multi", targets, self.expr())
        if k in ("field", "var"):
            tgt = self.target()
            self.take("op", "=")
            return ("set", tgt, self.expr())
        if k == "name":
            return ("call", self.expr())
        raise RulesError("unexpected %s %s" % (k, v))

    def literal_rows(self):
        self.take("op", "{")
        rows = []
        while self.peek() != ("op", "}"):
            if self.peek() == ("op", "{"):
                self.take()
                row = [self.take("str")[1]]
                while self.peek() == ("op", ","):
                    self.take()
                    row.append(self.take("str")[1])
                self.take("op", "}")
                rows.append(row)
            elif self.peek()[0] == "str":
                rows.append([self.take()[1]])
            if self.peek() == ("op", ","):
                self.take()
        self.take("op", "}")
        return rows

    def target(self):
        k, v = self.take()
        if k not in ("field", "var"):
            raise RulesError("cannot assign to %s" % v)
        return (k, v)

    def expr(self):
        left = self.atom()
        while self.peek() == ("op", "+"):
            self.take()
            left = ("+", left, self.atom())
        return left

    def atom(self):
        k, v = self.take()
        if k in ("str", "num"):
            return ("lit", v)
        if k in ("var", "field"):
            return (k, v)
        if k == "name" and self.peek() == ("op", "("):
            self.take()
            args = []
            if self.peek() != ("op", ")"):
                args.append(self.cond_or_expr())
                while self.peek() == ("op", ","):
                    self.take()
                    args.append(self.cond_or_expr())
            self.take("op", ")")
            return ("fn", v.lower(), args)
        if k == "name" and v.upper() in ("DEBUG", "INFO", "WARNING", "WARN", "ERROR", "FATAL"):
            return ("lit", v)
        if k == "name":
            return ("tname", v)
        raise RulesError("unexpected %s in an expression" % v)

    def cond_or_expr(self):
        return self.expr()


def expand(path, root, seen=None):
    """The text of a rules file with its includes inlined; paths under $NC_RULES_HOME map to root."""
    seen = seen or []
    if path in seen:
        raise RulesError("include loop: %s" % " -> ".join(seen + [path]))
    text = open(path, encoding="utf-8").read()

    def inc(m):
        target = resolve(m.group(1), root)
        if not target:
            raise RulesError("include not found: %s" % m.group(1))
        return expand(target, root, seen + [path])
    return re.sub(r'(?m)^\s*include\s+"([^"]+)"', inc, text)


def resolve(path, root):
    p = path.replace("$NC_RULES_HOME/", "")
    parts = p.split("/")
    for i in range(len(parts)):
        cand = os.path.join(root, *parts[i:])
        if os.path.exists(cand):
            return cand
    return None


class Rules:
    def __init__(self, root, master, include_rules):
        self.root = root
        text = expand(include_rules, root) + "\n" + expand(master, root)
        prog = Parser(tokenize(text)).block(stop=())
        self.tables, self.body = {}, []
        for st in prog:
            if st[0] == "table":
                _, name, src, default = st
                rows = {}
                if src[0] == "file":
                    f = resolve(src[1], root)
                    if not f:
                        raise RulesError("lookup file not found: %s" % src[1])
                    for line in open(f, encoding="utf-8"):
                        line = line.rstrip("\n")
                        if line.strip():
                            cols = line.split("\t")
                            rows[cols[0]] = cols[1:]
                else:
                    for r in src[1]:
                        rows[r[0]] = r[1:]
                if isinstance(default, list):
                    default = default[0] if len(default) == 1 else [d[0] if isinstance(d, list) else d for d in default]
                self.tables[name] = (rows, default)
            else:
                self.body.append(st)

    def run(self, element):
        env = {"var": dict(element), "field": {"Manager": "", "Node": "", "AlertKey": "", "Summary": ""}}
        try:
            self.exec_block(self.body, env)
        except _Stop:
            pass
        return env

    def exec_block(self, stmts, env):
        for st in stmts:
            self.exec(st, env)

    def exec(self, st, env):
        kind = st[0]
        if kind == "set":
            env[st[1][0]][st[1][1]] = self.value(st[2], env)
        elif kind == "multi":
            vals = self.value(st[2], env)
            if not isinstance(vals, list):
                vals = [vals]
            for (k, n), v in zip(st[1], vals):
                env[k][n] = v
        elif kind == "if":
            self.exec_block(st[2] if self.truth(st[1], env) else st[3], env)
        elif kind == "switch":
            sel = str(self.value(st[1], env))
            for labels, body in st[2]:
                if sel in labels:
                    self.exec_block(body, env)
                    return
            if st[3]:
                self.exec_block(st[3], env)
        elif kind == "call":
            self.value(st[1], env)
        elif kind == "table":
            raise RulesError("a table declared after the first statement: %s" % st[1])

    def truth(self, e, env):
        v = self.value(e, env)
        return v not in (False, None, "", "0")

    def value(self, e, env):
        k = e[0]
        if k == "lit":
            return e[1]
        if k == "tname":
            raise RulesError("%s is not a value" % e[1])
        if k == "var":
            return str(env["var"].get(e[1], ""))
        if k == "field":
            return str(env["field"].get(e[1], ""))
        if k == "+":
            return str(self.value(e[1], env)) + str(self.value(e[2], env))
        if k == "fn":
            name, args = e[1], e[2]
            if name == "lookup":
                key = str(self.value(args[0], env))
                if args[1][0] != "tname":
                    raise RulesError("the table of a lookup must be a name")
                tname = args[1][1]
                if tname not in self.tables:
                    raise RulesError("lookup in undeclared table %s" % tname)
                rows, default = self.tables[tname]
                if key in rows:
                    r = rows[key]
                    return r if len(r) > 1 else (r[0] if r else "")
                return default
            vals = [self.value(a, env) for a in args]
            if name == "match":
                return str(vals[0]) == str(vals[1])
            if name == "nmatch":
                return str(vals[0]).startswith(str(vals[1]))
            if name == "regmatch":
                return re.search(vals[1], str(vals[0])) is not None
            if name == "extract":
                m = re.search(vals[1], str(vals[0]))
                return m.group(1) if m and m.groups() else ""
            if name == "hostname":
                return "testhost"
            if name == "lower":
                return str(vals[0]).lower()
            if name == "upper":
                return str(vals[0]).upper()
            if name == "length":
                return str(len(str(vals[0])))
            if name in ("log", "details", "update", "setlog"):
                return ""
            if name == "discard":
                raise _Stop()
            raise RulesError("function %s is not known to the simulator" % name)
        raise RulesError("cannot evaluate %s" % k)

    # field lookups use the field names as written, e.g. "Field" -> env["field"]["Field"]


class _Stop(Exception):
    pass


# ---------------------------------------------------------------- test traps from the catalogue
def test_value(vb, n, clear=None, avoid=None):
    if clear and clear[0] == vb["name"]:
        return clear[1]
    enums = vb.get("enums") or {}
    if enums:
        keys = sorted(enums, key=lambda x: int(x))
        bad = [k for k in keys if not re.match(r"^(clear|cleared|normal|ok|recovery|up|good|idle)$", enums[k], re.I)
               and not (avoid and avoid[0] == vb["name"] and str(k) == str(avoid[1]))]
        return str((bad or keys)[0])
    if avoid and avoid[0] == vb["name"]:
        return "7" if str(avoid[1]) != "7" else "9"
    if "IpAddress" in (vb.get("syntax") or ""):
        return "10.0.0.%d" % n
    return "v%d" % n


def trap_element(e, clear=None, instance="7.3"):
    el = {"Node": "testnode", "IPaddress": "10.9.9.9", "ReceivedTime": "1700000000",
          "enterprise": "." + e["enterprise"], "generic-trap": str(e["generic"]), "specific-trap": str(e["specific"])}
    for v in e["varbinds"]:
        el[str(v["n"])] = test_value(v, v["n"], clear, avoid=None if clear else e.get("clear_when"))
        if v.get("oid"):
            idx = v.get("table_index") or []
            inst = ".".join(instance.split(".")[:1] * len(idx)) if idx else "0"
            if idx:
                inst = ".".join(str(5 + i) for i in range(len(idx)))
            el["OID%d" % v["n"]] = "." + v["oid"] + "." + inst
    return el


def run_catalogue(root, catalogue_md):
    jpath = catalogue_md[:-3] + ".json" if catalogue_md.endswith(".md") else catalogue_md + ".json"
    cat = json.load(open(jpath, encoding="utf-8"))
    masters = [f for f in os.listdir(root) if f.endswith(".master.rules")]
    if not masters:
        return [{"where": root, "what": "no <name>.master.rules to simulate"}], "not simulated"
    name = masters[0][:-len(".master.rules")]
    inc = os.path.join(root, "config", "%s.master.include.rules" % name)
    F = []
    try:
        rules = Rules(root, os.path.join(root, masters[0]), inc)
    except (RulesError, OSError) as ex:
        return [{"where": masters[0], "what": "the simulator cannot read the rules: %s" % ex}], "not simulated"
    tnum = {"problem": "1", "resolution": "2", "information": "13"}
    events = {}
    sent = 0
    for e in cat["entries"]:
        if e.get("aggregated"):
            continue
        try:
            ev = rules.run(trap_element(e))
        except RulesError as ex:
            F.append({"where": e["name"], "what": "the simulator stopped: %s" % ex})
            continue
        sent += 1
        f, v = ev["field"], ev["var"]
        events[e["name"]] = f
        exp_id = "SNMPTRAP-%s-%s" % (e["module"] or "SHEET", re.sub(r"[^A-Za-z0-9_]", "_", e["name"]))
        if v.get("OS_EventId") != exp_id:
            F.append({"where": e["name"], "what": "a test trap gave event id %s, expected %s" % (v.get("OS_EventId"), exp_id)})
            continue
        sent_vals = ", ".join("$%d=%s" % (x["n"], ev["var"].get(str(x["n"]), "")) for x in e["varbinds"][:6]) or "no variables"
        if e.get("severity") is not None and str(f.get("Severity")) != str(e["severity"]):
            F.append({"where": e["name"], "what": "a test trap (%s) gave severity %s, the catalogue says %s" % (sent_vals, f.get("Severity"), e["severity"])})
        if e.get("type") and str(f.get("Type")) != tnum[e["type"]]:
            F.append({"where": e["name"], "what": "a test trap (%s) gave type %s, the catalogue says %s" % (sent_vals, f.get("Type"), e["type"])})
        for fld in ("AlertGroup", "Summary", "Identifier", "Agent"):
            if not f.get(fld) or f.get(fld) in ("Unknown",):
                F.append({"where": e["name"], "what": "a test trap gave an empty or unknown @%s" % fld})
        if "unknown" in (f.get("Summary") or "").split():
            F.append({"where": e["name"], "what": "a test trap's summary shows an unknown value: %s" % f.get("Summary")})
        if e.get("clear_when"):
            ev2 = rules.run(trap_element(e, clear=e["clear_when"]))
            g = ev2["field"]
            if str(g.get("Type")) != "2":
                F.append({"where": e["name"], "what": "with %s = %s the event is type %s, not a clear" % (e["clear_when"][0], e["clear_when"][1], g.get("Type"))})
            for fld in ("Node", "AlertKey", "AlertGroup", "Agent"):
                if g.get(fld) != f.get(fld):
                    F.append({"where": e["name"], "what": "its clear by value has another @%s (%s, %s)" % (fld, f.get(fld), g.get(fld))})
    pairs = 0
    groups = {}
    for e in cat["entries"]:
        if not e.get("aggregated") and e["type"] in ("problem", "resolution"):
            groups.setdefault(e["group"], []).append(e)
    for gname, es in groups.items():
        probs = [x for x in es if x["type"] == "problem" and x["name"] in events]
        res = [x for x in es if x["type"] == "resolution" and x["name"] in events]
        for p in probs:
            for r in res:
                pairs += 1
                a, b = events[p["name"]], events[r["name"]]
                for fld in ("Node", "AlertKey", "AlertGroup", "Agent"):
                    if a.get(fld) != b.get(fld):
                        F.append({"where": "%s, %s" % (p["name"], r["name"]), "what": "the clear would not clear the problem: @%s %r and %r" % (fld, a.get(fld), b.get(fld))})
    by_key = {}
    for e in cat["entries"]:
        if e["name"] in events and e.get("type") == "problem":
            f = events[e["name"]]
            by_key.setdefault((f.get("Node"), f.get("AlertKey"), f.get("AlertGroup"), f.get("Manager")), []).append(e)
    for e in cat["entries"]:
        if e["name"] in events and e.get("type") == "resolution":
            f = events[e["name"]]
            for p in by_key.get((f.get("Node"), f.get("AlertKey"), f.get("AlertGroup"), f.get("Manager")), []):
                if p.get("group") != e.get("group"):
                    F.append({"where": "%s, %s" % (e["name"], p["name"]), "what": "the clear %s would also clear %s, a problem of another "
                              "group: same @Node, @AlertKey (%r) and @AlertGroup (%r)" % (e["name"], p["name"], f.get("AlertKey"), f.get("AlertGroup"))})
    agg = cat.get("aggregated")
    alarms = 0
    if agg:
        rising = [e for e in cat["entries"] if e["name"] == agg["trap"]][0]
        falling = [e for e in cat["entries"] if e["name"] == agg.get("cleared_by")]
        for a in cat.get("alarms", []):
            inst = []
            for i, ix in enumerate(agg["index"]):
                inst.append(str(a["id"]) if ix == agg["alarm_index"] else str([10, 0, 0, 5][i] if i < 4 else 0))
            el = trap_element(rising)
            for v in rising["varbinds"]:
                el["OID%d" % v["n"]] = "." + v["oid"] + "." + ".".join(inst)
            sevs = [v for v in rising["varbinds"] if v.get("enums")]
            if sevs:
                el[str(sevs[0]["n"])] = "4"
            try:
                ev = rules.run(el)
            except RulesError as ex:
                F.append({"where": "alarm ID %d" % a["id"], "what": "the simulator stopped: %s" % ex})
                continue
            alarms += 1
            f = ev["field"]
            if a.get("severity") is not None and str(f.get("Severity")) != str(a["severity"]):
                F.append({"where": "alarm ID %d" % a["id"], "what": "a test alarm gave severity %s, the catalogue says %s" % (f.get("Severity"), a["severity"])})
            if a.get("type") and str(f.get("Type")) != tnum[a["type"]]:
                F.append({"where": "alarm ID %d" % a["id"], "what": "a test alarm gave type %s, the catalogue says %s" % (f.get("Type"), a["type"])})
            if falling and a.get("type") == "problem":
                el2 = trap_element(falling[0])
                for v in falling[0]["varbinds"]:
                    el2["OID%d" % v["n"]] = "." + v["oid"] + "." + ".".join(inst)
                g = rules.run(el2)["field"]
                if str(g.get("Type")) != "2":
                    F.append({"where": "alarm ID %d" % a["id"], "what": "its clearing trap gave type %s, not a clear" % g.get("Type")})
                for fld in ("Node", "AlertKey", "AlertGroup", "Agent"):
                    if g.get(fld) != f.get(fld):
                        F.append({"where": "alarm ID %d" % a["id"], "what": "its clearing trap gives another @%s (%r, %r)" % (fld, f.get(fld), g.get(fld))})
    # an unknown trap reaches the default
    ev = rules.run({"Node": "testnode", "IPaddress": "10.9.9.9", "ReceivedTime": "1", "enterprise": ".1.3.6.1.4.1.99999",
                    "generic-trap": "6", "specific-trap": "1"})
    if not ev["field"].get("Summary"):
        F.append({"where": "default", "what": "a trap not in the catalogue gives no summary"})
    summary = "%d test traps sent through the rules (one per trap), %d test alarms through %s, %d problem/clear pairs and every clear by value replayed" % (
        sent, alarms, agg["trap"] if agg else "-", pairs)
    return F, summary
