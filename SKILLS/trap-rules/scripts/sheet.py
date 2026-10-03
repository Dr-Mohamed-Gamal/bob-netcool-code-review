"""Read a trap list: an .xlsx workbook (every sheet) or a .csv file, with no packages.

read(path) -> [{"sheet": name, "rows": [(row number, [cell text, ...]), ...]}]
tables(sheets) finds the trap tables: a header row naming a trap and an OID column.
"""
import csv
import os
import re
import zipfile
import xml.etree.ElementTree as ET

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def col_index(ref):
    letters = re.match(r"[A-Z]+", ref).group(0)
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n - 1


def text_of(node):
    return "".join(t.text or "" for t in node.iter("{%s}t" % NS["m"]))


def read_xlsx(path):
    z = zipfile.ZipFile(path)
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        root = ET.fromstring(z.read("xl/sharedStrings.xml"))
        shared = [text_of(si) for si in root.findall("m:si", NS)]
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    target = {r.get("Id"): r.get("Target") for r in rels}
    out = []
    for s in wb.find("m:sheets", NS):
        name = s.get("name")
        t = target.get(s.get(REL), "")
        t = t.lstrip("/")
        member = t if t.startswith("xl/") else "xl/" + t
        root = ET.fromstring(z.read(member))
        rows = []
        for row in root.iter("{%s}row" % NS["m"]):
            cells = {}
            for c in row.findall("m:c", NS):
                kind, v = c.get("t"), c.find("m:v", NS)
                if kind == "s" and v is not None:
                    val = shared[int(v.text)]
                elif kind == "inlineStr":
                    val = text_of(c)
                else:
                    val = v.text if v is not None else ""
                if val is not None and str(val).strip():
                    cells[col_index(c.get("r"))] = clean_cell(val)
            if cells:
                width = max(cells) + 1
                rows.append((int(row.get("r")), [cells.get(i, "") for i in range(width)]))
        out.append({"sheet": name, "rows": rows})
    return out


def clean_cell(val):
    val = str(val).replace("\r", "")
    if re.match(r"^-?\d+\.0$", val):
        val = val[:-2]
    return "\n".join(x.rstrip() for x in val.strip().split("\n"))


def read_csv(path):
    with open(path, encoding="utf-8-sig", errors="replace", newline="") as fh:
        rows = [(i, [clean_cell(c) for c in r]) for i, r in enumerate(csv.reader(fh), 1) if any(c.strip() for c in r)]
    return [{"sheet": os.path.splitext(os.path.basename(path))[0], "rows": rows}]


def read(path):
    if path.lower().endswith((".xlsx", ".xlsm")):
        return read_xlsx(path)
    if path.lower().endswith((".csv", ".txt")):
        return read_csv(path)
    raise ValueError("%s: give an .xlsx or a .csv trap list" % path)


# What a header cell names: the first pattern that matches wins.
HEADERS = [
    ("oid", r"^(trap\s*oid|snmptrapoid|oid|trap oid|notification oid)$"),
    ("name", r"^(trap\s*name|trapname|notification( name)?)$"),
    ("label", r"^name$"),
    ("severity", r"^(severity|system logging severity level|sev)$"),
    ("component", r"^(componen\w*|node type|device type)$"),
    ("description", r"^(trap description|description)$"),
    ("text", r"^(trap expected event text|expected (event )?text|event text|summary)$"),
    ("module", r"^(mib( file| module)?|source mib|defined in)$"),
    ("alarm_id", r"^(alarm id|event id)$"),
]
OID_RE = re.compile(r"^\.?\d+(\.\d+){3,}$")


def header_map(cells):
    """Header key -> every column it names, in order."""
    found = {}
    for i, c in enumerate(cells):
        h = re.sub(r"\s+", " ", c.lower()).strip()
        for key, pat in HEADERS:
            if re.match(pat, h):
                found.setdefault(key, []).append(i)
                break
    return found


def is_header(cells):
    hm = header_map(cells)
    return "oid" in hm and ("name" in hm or "label" in hm)


def choose(hm, body):
    """One column per key: where a key names several columns, the one whose values fit it."""
    def score(key, i):
        vals = [cells[i] for _, cells in body if i < len(cells) and cells[i]]
        if not vals:
            return 0
        if key == "oid":
            return sum(1 for v in vals if OID_RE.match(v)) / len(vals)
        if key == "severity":
            return sum(1 for v in vals if not v.isdigit()) / len(vals)
        return 1
    out = {}
    for key, cols in hm.items():
        out[key] = max(cols, key=lambda i: (score(key, i), -cols.index(i)))
    if "name" not in out and "label" in out:
        out["name"] = out.pop("label")
    return out


def tables(sheets):
    """Each run of rows under a header row that has an OID column and a name column."""
    out = []
    for sh in sheets:
        rows = sh["rows"]
        k = 0
        while k < len(rows):
            rn, cells = rows[k]
            if is_header(cells):
                body, j = [], k + 1
                while j < len(rows) and not is_header(rows[j][1]):
                    body.append(rows[j])
                    j += 1
                out.append({"sheet": sh["sheet"], "header_row": rn, "columns": choose(header_map(cells), body),
                            "header": cells, "rows": body})
                k = j
            else:
                k += 1
    return out


def cell(cells, i):
    return cells[i] if i is not None and i < len(cells) else ""
