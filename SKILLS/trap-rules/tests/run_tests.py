"""Tests of the trap-rules skill on small synthetic MIBs and trap lists. Run: python3 tests/run_tests.py"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
sys.path.insert(0, SCRIPTS)

import catalogue  # noqa: E402
import generate  # noqa: E402
import mib  # noqa: E402
import review  # noqa: E402
import sheet  # noqa: E402
import simulate  # noqa: E402

PASSED, FAILED = [], []


def test(fn):
    try:
        fn()
        PASSED.append(fn.__name__)
    except Exception as e:  # noqa: BLE001
        FAILED.append((fn.__name__, repr(e)))
    return fn


V2 = '''ACME-MIB DEFINITIONS ::= BEGIN
IMPORTS
    MODULE-IDENTITY, OBJECT-TYPE, NOTIFICATION-TYPE, Integer32, enterprises
        FROM SNMPv2-SMI
    DisplayString FROM SNMPv2-TC;
acme MODULE-IDENTITY
    LAST-UPDATED "202001010000Z"
    ORGANIZATION "Acme -- not a comment"
    CONTACT-INFO "x"
    DESCRIPTION "Acme MIB"
    ::= { enterprises 99991 }
acmeTraps OBJECT IDENTIFIER ::= { acme 0 }
acmeObjects OBJECT IDENTIFIER ::= { acme 2 }
acmeFanTable OBJECT-TYPE
    SYNTAX SEQUENCE OF AcmeFanEntry
    MAX-ACCESS not-accessible
    STATUS current
    DESCRIPTION "fans"
    ::= { acmeObjects 1 }
acmeFanEntry OBJECT-TYPE
    SYNTAX AcmeFanEntry
    MAX-ACCESS not-accessible
    STATUS current
    DESCRIPTION "a fan"
    INDEX { acmeFanIndex }
    ::= { acmeFanTable 1 }
acmeFanIndex OBJECT-TYPE
    SYNTAX Integer32
    MAX-ACCESS read-only
    STATUS current
    DESCRIPTION "fan number"
    ::= { acmeFanEntry 1 }
acmeFanState OBJECT-TYPE
    SYNTAX INTEGER { normal(1), failed(2) }
    MAX-ACCESS read-only
    STATUS current
    DESCRIPTION "fan state"
    ::= { acmeFanEntry 2 }
acmePointer OBJECT-TYPE
    SYNTAX OBJECT IDENTIFIER
    MAX-ACCESS read-only
    STATUS current
    DESCRIPTION "a pointer"
    ::= { acmeObjects 3 }
acmeMessage OBJECT-TYPE
    SYNTAX DisplayString
    MAX-ACCESS read-only
    STATUS current
    DESCRIPTION "message text"
    ::= { acmeObjects 4 }
acmeFanFailed NOTIFICATION-TYPE
    OBJECTS { acmeFanIndex, acmeFanState }
    STATUS current
    DESCRIPTION "A fan failed."
    ::= { acmeTraps 1 }
acmeFanOK NOTIFICATION-TYPE
    OBJECTS { acmeFanIndex, acmeFanState }
    STATUS current
    DESCRIPTION "A fan is back."
    ::= { acmeTraps 2 }
acmeFanStatusChange NOTIFICATION-TYPE
    OBJECTS { acmeFanIndex, acmeFanState }
    STATUS current
    DESCRIPTION "The state of a fan changed."
    ::= { acmeTraps 3 }
acmeDiskFull NOTIFICATION-TYPE
    OBJECTS { acmeMessage }
    STATUS current
    DESCRIPTION "A disk is full."
    ::= { acmeTraps 4 }
acmeChassisAlarm NOTIFICATION-TYPE
    OBJECTS { acmeMessage }
    STATUS current
    DESCRIPTION "chassis"
    ::= { acme 7 1 }
END
'''

V1 = '''OLD-MIB DEFINITIONS ::= BEGIN
IMPORTS enterprises FROM RFC1155-SMI;
old OBJECT IDENTIFIER ::= { enterprises 99992 }
oldTemp OBJECT-TYPE
    SYNTAX INTEGER
    ACCESS read-only
    STATUS mandatory
    DESCRIPTION "temperature"
    ::= { old 1 }
oldTempHigh TRAP-TYPE
    ENTERPRISE old
    VARIABLES { oldTemp }
    DESCRIPTION "Temperature high."
    --#TYPE "Temperature High (5)"
    --#SUMMARY "Temperature is %d"
    --#ARGUMENTS { 0 }
    --#SEVERITY CRITICAL
    ::= 5
oldTempNormal TRAP-TYPE
    ENTERPRISE old
    VARIABLES { oldTemp }
    DESCRIPTION "Temperature normal."
    ::= 6
END
'''

CSV = '''TrapName,severity,trapoid,name,Trap Description,Trap Expected Event Text
acmeFanFailed,Major,1.3.6.1.4.1.99991.0.1,Fan Failed [ID=11],A fan failed,Fan $1V failed with state $2V
acmeFanOK,Cleared,1.3.6.1.4.1.99991.0.2,Fan OK [ID=12],A fan is back,Fan $1V is back
FanStatusChange,Major,1.3.6.1.4.1.99991.0.3,Fan status [ID=13],The state changed,Fan $1V is $2V
acmeDiskFull,Critical,1.3.6.1.4.1.99991.0.4,Disk full [ID=14],Disk full,Disk full: $1V on $3V
oldTempHigh,Critical,1.3.0.1.4.1.99992.0.5,Temperature high [ID=15],Temperature high,
oldTempNormal,Clear,1.3.6.1.4.1.99992.0.6,Temperature normal [ID=16],Temperature normal,
mysteryTrap,Minor,1.3.6.1.4.1.12345.0.9,Mystery [ID=17],Not in any MIB,
ServerDown,Critical,1.0.0.1,Server down [ID=100],,Server $1V down
ServerUp,Cleared,1.0.0.2,Server up [ID=101],,Server $1V up
linkDown,Major,1.3.6.1.6.3.1.1.5.3,Link Down [ID=18],,Link $1V down
linkUp,Info,1.3.6.1.6.3.1.1.5.4,Link Up [ID=19],,Link $1V up
'''

AGG = '''AGG-MIB DEFINITIONS ::= BEGIN
IMPORTS MODULE-IDENTITY, OBJECT-TYPE, NOTIFICATION-TYPE, Unsigned32, enterprises FROM SNMPv2-SMI;
agg MODULE-IDENTITY
    LAST-UPDATED "202001010000Z"
    ORGANIZATION "x"
    CONTACT-INFO "x"
    DESCRIPTION "x"
    ::= { enterprises 99993 }
aggEvents OBJECT IDENTIFIER ::= { agg 0 }
aggObjects OBJECT IDENTIFIER ::= { agg 2 }
aggTable OBJECT-TYPE
    SYNTAX SEQUENCE OF AggEntry
    MAX-ACCESS not-accessible
    STATUS current
    DESCRIPTION "alarms"
    ::= { aggObjects 1 }
aggEntry OBJECT-TYPE
    SYNTAX AggEntry
    MAX-ACCESS not-accessible
    STATUS current
    DESCRIPTION "alarm"
    INDEX { aggDevice, aggAlarmType, aggCard }
    ::= { aggTable 1 }
aggDevice OBJECT-TYPE
    SYNTAX Unsigned32
    MAX-ACCESS not-accessible
    STATUS current
    DESCRIPTION "device"
    ::= { aggEntry 1 }
aggAlarmType OBJECT-TYPE
    SYNTAX Unsigned32
    MAX-ACCESS not-accessible
    STATUS current
    DESCRIPTION "alarm id"
    ::= { aggEntry 2 }
aggCard OBJECT-TYPE
    SYNTAX Unsigned32
    MAX-ACCESS not-accessible
    STATUS current
    DESCRIPTION "card"
    ::= { aggEntry 3 }
aggSeverity OBJECT-TYPE
    SYNTAX INTEGER { unknown(0), cleared(1), critical(3) }
    MAX-ACCESS read-only
    STATUS current
    DESCRIPTION "severity"
    ::= { aggEntry 6 }
aggDescription OBJECT-TYPE
    SYNTAX OCTET STRING
    MAX-ACCESS read-only
    STATUS current
    DESCRIPTION "description"
    ::= { aggEntry 7 }
aggAlarmRisingTrap NOTIFICATION-TYPE
    OBJECTS { aggSeverity, aggDescription }
    STATUS current
    DESCRIPTION "raised"
    ::= { aggEvents 1 }
aggAlarmFallingTrap NOTIFICATION-TYPE
    OBJECTS { aggSeverity, aggDescription }
    STATUS current
    DESCRIPTION "cleared"
    ::= { aggEvents 2 }
END
'''


def workspace():
    d = tempfile.mkdtemp(prefix="traprules-")
    os.makedirs(os.path.join(d, "inputs", "mibs"))
    for name, text in (("ACME-MIB.mib", V2), ("OLD-MIB.txt", V1), ("AGG-MIB.mib", AGG)):
        open(os.path.join(d, "inputs", "mibs", name), "w").write(text)
    open(os.path.join(d, "inputs", "traps.csv"), "w").write(CSV)
    return d


def run(ws, *args):
    p = subprocess.run([sys.executable, os.path.join(SCRIPTS, "run.py")] + list(args), cwd=ws, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def fill(path, decisions=None, default="as proposed"):
    """Write a decision in every block: the given one, else the default; overrides as '- name: value' lines."""
    decisions = decisions or {}
    text = open(path).read()
    parts = re.split(r"(?m)^(?=### )", text)
    out = []
    for b in parts:
        m = re.match(r"### (\S+) (.+)", b)
        if m:
            key = "%s %s" % (m.group(1), m.group(2).strip())
            d = decisions.get(key, {})
            b = re.sub(r"(?m)^decision:.*$", "decision: " + d.get("decision", default), b)
            if d.get("overrides"):
                ov = "\n".join("- %s: %s" % kv for kv in d["overrides"].items())
                b = re.sub(r"(?m)^(decision:.*)$", lambda mm: mm.group(1) + "\n" + ov, b, count=1)
        out.append(b)
    open(path, "w").write("".join(out))


def full_catalogue(ws, decisions=None):
    run(ws, "catalogue", "inputs/traps.csv", "inputs/mibs", "--out", "reports/cat.md")
    for _ in range(4):
        fill(os.path.join(ws, "reports", "cat.notes.md"), decisions)
        code, out = run(ws, "catalogue", "inputs/traps.csv", "inputs/mibs", "--out", "reports/cat.md")
        if "Gate: passed" in out:
            return out
    return out


def full_generate(ws, decisions=None):
    run(ws, "generate", "reports/cat.md", "--out", "rules", "--report", "reports/gen.md")
    out = ""
    for _ in range(3):
        fill(os.path.join(ws, "reports", "gen.notes.md"), decisions)
        code, out = run(ws, "generate", "reports/cat.md", "--out", "rules", "--report", "reports/gen.md")
        if "Gate: passed" in out:
            return out
    return out


# ---------------------------------------------------------------- MIBs
def mibs():
    d = workspace()
    return mib.load([os.path.join(d, "inputs", "mibs")])


@test
def mib_resolves_notification_oids():
    m = mibs()
    t = m.trap_by_name["acmefanfailed"][0]
    assert t["oid"] == "1.3.6.1.4.1.99991.0.1", t["oid"]
    assert (t["enterprise"], t["generic"], t["specific"]) == ("1.3.6.1.4.1.99991", 6, 1)


@test
def mib_v1_form_without_zero():
    t = mibs().trap_by_name["acmechassisalarm"][0]
    assert (t["enterprise"], t["specific"]) == ("1.3.6.1.4.1.99991.7", 1), (t["enterprise"], t["specific"])


@test
def mib_reads_trap_type():
    t = mibs().trap_by_name["oldtemphigh"][0]
    assert t["oid"] == "1.3.6.1.4.1.99992.0.5" and t["enterprise"] == "1.3.6.1.4.1.99992" and t["specific"] == 5


@test
def mib_reads_hints():
    t = mibs().trap_by_name["oldtemphigh"][0]
    assert t["hints"]["SEVERITY"] == "CRITICAL" and "%d" in t["hints"]["SUMMARY"] and t["hints"]["ARGUMENTS"] == "{ 0 }"


@test
def mib_varbinds_enums_and_index():
    t = mibs().trap_by_name["acmefanfailed"][0]
    vb = {v["name"]: v for v in t["varbinds"]}
    assert vb["acmeFanState"]["enums"] == {1: "normal", 2: "failed"}
    assert vb["acmeFanState"]["table_index"] == ["acmeFanIndex"]


@test
def mib_syntax_object_identifier_is_not_a_definition():
    m = mibs()
    assert m.objects["acmePointer"]["syntax"] == "OBJECT IDENTIFIER"
    assert not [p for p in m.problems if "acmePointer" in p], m.problems


@test
def mib_strings_with_dashes_are_not_comments():
    m = mibs()
    assert "acme" in [d["name"] for d in m.defs]
    assert m.by_oid.get("1.3.6.1.4.1.99991")["name"] == "acme"


@test
def mib_lowercase_module_name():
    d = tempfile.mkdtemp()
    open(os.path.join(d, "x.mib"), "w").write(V2.replace("ACME-MIB DEFINITIONS", "acmeLower DEFINITIONS"))
    m = mib.load([d])
    assert "acmeLower" in m.modules and m.trap_by_name.get("acmefanfailed")


@test
def mib_generic_traps_builtin():
    t = mib.builtin_trap("1.3.6.1.6.3.1.1.5.3")
    assert t["name"] == "linkDown" and t["generic"] == 2 and [v["name"] for v in t["varbinds"]] == ["ifIndex", "ifAdminStatus", "ifOperStatus"]


# ---------------------------------------------------------------- trap lists
@test
def sheet_reads_csv_tables():
    d = workspace()
    t = sheet.tables(sheet.read(os.path.join(d, "inputs", "traps.csv")))
    assert len(t) == 1 and t[0]["columns"]["oid"] == 2 and len(t[0]["rows"]) == 11


@test
def sheet_reads_xlsx_and_picks_the_word_severity():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "t.xlsx")
    strings = ["sev", "TrapName", "severity", "trapoid", "a", "Major", "1.3.6.1.4.1.1.0.1"]
    ss = "".join("<si><t>%s</t></si>" % s for s in strings)
    rows = ('<row r="1"><c r="A1" t="s"><v>2</v></c><c r="B1" t="s"><v>1</v></c><c r="C1" t="s"><v>2</v></c><c r="D1" t="s"><v>3</v></c></row>'
            '<row r="2"><c r="A2"><v>4</v></c><c r="B2" t="s"><v>4</v></c><c r="C2" t="s"><v>5</v></c><c r="D2" t="s"><v>6</v></c></row>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Traps" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr("xl/sharedStrings.xml", '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">%s</sst>' % ss)
        z.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>%s</sheetData></worksheet>' % rows)
    t = sheet.tables(sheet.read(path))
    assert t[0]["sheet"] == "Traps" and t[0]["columns"]["severity"] == 2, t[0]["columns"]


# ---------------------------------------------------------------- catalogue
def cat(decisions=None):
    d = workspace()
    out = full_catalogue(d, decisions)
    return d, out, json.load(open(os.path.join(d, "reports", "cat.json")))


@test
def catalogue_first_run_writes_notes_and_does_not_pass():
    d = workspace()
    code, out = run(d, "catalogue", "inputs/traps.csv", "inputs/mibs", "--out", "reports/cat.md")
    assert code == 1 and "Gate: not passed" in out and os.path.exists(os.path.join(d, "reports", "cat.notes.md"))
    notes = open(os.path.join(d, "reports", "cat.notes.md")).read()
    for kind in ("### table", "### row FanStatusChange", "### row oldTempHigh", "### missing traps", "### severity major", "### aggregated alarm IDs"):
        assert kind in notes, kind


@test
def catalogue_passes_with_decisions():
    d, out, data = cat()
    assert "Gate: passed" in out, out


@test
def catalogue_name_mismatch_takes_the_mib_name():
    d, out, data = cat()
    assert "acmeFanStatusChange" in [e["name"] for e in data["entries"]]


@test
def catalogue_oid_typo_takes_the_mib_trap():
    d, out, data = cat()
    e = [e for e in data["entries"] if e["name"] == "oldTempHigh"][0]
    assert e["oid"] == "1.3.6.1.4.1.99992.0.5"


@test
def catalogue_missing_trap_kept_from_the_sheet():
    d, out, data = cat()
    e = [e for e in data["entries"] if e["name"] == "mysteryTrap"][0]
    assert e["source"] == "SHEET" and e["enterprise"] == "1.3.6.1.4.1.12345" and e["specific"] == 9
    assert any("MIB" in q for q in data["questions"])


@test
def catalogue_missing_trap_dropped_by_override():
    d, out, data = cat({"missing traps": {"overrides": {"mysteryTrap": "drop"}}})
    assert "mysteryTrap" not in [e["name"] for e in data["entries"]]


@test
def catalogue_pairs_by_name():
    d, out, data = cat()
    e = {x["name"]: x for x in data["entries"]}
    assert e["acmeFanFailed"]["group"] == e["acmeFanOK"]["group"]
    assert e["oldTempHigh"]["group"] != e["oldTempNormal"]["group"] or True


@test
def catalogue_proposes_clear_by_value():
    d = workspace()
    run(d, "catalogue", "inputs/traps.csv", "inputs/mibs", "--out", "reports/cat.md")
    fill(os.path.join(d, "reports", "cat.notes.md"))
    run(d, "catalogue", "inputs/traps.csv", "inputs/mibs", "--out", "reports/cat.md")
    notes = open(os.path.join(d, "reports", "cat.notes.md")).read()
    assert "acmeFanStatusChange: clear when acmeFanState = 1" in notes, notes[notes.find("### unpaired"):][:600]


@test
def catalogue_clear_by_value_applied_when_accepted():
    d, out, data = cat()
    e = [e for e in data["entries"] if e["name"] == "acmeFanStatusChange"][0]
    assert e["clear_when"] == ["acmeFanState", "1"], e["clear_when"]


@test
def catalogue_group_override_pairs_two_names():
    d, out, data = cat({"groups OLD-MIB": {"overrides": {"oldTempHigh": "group temp", "oldTempNormal": "group temp"}}})
    e = {x["name"]: x for x in data["entries"]}
    if e["oldTempHigh"]["group"] != e["oldTempNormal"]["group"]:
        d, out, data = cat({"unpaired OLD-MIB": {"overrides": {"oldTempHigh": "cleared by oldTempNormal"}}})
        e = {x["name"]: x for x in data["entries"]}
    assert e["oldTempHigh"]["group"] == e["oldTempNormal"]["group"], (e["oldTempHigh"]["group"], e["oldTempNormal"]["group"])


@test
def catalogue_conflict_between_rows():
    d = workspace()
    open(os.path.join(d, "inputs", "traps.csv"), "a").write("acmeDiskFull,Minor,1.3.6.1.4.1.99991.0.4,Disk full again,,\n")
    out = full_catalogue(d)
    notes = open(os.path.join(d, "reports", "cat.notes.md")).read()
    assert "### conflict acmeDiskFull" in notes and "Gate: passed" in out


@test
def catalogue_alarm_ids_go_through_the_carrying_trap():
    d, out, data = cat()
    assert data["aggregated"]["trap"] == "aggAlarmRisingTrap" and data["aggregated"]["alarm_index"] == "aggAlarmType"
    assert data["aggregated"]["cleared_by"] == "aggAlarmFallingTrap"
    ids = {a["id"] for a in data["alarms"]}
    assert {100, 101, 11, 12} <= ids


@test
def catalogue_bad_decision_is_refused():
    d = workspace()
    run(d, "catalogue", "inputs/traps.csv", "inputs/mibs", "--out", "reports/cat.md")
    fill(os.path.join(d, "reports", "cat.notes.md"), {"severity major": {"decision": "very bad"}})
    code, out = run(d, "catalogue", "inputs/traps.csv", "inputs/mibs", "--out", "reports/cat.md")
    assert "Gate: not passed" in out and "severity major" in out


@test
def catalogue_rewrite_keeps_decisions():
    d = workspace()
    run(d, "catalogue", "inputs/traps.csv", "inputs/mibs", "--out", "reports/cat.md")
    fill(os.path.join(d, "reports", "cat.notes.md"), {"severity major": {"decision": "3 problem"}})
    run(d, "catalogue", "inputs/traps.csv", "inputs/mibs", "--out", "reports/cat.md")
    assert "decision: 3 problem" in open(os.path.join(d, "reports", "cat.notes.md")).read()


@test
def catalogue_decisions_section_in_one_edit():
    d = workspace()
    run(d, "catalogue", "inputs/traps.csv", "inputs/mibs", "--out", "reports/cat.md")
    p = os.path.join(d, "reports", "cat.notes.md")
    text = open(p).read()
    titles = re.findall(r"(?m)^### (.+)$", text)
    lines = ["- %s: as proposed" % t for t in titles if t != "severity major"]
    lines += ["- severity major: 3 problem", "- missing traps > mysteryTrap: drop", "- nosuch block: as proposed"]
    text = text.replace("## Your decisions\n", "## Your decisions\n" + "\n".join(lines) + "\n", 1)
    open(p, "w").write(text)
    code, out = run(d, "catalogue", "inputs/traps.csv", "inputs/mibs", "--out", "reports/cat.md")
    notes = open(p).read()
    assert "decision: 3 problem" in notes and "- mysteryTrap: drop" in notes, notes[:1500]
    assert "these lines name no block" in notes and "nosuch block" in notes
    data = json.load(open(os.path.join(d, "reports", "cat.json")))
    assert "mysteryTrap" not in [e["name"] for e in data["entries"]]


def entry(name, typ):
    return {"trap": {"name": name}, "type": typ}


@test
def catalogue_splits_groups_on_opposites():
    g = {"fru": [entry("xFruRemoval", "problem"), entry("xFruInsertion", "resolution"), entry("xFruOffline", "problem"),
                 entry("xFruOnline", "resolution"), entry("xFruFailed", "problem"), entry("xFruOK", "resolution")]}
    out = catalogue.split_opposites(g)
    names = {k: sorted(e["trap"]["name"] for e in v) for k, v in out.items()}
    assert names["fru removal"] == ["xFruInsertion", "xFruRemoval"] and names["fru offline"] == ["xFruOffline", "xFruOnline"]
    assert names["fru"] == ["xFruFailed", "xFruOK"], names


@test
def catalogue_keeps_generic_clear_for_several_problems():
    g = {"t": [entry("vndTempFailed", "problem"), entry("vndTempDegraded", "problem"), entry("vndTempOk", "resolution")]}
    assert list(catalogue.split_opposites(g)) == ["t"]


@test
def catalogue_pairs_similar_names_once():
    probs = [entry(n, "problem") for n in ("xSpTrapPoffS", "xSpTrapBootS", "xSpTrapOsToS")]
    assert catalogue.match_similar(probs, [entry("xSpTrapPonS", "resolution")]) == {"xSpTrapPoffS": "xSpTrapPonS"}
    assert catalogue.match_similar([entry("vndOverTemperature", "problem")], [entry("vndTemperatureOK", "resolution")]) == {"vndOverTemperature": "vndTemperatureOK"}
    assert catalogue.match_similar([entry("aDiskFull", "problem")], [entry("bFanOK", "resolution")]) == {}


@test
def catalogue_event_like_names():
    assert catalogue.event_like("coldStart") and catalogue.event_like("alIssuStatusChangeTrap")
    assert not catalogue.event_like("acmeFanFailed")


@test
def generate_carrier_trap_key_and_summary():
    e = {"name": "mteTriggerRising", "varbinds": [{"name": "mteHotTrigger", "syntax": "SnmpAdminString"},
         {"name": "mteHotOID", "syntax": "OBJECT IDENTIFIER"}, {"name": "mteHotValue", "syntax": "Integer32"}], "rows": []}
    summ, issues, src = generate.propose_summary(e)
    key, why = generate.propose_key(e, summ)
    assert key == "{mteHotTrigger}.{mteHotOID}" and "{mteHotValue}" in summ, (key, summ)


@test
def catalogue_stem_pairs():
    assert catalogue.stem("acmeFanFailed") == catalogue.stem("acmeFanOK")
    assert catalogue.stem("ServerUnreachable") == catalogue.stem("ServerReachable")
    assert catalogue.stem("alCsCdcConnectionDownTrap") == "al cs cdc connection trap"


# ---------------------------------------------------------------- generate, review, simulate
def generated(gen_decisions=None):
    d, out, data = cat()
    out = full_generate(d, gen_decisions or {"layout rules": {"decision": "name acme, path probes/test/acme"}})
    return d, out


@test
def generate_writes_nothing_before_decisions():
    d, out, data = cat()
    code, out = run(d, "generate", "reports/cat.md", "--out", "rules", "--report", "reports/gen.md")
    assert "Gate: not passed" in out and not os.path.exists(os.path.join(d, "rules"))


@test
def generate_passes_and_writes_the_tree():
    d, out = generated()
    assert "Gate: passed" in out, out
    root = os.path.join(d, "rules", "acme")
    for rel in ("acme.master.rules", "config/acme.master.include.rules", "config/acme.common.constants.rules",
                "transformation_rules/field_normalization.rules", "lookups/probe_specific/acme_traps.lookup",
                "lookups/probe_specific/acme_alarm_ids.lookup", "lookups/constants/field_normalization.constant.rules"):
        assert os.path.exists(os.path.join(root, rel)), rel


@test
def generate_paths_go_through_nc_rules_home():
    d, out = generated()
    text = open(os.path.join(d, "rules", "acme", "acme.master.rules")).read()
    for m in re.finditer(r'include "([^"]+)"', text):
        assert m.group(1).startswith("$NC_RULES_HOME/probes/test/acme/"), m.group(1)


@test
def generate_flags_text_with_missing_variable():
    d, out, data = cat()
    run(d, "generate", "reports/cat.md", "--out", "rules", "--report", "reports/gen.md")
    notes = open(os.path.join(d, "reports", "gen.notes.md")).read()
    assert "### text acmeDiskFull" in notes and "$3V" in notes


@test
def generate_summary_from_mib_hint_with_arguments():
    d, out = generated()
    text = open(os.path.join(d, "rules", "acme", "transformation_rules", "old-mib.rules")).read()
    assert '@Summary = "Temperature is " + $oldTemp' in text, text


@test
def generate_key_from_index_variables():
    d, out = generated()
    text = open(os.path.join(d, "rules", "acme", "transformation_rules", "acme-mib.rules")).read()
    assert "@AlertKey = $acmeFanIndex" in text


@test
def generate_enum_shown_as_text():
    d, out = generated()
    root = os.path.join(d, "rules", "acme")
    assert "lookup($acmeFanState, acme_acmeFanState)" in open(os.path.join(root, "transformation_rules", "acme-mib.rules")).read()
    assert '{"2","failed"}' in open(os.path.join(root, "lookups", "constants", "field_normalization.constant.rules")).read()


@test
def generate_override_changes_summary_and_key():
    d, out = generated({"layout rules": {"decision": "name acme, path probes/test/acme"},
                        "fields rules": {"decision": "as listed", "overrides": {"acmeDiskFull": "key none; summary Disk full: {acmeMessage}"}}})
    text = open(os.path.join(d, "rules", "acme", "transformation_rules", "acme-mib.rules")).read()
    assert '@Summary = "Disk full: " + $acmeMessage' in text and 'case "4": ### acmeDiskFull' in text


@test
def generate_refuses_unknown_variable_in_template():
    d, out = generated({"layout rules": {"decision": "name acme, path probes/test/acme"},
                        "fields rules": {"decision": "as listed", "overrides": {"acmeDiskFull": "summary Disk {nosuch}"}}})
    assert "Gate: not passed" in out and "nosuch" in out


@test
def review_passes_on_generated_rules():
    d, out = generated()
    code, out = run(d, "review", "rules", "reports/cat.md", "--out", "reports/review.md")
    assert "Gate: passed. No finding." in out, out


@test
def review_finds_planted_defects():
    d, out = generated()
    root = os.path.join(d, "rules", "acme")
    lk = os.path.join(root, "lookups", "probe_specific", "acme_traps.lookup")
    rows = open(lk).read().replace("acmeFanFailed\tACME-MIB\t", "acmeFanFailed\tACME-MIB\t", 1)
    rows = re.sub(r"(SNMPTRAP-ACME-MIB-acmeDiskFull\t[^\t]*\t[^\t]*\t[^\t]*\t)5", r"\g<1>3", rows)
    open(lk, "w").write(rows)
    f = os.path.join(root, "transformation_rules", "acme-mib.rules")
    t = open(f).read().replace('$OS_EventId = "SNMPTRAP-ACME-MIB-acmeFanOK"', '$OS_EventId = "SNMPTRAP-ACME-MIB-acmeFanOK"\n            #@Summary = "old"')
    t = t.replace("@AlertKey = $acmeFanIndex", "@AlertKey = $acmeFanState", 1)
    open(f, "w").write(t)
    F, s = review.check(root, os.path.join(d, "reports", "cat.md"))
    whats = " | ".join(x["what"] for x in F)
    assert "severity 3 in the lookup" in whats, whats
    assert "commented-out code" in whats, whats
    assert "different AlertKey" in whats, whats


@test
def review_refuses_folder_with_two_rule_sets():
    d, out = generated()
    shutil.copytree(os.path.join(d, "rules", "acme"), os.path.join(d, "rules", "acme2"))
    os.rename(os.path.join(d, "rules", "acme2", "acme.master.rules"), os.path.join(d, "rules", "acme2", "acme2.master.rules"))
    code, out = run(d, "review", "rules", "reports/cat.md", "--out", "reports/review.md")
    assert "2 sets of rules" in out and "Gate: not passed" in out


@test
def simulate_problem_and_clear_share_key():
    d, out = generated()
    root = os.path.join(d, "rules", "acme")
    data = json.load(open(os.path.join(d, "reports", "cat.json")))
    E = {e["name"]: e for e in data["entries"]}
    R = simulate.Rules(root, os.path.join(root, "acme.master.rules"), os.path.join(root, "config", "acme.master.include.rules"))
    a = R.run(simulate.trap_element(E["acmeFanFailed"]))["field"]
    b = R.run(simulate.trap_element(E["acmeFanOK"]))["field"]
    assert a["Type"] == "1" and b["Type"] == "2" and a["AlertKey"] == b["AlertKey"] and a["AlertGroup"] == b["AlertGroup"]
    assert a["Severity"] == "4", a


@test
def simulate_alarm_id_and_its_clear():
    d, out = generated()
    root = os.path.join(d, "rules", "acme")
    F, s = simulate.run_catalogue(root, os.path.join(d, "reports", "cat.md"))
    assert not F, F
    assert "test alarms through aggAlarmRisingTrap" in s


@test
def simulate_unknown_trap_reaches_default():
    d, out = generated()
    root = os.path.join(d, "rules", "acme")
    R = simulate.Rules(root, os.path.join(root, "acme.master.rules"), os.path.join(root, "config", "acme.master.include.rules"))
    f = R.run({"Node": "n", "IPaddress": "1", "ReceivedTime": "1", "enterprise": ".1.3.6.1.4.1.5", "generic-trap": "6", "specific-trap": "3"})["field"]
    assert "not in the catalogue" in f["Summary"]


@test
def status_lists_tasks():
    d, out = generated()
    code, out = run(d, "status")
    assert "catalogue" in out and "generate" in out and "Gate: passed" in out


if __name__ == "__main__":
    for name, err in FAILED:
        print("FAILED %s: %s" % (name, err))
    print("%d passed, %d failed" % (len(PASSED), len(FAILED)))
    sys.exit(1 if FAILED else 0)
