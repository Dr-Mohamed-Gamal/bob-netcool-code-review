#!/usr/bin/env python3
"""Tests for the scripts of the code-review skill.

    python3 run_tests.py

Writes small samples in several languages to a temporary folder, each with
defects planted at known lines, and runs the scripts on them the way a user
would, as commands: the scan, the review and its notes file, the fix and its
notes file, the change made from a plan, the comparison and the trace of two
versions, and the one command that runs each step. It checks what they print
and what they write. Exit code 0 when every test passes. Python standard
library only.

The scan reads the documents (.txt, .md) next to the code and under the
working folder, so every command here runs in an empty working folder and
each flow has a folder of its own; a document is only ever placed on
purpose. A test marked "known fault" describes a fault in a script that is
still to be corrected: it is expected to fail until the script is corrected.
Every temporary file is deleted at the end.
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
TITLES = ["Assignment in a condition", "Name read, never assigned", "Name assigned, never read",
          "Name used once, close to another name", "Name not in the list of names", "Assigned twice in a row",
          "Entity without its closing ;", "Tag opened and closed a different number of times",
          "Placeholder text in strings", "Brackets that do not balance", "&& and || mixed without brackets",
          "else or else-if with no if before it", "Names that differ only by letter case",
          "Same condition twice in one chain", "Compared or assigned to itself", "Block with nothing in it",
          "Name read before the line that first sets it", "Result indexed before its size is checked",
          "Loop whose condition nothing in the loop changes", "Error handler that only logs",
          "Query built by joining text with a value", "Environment name, address or credential in a string",
          "Function defined and never called", "Comparisons that contradict each other", "Condition followed by ;",
          "Comparison whose result is not used", "Branches with the same statements",
          "Same label twice in one switch", "Function defined more than once",
          "Code after a statement that leaves the block", "String not closed on its line",
          "Loop bound that includes the size", "Command or code run with text joined to a value",
          "Data from outside the code is changed", "Replace limited to a count"]

SAMPLES = {
    "defects.js": """// billing
function total(items, taxRate) {
  let sum = 0;
  for (const item of items) {
    if (item.price = 0) { continue; }
    sum += item.price * item.qty;
  }
  let label = "<b>Total&nbsp</b>";
  label = "<b>Total";
  if (sum == 0 || taxrate > 1) { return "TODO: " + label; }
  return sum * (1 + taxRate);
}
""",
    "clean.js": """// billing, nothing wrong
function total(items, taxRate) {
  let sum = 0;
  for (let i = 0; i < items.length; i++) {
    if (items[i].price === 0 || items[i].qty <= 0) { continue; }
    sum += items[i].price * items[i].qty;
  }
  const label = "<b>Total</b> &amp; tax";
  return label + sum * (1 + taxRate);
}
print(total([], 0));
""",
    "defects.py": '''# billing helper; don't count free items
def total(items, tax_rate):
    """Sum the items."""
    amount = 0
    for item in items:
        if item.price == 0:   # skip
            continue
        amount += item.price * item.qty
    half = amount // 2 + bonus
    unused = half
    if half > 10 and taxrate > 1:
        return "TODO: fix"
    extra = 1 if check(flag=True) else 0
    return amount * (1 + tax_rate) + extra
''',
    "Defects.java": """public class Billing {
    /* totals */
    public static double total(double[] prices, double taxRate) {
        double sum = 0;
        boolean done = false;
        for (double price : prices) {
            if (done = true) { break; }
            sum += price;
        }
        String label = "<b>Total&amp</b>";
        return sum * (1 + taxrate) + label.length();
    }
}
""",
    "defects.php": """<?php
// billing
function total($items, $taxRate) {
    $sum = 0;
    # each item
    foreach ($items as $item) {
        if ($item['price'] = 0) { continue; }
        $sum += $item['price'];
    }
    return $sum * (1 + $taxrate);
}
""",
    "defects.c": """#include <stdio.h>
/* totals */
int total(int *prices, int n) {
    int sum = 0;
    int i;
    for (i = 0; i < n; i++) {
        if (sum = 100) { break; }
        sum += prices[i];
    }
    printf("total: %d\\n", sum);
    return sum + offset;
}
""",
    "deploy.sh": """#!/bin/sh
# deploy
target="prod"
if [ "$target" = "prod" ]; then
  echo "deploying to $target"
fi
""",
    "report.sql": """-- monthly report
IF v_count = 0 THEN
  v_total := 1;
END IF;
""",
    "rules.src": """// sample rules
if (@Severity = 5) {
    Title = "Critical: " + @Node;
}
elseif (@Severity == 4 && @Manager = 'Collector') {
    Title = "Major: " + @Node;
}
Summary = Title + " " + sumary;
Summary = Summary + " at " + Node;
Payload = '<param name="title">' + Summary + '<param>' + "&lt" + 'Test1,Test2';
log("done " + Payload);
""",
}

# More languages: (file name, text, {title index: expected count}, names that must be the only unset ones)
MORE_LANGUAGES = [
    ("billing.ts", """// billing
interface Item { price: number; qty: number; }
export function total(items: Item[], taxRate: number): number {
  let sum: number = 0;
  for (const item of items) {
    if (item.price = 0) { continue; }
    sum += item.price * item.qty;
  }
  const label: string = "<b>Total&nbsp</b>";
  return sum * (1 + taxrate) + label.length;
}
console.log(total([], 0));
""", {0: 1, 6: 1}, ["taxrate"]),
    ("Billing.cs", """using System;
using System.Collections.Generic;
namespace Shop {
    public class Billing {
        public static double Total(List<double> prices, double taxRate) {
            double sum = 0;
            bool done = false;
            foreach (var price in prices) {
                if (done = true) { break; }
                sum += price;
            }
            string label = "<b>Total";
            Console.WriteLine(label);
            return sum * (1 + taxrate);
        }
    }
}
""", {0: 1}, ["taxrate"]),
    ("billing.go", """package billing

// Total adds the prices
func Total(prices []float64, taxRate float64) float64 {
	sum := 0.0
	for i := 0; i <= len(prices); i++ {
		sum += prices[i]
	}
	if sum == sum {
		return 0
	}
	return sum * (1 + taxrate)
}
""", {0: 0, 14: 1, 31: 1}, ["taxrate"]),
    ("billing.rb", """# billing
def total(items, tax_rate)
  sum = 0
  items.each do |item|
    sum += item.price * item.qty
  end
  if sum = 0
    puts "TODO: nothing to bill"
  end
  sum * (1 + taxrate)
end
puts total([], 0)
""", {0: 1, 8: 1}, ["taxrate"]),
    ("Billing.kt", """// billing
fun total(items: List<Double>, taxRate: Double): Double {
    var sum = 0.0
    val label: String = "<b>Total</b>"
    for (price in items) {
        sum += price
    }
    if (sum == sum) { println(label) }
    return sum * (1 + taxrate)
}
fun main() { println(total(listOf(), 0.0)) }
""", {0: 0, 14: 1}, ["taxrate"]),
    ("billing.pl", """#!/usr/bin/perl
# billing
use strict;
sub total {
    my ($items, $tax_rate) = @_;
    my $sum = 0;
    foreach my $item (@$items) {
        if ($item->{price} = 0) { next; }
        $sum += $item->{price};
    }
    return $sum * (1 + $taxrate);
}
print total([], 0);
""", {0: 1}, ["$taxrate"]),
    ("billing.ps1", """# billing
function Get-Total($items, $taxRate) {
    $sum = 0
    foreach ($item in $items) {
        if ($item.Price = 0) { continue }
        $sum += $item.Price
    }
    Write-Host "TODO: check tax"
    return $sum * (1 + $taxrate)
}
Get-Total @() 0
""", {0: 1, 8: 1}, ["$taxrate"]),
    ("billing.lua", """-- billing
local function total(items, taxRate)
  local sum = 0
  for i = 1, #items do
    if items[i].price ~= 0 then
      sum = sum + items[i].price
    end
  end
  if sum == sum then
    return 0
  end
  return sum * (1 + taxrate)
end
print(total({}, 0))
""", {0: 0, 14: 1}, ["taxrate"]),
]

BEFORE = """// lookups
function load(key) {
  let a = fetchRows(table, "name = '" + key + "'");
  let b = fetchRows(table, "owner = '" + key + "'");
  let label = "Total: ";
  if (a.length > 0) { label = label + a[0]; } else { label = label + "none"; }
  return label + b.length;
}
"""
AFTER_SWAP = """// lookups
function load(key) {
  let rows = runQuery("select * from " + table + " where name = '" + key + "'");
  let label = "Total = ";
  label = label + (rows.length > 0 ? rows[0] : "none");
  return label + rows.length;
}
"""
SPLIT_A = """// part one
function prepare(key) {
  let a = fetchRows(table, "name = '" + key + "'");
  let b = fetchRows(table, "owner = '" + key + "'");
  wirelessType = "Fixed";
  return a.length + b.length;
}
"""
SPLIT_B = """// part two
function build() {
  let label = "Total: ";
  if (rowCount > 0) { label = label + WIRELESSTYPE; } else { label = label + "none"; }
  return label;
}
"""

# Code that comes with a document: a list of the fields, with their types. The code reads one
# field the list does not hold (@Severty), one field used once that the list holds (@Mode), and
# joins a numeric field into a query.
FIELDS_CODE = """// rules with fields
if (@Severity == 5) {
    @Summary = "Critical on " + @Node;
}
if (@Manager == 'Collector') {
    @Summary = @Summary + " from " + @Agent + " " + @Mode;
}
@Identifier = @Node + @Severty;
Details = "select * from alerts where sev = " + @Severity;
@Summary = @Summary + Details;
"""
FIELDS_DOC = """# Event fields

Fields of the event:
Severity  Integer
Summary  String
Node  String
Manager  String
Agent  String
Identifier  String
Mode  String
"""

# Code for the change made from a plan: CRLF line endings and one latin-1 character, which the
# copy must keep byte for byte.
EDIT_CODE = """// lookups: r\xe8gles
function load(key) {
  let order_total = fetchRows(table, "name = '" + key + "'");
  let row_count = fetchRows(table, "owner = '" + key + "'");
  log("order_total is " + order_total);
  obj.order_total = order_total;
  let label = "Total: ";
  if (order_total.length > 0) { label = label + order_total[0]; } else { label = label + "none"; }
  return label + row_count.length;
}
"""
EDIT_EXPECTED = """// lookups: r\xe8gles
// generated from the plan
'use strict';
function load(key) {
  const orderRows = fetchRows(table, "name = '" + key + "'");
  const row_count = fetchRows(table, "owner = '" + key + "'");
  log("order_total is " + orderRows);
  obj.order_total = orderRows;
  let label = "Sum: ";
  if (orderRows.length > 0) { label = label + orderRows[0]; } else { label = label + "none"; }
  return label + row_count.length;
}
"""
EDIT_PLAN_PARTS = """## Corrections
### line 7
after: let label = "Sum: ";
why: the requirement renames the label from Total to Sum; the rest of the line is the same.

### after line 1
insert:
```
// generated from the plan
'use strict';
```
why: the requirement asks for strict mode at the top of every file.

### rule constants
match: let (\\w+) = fetchRows
with: const \\1 = fetchRows
why: the requirement asks for constants where a value is set once; both lookups are set once.
"""
EDIT_PLAN_REFUSED = """
### rule nothing
match: zzz_never_there
with: y
why: this rule matches nothing and must be refused by the script.

### rule broken
match: ([unclosed
with: x
why: this regular expression is not valid and must be refused.
"""
EDIT_PLAN_TAIL = """
## Renames
order_total -> orderRows
%s
## Explanations
The label text "Total: " becomes "Sum: " because the requirement renames the label.
The string "use strict" is the strict mode line the requirement asks for.
The keyword `const` replaces let for the two lookups, as the requirement asks for constants.

## Verdict
The plan renames the lookup result, makes the two lookups constants and adds strict mode.
"""

# Code for a split into files: two functions and the call that uses both.
SPLIT_CODE = """// part one: lookups
function load(key) {
  let order_total = fetchRows(table, "name = '" + key + "'");
  TT_Check_Data = order_total.length;
  return order_total;
}
// part two: labels
function build(rows) {
  let label = "Total: ";
  if (rows.length > 0) { label = label + rows[0]; } else { label = label + "none"; }
  return label;
}
send(build(load(key)));
"""
SPLIT_PLAN = """# Plan

## Corrections
### line 13
remove: yes
why: the call at the end moves to the second file as its last line, see the append below.

## Renames
accept the proposals

## Files
### lib/lookups.js
lines: 1-6
why: the lookup function, as the requirement asks for one file per concern.

### lib/labels.js
lines: %s
prepend:
```
// labels, split from big.js
```
append:
```
send(build(load(key)));
```
why: the label function and the call that uses both.
%s
## Explanations
`send`, `build` and `load` are called from the new last line of labels.js, as before.
The line `// labels, split from big.js` is a comment that names the origin of the file.
lib/lookups.js and lib/labels.js are both loaded by the page that uses them; neither names the other.
"""
SPLIT_PLAN_OUTSIDE = """
### lib/outside.js
lines: 40-45
why: a range outside the code, to be refused.
"""

# The corrections a person writes for the fix of rules.src: one line, a removal, an indented line
# and a fenced block that replaces three lines by four. The removal is not the last block on purpose.
FIX_NOTES = """# Notes for the change log log.md

## Corrections
### line 8
kind: Misspelt name
after: Summary = Title + " " + @Summary;
why: sumary is nothing; the field @Summary holds the summary of the event, so for the summary "Link down" the line now gives "Major: n Link down" and no longer "Major: n ".

### line 9
remove: yes
why: the node is already in the title, so " at node" repeated it; the summary for node n now ends with the title only.

### line 3
kind: Wording
after: Title = "Critical alarm: " + @Node;
why: the desk asked for the word alarm in the title: node n now gives "Critical alarm: n" instead of "Critical: n".

### lines 5-7
kind: Branch rewritten
after:
```
elseif (@Severity == 4) {
    Title = "Major: " + @Node;
    Title = Title + " (" + @Manager + ")";
}
```
why: the manager is part of the title now: an event from Collector on node n gives "Major: n (Collector)" instead of "Major: n".

## Left for the owner

## Verdict
Every High finding is corrected; the placeholder text is left to the owner.

## Questions for the owner
Should the Collector check stay?
"""
FIX_EXPECTED = """// sample rules
if (@Severity == 5) {
    Title = "Critical alarm: " + @Node;
}
elseif (@Severity == 4) {
    Title = "Major: " + @Node;
    Title = Title + " (" + @Manager + ")";
}
Summary = Title + " " + @Summary;
Payload = '<param name="title">' + Summary + '</param>' + "&lt;" + 'Test1,Test2';
log("done " + Payload);
"""

# Small variations of each kind of defect: (code, title of the check, hits expected, text expected in the output)
C, U, R, O, UL, T, E, G, P, BR, MX, OR, TW, RP, SF, EM, EA, IX, LP, HD, QY, SC, NC, \
    CT, SM, NE, DB, DC, DF, UR, ST, BD, CM, WB, CP = range(35)
VARIATIONS = [
    # assignment in a condition, written in different ways
    ("if (a = b) { x(); }", C, 1, ""),
    ("if(a=b){x();}", C, 1, ""),
    ("if ( a = b )\n{\n  x();\n}", C, 1, ""),
    ("if (a == 1 && b = 2) { x(); }", C, 1, ""),
    ("if (a == 1 ||\n    b = 2) { x(); }", C, 1, "line 2"),
    ("if (a == 1) { x(); } elseif (b = 2) { y(); }", C, 1, ""),
    ("if (a == 1) { x(); } else if (b = 2) { y(); }", C, 1, ""),
    ("while (n = next()) { x(); }", C, 1, ""),
    ("IF (a = b) { x(); }", C, 1, ""),
    ("ElseIf (a = b) { x(); }", C, 1, ""),
    ("if ((a == 1) && ((b = 2) || c == 3)) { x(); }", C, 1, ""),
    ("if (a = 1) { x(); }\nif (b = 2) { y(); }\nif (c = 3) { z(); }", C, 3, ""),
    ("if (a = 1 && b = 2) { x(); }", C, 1, "2 times on this line"),
    # ... and what must not be reported
    ("if (a == b) { x = 1; }", C, 0, ""),
    ("if (a != b && c <= d && e >= f) { x(); }", C, 0, ""),
    ("if (a === b || a !== c) { x(); }", C, 0, ""),
    ('if (s == "a = b") { x(); }', C, 0, ""),
    ("// if (a = b)\nx();", C, 0, ""),
    ("/* if (a = b) */ x();", C, 0, ""),
    ("for (i = 0; i < n; i++) { x(); }", C, 0, ""),
    ("x = (a == b);", C, 0, ""),
    ("if (f(a) == 1) { y = 2; }", C, 0, ""),
    ('log("if (a = b)");', C, 0, ""),
    # names
    ("total = 1;\nprint(totl);", U, 1, "close to total"),
    ("total = 1;\nprint(Total);", U, 1, "close to total"),
    ("userName = 1;\nprint(usreName);", U, 1, "close to userName"),
    ("userName = 1;\nprint(userNam);", U, 1, "close to userName"),
    ("userName = 1;\nprint(userNamee);", U, 1, "close to userName"),
    ("x = @Node; y = @Node; z = Node;", U, 1, "also written @Node"),
    ("x = $node; y = $node; z = node;", U, 1, "also written $node"),
    ("total = 1;\nprint(total);", U, 0, ""),
    ("lib.start();\nlib.stop();", U, 0, ""),
    ("x = $specific-trap;\nprint(x);", U, 0, "", "trap.rules"),
    ("table SiteLookup = 'a'\n@Site = lookup(@Node, SiteLokup)\n", R, 0, "", "pair.rules"),
    ("table SiteLookup = 'a'\n@Site = lookup(@Node, SiteLokup)\n", U, 1, "SiteLokup", "pair.rules"),
    ("WinStart = now();\nprint('from ' + Winstart);", R, 0, ""),
    ("@Severity = 1;\nx = @Severity;\nSeverity = 2;\nprint(x + @Severity);", R, 1, "also written @Severity"),
    ("name = 'a-b';\nparts = name.split('-');\nprint(parts);", R, 0, ""),
    ("function f(text) { return text.trim(); }\nprint(f('a'));", R, 0, ""),
    ("box.width = 3;\nprint(box.width);", EA, 0, ""),
    ("print(box.width);\nbox = make();", EA, 1, "box"),
    ("function f(a, b) { return a + b; }", U, 0, ""),
    ("a = 1;\nb = 2;\nprint(a);", R, 1, "b"),
    ("a = 1;\nb = 2;\nprint(a + b);", R, 0, ""),
    ("print(@Summary); print(@Summary); print(@Sumary);", O, 1, "@Sumary"),
    ("print(@Summary); print(@Summary); print(@Smumary);", O, 1, "@Smumary"),
    ("print(@Detail1); print(@Detail1); print(@Detail2);", O, 0, ""),
    ("a = row.Address; b = row.Address; c = row.Adress;", O, 1, ".Adress"),
    # a value overwritten at once
    ("count = 1;\ncount = 2;\nprint(count);", T, 1, ""),
    ("count = 1\ncount = 2\nprint(count)", T, 1, ""),
    ("count = 1;\ncount = count + 1;\nprint(count);", T, 0, ""),
    ("count = 1;\nprint(count);\ncount = 2;\nprint(count);", T, 0, ""),
    # markup held in strings
    ('s = "a &lt b"; print(s);', E, 1, ""),
    ('s = "a &amp: b"; print(s);', E, 1, ""),
    ('s = "&#39 x"; print(s);', E, 1, ""),
    ('s = "a &lt; b &amp; c &#39;"; print(s);', E, 0, ""),
    ('s = "page?a=1&b=2&amp=3"; print(s);', E, 0, ""),
    ('s = "<b>x<b>"; print(s);', G, 1, ""),
    ('s = "<td class=\'k\'>x<td>"; print(s);', G, 1, ""),
    ('s = "<p>x"; print(s);', G, 1, ""),
    ('s = "<b>x</b><br/>"; print(s);', G, 0, ""),
    ('s = "<p>"; t = s + "x" + "</p>"; print(t);', G, 0, ""),
    ('s = "<a href=\'" + url + "\'>open</a>"; print(s);', G, 0, ""),
    ('s = "<td class=\'" + cls + "\'>" + v + "<td>"; print(s);', G, 1, ""),
    ('s = "a < b and b > c"; print(s);', G, 0, ""),
    # placeholder text
    ('s = "Test1"; print(s);', P, 1, ""),
    ('s = "TODO later"; print(s);', P, 1, ""),
    ('s = "dummy value"; print(s);', P, 1, ""),
    ('s = "sample@example.com"; print(s);', P, 1, ""),
    ('s = "noc@example.com"; print(s);', P, 1, "example.com"),
    ('s = "see the examples.computed table"; print(s);', P, 0, ""),
    ('s = "latest contest Testing attestation"; print(s);', P, 0, ""),
    ('log("test run");', P, 0, ""),
    # brackets that do not balance
    ("if (a == 1) { x(); ", BR, 1, "never closed"),
    ("if (a == 1) { x(); } }", BR, 1, "closes nothing"),
    ("x = f(a, (b + c);", BR, 1, ""),
    ("x = a[1;", BR, 1, ""),
    ("if (a == 1) {\n  if (b == 2) {\n    x();\n}", BR, 1, ""),
    ("if (a == 1) { x(b[0]); }", BR, 0, ""),
    ('s = "{ ( ["; print(s);', BR, 0, ""),
    ("// {\nx();", BR, 0, ""),
    ("var r = /[(]/;\nuse(r);", BR, 0, "", "pattern.js"),
    ("var r = /a{2/g;\nuse(r);", BR, 0, "", "pattern.js"),
    ("var total = 4; var half = total / 2; var q = half / (3); use(q);", BR, 0, "", "divide.js"),
    # && and || in one group without brackets
    ("if (a == 1 && b == 2 || c == 3) { x(); }", MX, 1, ""),
    ("if (a == 1 and b == 2 or c == 3) { x(); }", MX, 1, ""),
    ("if (a == 1 ||\n    b == 2 && c == 3) { x(); }", MX, 1, ""),
    ("while (a && b || c) { a = next(); }", MX, 1, ""),
    ("if (x && (a == 1 || b == 2 && c == 3)) { y(); }", MX, 1, ""),
    ("if ((a == 1 && b == 2) || c == 3) { x(); }", MX, 0, ""),
    ("if (a == 1 && (b == 2 || c == 3)) { x(); }", MX, 0, ""),
    ("if (a == 1 && b == 2 && c == 3) { x(); }", MX, 0, ""),
    ("if (a == 1 || b == 2 || c == 3) { x(); }", MX, 0, ""),
    ("if (f(a || b) && c) { x(); }", MX, 0, ""),
    # else or else-if that does not follow an if
    ("function f(a) {\n  elseif (a == 2) { x(); }\n}\nf(1);", OR, 1, "line 2"),
    ("while (a < 3) { a = a + 1; } else { x(); }", OR, 1, ""),
    ("x();\nelse { y(); }", OR, 1, ""),
    ("if (a == 1) { x(); } else { y(); }", OR, 0, ""),
    ("if (a == 1) { x(); } elseif (a == 2) { y(); } else { z(); }", OR, 0, ""),
    ("if (a == 1) { x(); }\nelse if (a == 2) { y(); }\nelse { z(); }", OR, 0, ""),
    ("if (a == 1) x(); else y();", OR, 0, ""),
    ("if a == 1:\n    x()\nelse:\n    y()\n", OR, 0, "", "branch.py"),
    # two spellings of one name that differ only by letter case, both in use
    ("openedBy = 'a';\nopenedby = 'b';\nprint(openedBy + openedby);", TW, 1, "openedBy"),
    ("userName = 1;\nUserName = 2;\nprint(userName); print(UserName);", TW, 1, ""),
    ("title = 'a';\nTITLE = '<t>' + title + '</t>';\nprint(TITLE);", TW, 0, ""),
    ("total = 1;\nprint(total);", TW, 0, ""),
    # the same condition twice in one chain
    ("if (a == 1) { x(); } elseif (a == 2) { y(); } elseif (a == 1) { z(); }", RP, 1, "same condition as line 1"),
    ("if (a == 1) { x(); } else if (a == 1) { y(); }", RP, 1, ""),
    ("if (a == 1) {\n  x();\n}\nelseif (b == 2) {\n  y();\n}\nelseif (b == 2) {\n  z();\n}", RP, 1, "line 4"),
    ("if (a == 1) { x(); } elseif (a == 2) { y(); } else { z(); }", RP, 0, ""),
    ("if (a == 1) { x(); }\nif (a == 1) { y(); }", RP, 0, ""),
    # compared with itself, two fixed values, assigned to itself
    ("if (a == a) { x(); }", SF, 1, "compared with itself"),
    ("if (@Node != @Node) { x(); }", SF, 1, ""),
    ("if (1 == 1) { x(); }", SF, 1, "two fixed values"),
    ('if ("a" == "b") { x(); }', SF, 1, ""),
    ("total = total;", SF, 1, "assigned to itself"),
    ("if (a.x == b.x) { y(); }", SF, 0, ""),
    ("if (a == a + 1) { y(); }", SF, 0, ""),
    ("if (row.id == id) { y(); }", SF, 0, ""),
    ("if (id == row.id) { y(); }", SF, 0, ""),
    ("total = total + 1;", SF, 0, ""),
    ("if (x * 2 == 4) { y(); }", SF, 0, ""),
    # a block with nothing in it
    ("if (a == 1) { }", EM, 1, ""),
    ("if (a == 1) { x(); } else { }", EM, 1, ""),
    ("try { x(); } catch (e) { }", EM, 1, ""),
    ("if (a == 1) {\n  // nothing yet\n}", EM, 1, ""),
    ("x = {}; use(x);", EM, 0, ""),
    ("if (a == 1) { x(); }", EM, 0, ""),
    # a name read before the line that first sets it
    ("print(total);\ntotal = 1;", EA, 1, "total"),
    ("total = total + 1;\nprint(total);", EA, 1, "total"),
    ("count += 1;\nprint(count);", EA, 1, "count"),
    ("total = 1;\nprint(total);", EA, 0, ""),
    ("total = 0;\ntotal = total + 1;\nprint(total);", EA, 0, ""),
    ("function f() { print(total); }\ntotal = 1;\nf();", EA, 0, ""),
    ("for (i = 0; i < 3; i++) { print(i); }", EA, 0, ""),
    # the result of a call indexed before its size is checked
    ("rows = fetch(q);\nx = rows[0];\nprint(x);", IX, 1, "rows"),
    ("rows = fetch(q);\nlog(length(rows) + rows[0]);", IX, 1, ""),
    ("parts = name.split('-');\nx = parts[1];\nprint(x);", IX, 1, "parts"),
    ("rows = fetch(q);\nif (rows[0] == 1) { print(1); }", IX, 1, ""),
    ("rows = fetch(q);\nif (length(rows) > 0) { x = rows[0]; print(x); }", IX, 0, ""),
    ("rows = fetch(q);\nif (rows.length > 0) { x = rows[0]; print(x); }", IX, 0, ""),
    ("rows = fetch(q);\nif (rows != null) { x = rows[0]; print(x); }", IX, 0, ""),
    ("rows = fetch(q);\nn = length(rows);\nif (n > 0) { x = rows[0]; print(x); }", IX, 0, ""),
    ("rows = [1, 2];\nx = rows[0];\nprint(x);", IX, 0, ""),
    # a loop whose condition nothing in the loop changes
    ("i = 0;\nwhile (i < 10) { print(i); }", LP, 1, "i"),
    ("i = 0;\nwhile (i < n) { x = rows[i]; print(x); }", LP, 1, ""),
    ("i = 0;\nwhile (i < 10) { print(i); i = i + 1; }", LP, 0, ""),
    ("i = 0;\nwhile (i < 10) { i++; }", LP, 0, ""),
    ("i = 0;\nwhile (i < 10) { i += 2; }", LP, 0, ""),
    ("while (i < n) { if (done(i)) { break; } }", LP, 0, ""),
    ("while (true) { x(); }", LP, 0, ""),
    ("while (hasNext()) { x(); }", LP, 0, ""),
    ("i = 0;\nwhile (i < n) { advance(i); }", LP, 0, ""),
    # an error handler that only logs
    ("try { x(); } catch (e) { log(e); }", HD, 1, ""),
    ("try { x(); } catch (e) { console.log(e); logger.error(e); }", HD, 1, ""),
    ('Handle NullPointerException { log("x"); }', HD, 1, ""),
    ('Handle java.lang.Exception {\n  Log("failed");\n}', HD, 1, ""),
    ("try { x(); } catch (e) { log(e); failed = 1; }", HD, 0, ""),
    ("try { x(); } catch (e) { throw e; }", HD, 0, ""),
    ("try { x(); } catch (e) { }", HD, 0, ""),
    # a query built by joining text with a value
    ('q = "select * from t where id = " + id; run(q);', QY, 1, ""),
    ('q = "SELECT name FROM t WHERE n = \'" + name + "\'"; run(q);', QY, 1, ""),
    ('q = "update t set a = 1 where id = " + id; run(q);', QY, 1, ""),
    ('q = "delete from t where id = " + id; run(q);', QY, 1, ""),
    ('q = "insert into t values (" + v + ")"; run(q);', QY, 1, ""),
    ('q = "select * from t where id = 1"; run(q);', QY, 0, ""),
    ('f = "NodeName = \'" + node + "\'"; rows = find("T", f); print(rows);', QY, 1, ""),
    ('f = "Total = " + n; print(f);', QY, 0, ""),
    ('msg = "selected " + n; print(msg);', QY, 0, ""),
    ('log("select * from t where id = " + id);', QY, 0, ""),
    # an environment name, an address or a credential in a string
    ('ds = "ORDERS_UAT"; use(ds);', SC, 1, "UAT"),
    ('host = "reports-uat.internal"; use(host);', SC, 1, "uat"),
    ('label = "Situation report"; use(label);', SC, 0, ""),
    ('url = "http://10.1.2.3:8080/api"; use(url);', SC, 1, ""),
    ('h = "10.20.30.40"; use(h);', SC, 1, ""),
    ('c = "user=app;password=Secret123"; use(c);', SC, 1, "password"),
    ('h = "localhost"; use(h);', SC, 1, ""),
    ('oid = ".1.3.6.1.4.1.9.9.41"; use(oid);', SC, 0, ""),
    ('v = "version 1.2.3"; use(v);', SC, 0, ""),
    ('d = "DEVICE SITUATION"; use(d);', SC, 0, ""),
    ('log("connecting to 10.20.30.40");', SC, 0, ""),
    # a function that is defined and never called
    ("function used() { return 1; }\nfunction unused() { return 2; }\nx = used(); print(x);", NC, 1, "unused"),
    ("def helper():\n    return 1\n", NC, 1, "helper", "helper.py"),
    ("function a() { return 1; }\nx = a(); print(x);", NC, 0, ""),
    ("function cb() { return 1; }\nregister(cb);", NC, 0, ""),
    # comparisons that contradict each other
    ("if (a == 1 && a == 2) { x(); }", CT, 1, "cannot equal"),
    ("if (@Domain == 14000 && @Agent == 'x' && @Domain == 25000) { x(); }", CT, 1, "@Domain"),
    ("if (a != 1 || a != 2) { x(); }", CT, 1, "always differs"),
    ("if (s == 'a' and s == 'b') { x(); }", CT, 1, ""),
    ("if (b == 3 && (a == 1 && a == 2)) { x(); }", CT, 1, ""),
    ("if (a == 1 || a == 2) { x(); }", CT, 0, ""),
    ("if (a != 1 && a != 2) { x(); }", CT, 0, ""),
    ("if (a == 1 && b == 2) { x(); }", CT, 0, ""),
    ("if (a == 1 && a == 1) { x(); }", CT, 0, ""),
    ("if ((a == 1 && b == 2) || (a == 2 && b == 1)) { x(); }", CT, 0, ""),
    # a ; straight after a condition
    ("if (a == 1);\n{ x(); }", SM, 1, ""),
    ("while (i < 3);\n{ i = i + 1; }", SM, 1, ""),
    ("if (a == 1) { x(); }", SM, 0, ""),
    ("do { i = i + 1; } while (i < 3);", SM, 0, ""),
    ("if (a == 1) x();", SM, 0, ""),
    # a comparison whose result is not used
    ("total == 5;\nprint(total);", NE, 1, "total"),
    ("@Severity == 4;", NE, 1, ""),
    ("if (total == 5) { x(); }", NE, 0, ""),
    ("ok = total == 5;\nprint(ok);", NE, 0, ""),
    ("assert total == 5;", NE, 0, ""),
    ("return total == 5;", NE, 0, ""),
    # branches with the same statements
    ("if (a == 1) { level = 'low'; } elseif (a == 2) { level = 'mid'; } else { level = 'low'; }", DB, 1, "line 1"),
    ("if (a == 1) {\n  level = 'low';\n} else {\n  level = 'low';\n}", DB, 1, ""),
    ("if (a == 1) { level = 'low'; } elseif (a == 2) { level = 'low'; }", DB, 1, ""),
    ("if (a == 1) { level = 'low'; } else { level = 'high'; }", DB, 0, ""),
    ("if (a == 1) { x(); } else { x(); }", DB, 0, ""),
    # the same label twice in one switch
    ('switch (a) { case "1": x(); case "2": y(); case "1": z(); }', DC, 1, "same label as line 1"),
    ("switch (a)\n{\n  case 1:\n    x()\n  case 2:\n    y()\n  case 1:\n    z()\n}", DC, 1, "line 3"),
    ('switch (a) { case "1": x(); case "2": y(); default: z(); }', DC, 0, ""),
    ('switch (a) { case "1": switch (b) { case "1": x(); } }', DC, 0, ""),
    # a function defined more than once
    ("function f() { return 1; }\nfunction f() { return 2; }\nprint(f());", DF, 1, "also defined"),
    ("function f() { return 1; }\nfunction g() { return 2; }\nprint(f() + g());", DF, 0, ""),
    # code after a statement that leaves the block
    ("function f() {\n  return 1;\n  cleanup();\n}\nprint(f());", UR, 1, "line 3"),
    ("while (a) {\n  break;\n  a = next();\n}", UR, 1, ""),
    ("function f(a) {\n  if (a) { return 1; }\n  return 2;\n}\nprint(f(1));", UR, 0, ""),
    ("function f(a) {\n  if (a) return 1;\n  return 2;\n}\nprint(f(1));", UR, 0, ""),
    ('switch (a) { case "1": x(); break; case "2": y(); break; default: z(); }', UR, 0, ""),
    # a string that is not closed on its line
    ('s = "open text;\nprint(s);', ST, 1, ""),
    ("s = 'open text;\nprint(s);", ST, 1, ""),
    ('s = "closed"; t = \'also closed\'; print(s + t);', ST, 0, ""),
    ("// don't count this\nx();", ST, 0, ""),
    ('s = "a \\"quoted\\" word"; print(s);', ST, 0, ""),
    ("name = 'O''Brien'\nprint(name)", ST, 0, "", "names.sql"),
    # an index compared with <= to a size
    ("i = 0;\nwhile (i <= length(rows)) { use(rows[i]); i = i + 1; }", BD, 1, ""),
    ("for (i = 0; i <= rows.length; i++) { use(rows[i]); }", BD, 1, ""),
    ("i = 0;\nwhile (i < length(rows)) { use(rows[i]); i = i + 1; }", BD, 0, ""),
    ("if (count <= limit) { x(); }", BD, 0, ""),
    # a command or code run with text joined to a value
    ('system("rm -rf " + folder);', CM, 1, ""),
    ('result = eval("total + " + userText); print(result);', CM, 1, ""),
    ('system("uptime");', CM, 0, ""),
    ('m = re.exec(text); print(m);', CM, 0, ""),
    ('FILE=/tmp/a\neval "rm -f " $FILE\n', CM, 1, "", "clean.sh"),
    ('eval "$(ssh-agent)"\n', CM, 1, "", "agent.sh"),
    # shell scripts: a variable is set as NAME=value and read as $NAME, also inside a quoted string
    ('TARGET=prod\necho "deploying to $TARGT"\n', U, 1, "$TARGT", "vars.sh"),
    ('TARGET=prod\necho "deploying to $TARGET in $HOME"\n', U, 0, "", "vars.sh"),
    ('TARGET=prod\necho "deploying to ${TARGET}"\n', R, 0, "", "vars.sh"),
    ('for f in a b; do echo "$f"; done\nmkdir -p /opt/app/logs\n', U, 0, "", "loop.sh"),
    # a variable used only inside a string is read there
    ('<?php\n$name = "x";\necho "hello $name";\n', R, 0, "", "hello.php"),
    ('name = "x"\nputs "hello #{name}"\n', R, 0, "", "hello.rb"),
    ('const name = "x";\nconsole.log(`hello ${name}`);\n', R, 0, "", "hello.js"),
    # a credential written into the code
    ('dbPassword = "S3cretValue"; connect(dbPassword);', SC, 1, "a value for dbPassword"),
    ('apiKey = "abc123def"; call(apiKey);', SC, 1, ""),
    ('dbPassword = getSecret("db"); connect(dbPassword);', SC, 0, ""),
    ('token = next(); use(token);', SC, 0, ""),
    # data given to the code (names of a sort that is never assigned) is assigned
    ("x = @A; y = @B; z = @C;\n@D = 1;\nprint(x + y + z);", WB, 1, "@D — assigned on line 2"),
    ("x = @A; y = @B; z = @C;\n@D = 1;\n@D = @D + 1;\nprint(x + y + z);", WB, 1, "assigned on lines 2, 3"),
    ("x = @A; y = @B; z = @C;\nprint(x + y + z);", WB, 0, ""),
    # a replace call limited to a count
    ('s = text.replace("&", "&amp;", 2); print(s);', CP, 1, "limited to 2 replacements"),
    ('s = text.replace("&", "&amp;"); print(s);', CP, 0, ""),
    ('s = text.replace("&", "&amp;", 1); print(s);', CP, 0, ""),
]

passed, failed, known_faults = 0, [], []
CWD = None                                   # the empty working folder every command runs in


def check(name, condition, detail="", known=False):
    """Count a test. A known fault is a fault in a script that is still to be corrected: it is
    reported apart, and keeps the suite failing until the script is corrected."""
    global passed
    if condition:
        passed += 1
    elif known:
        known_faults.append("%s %s" % (name, detail))
    else:
        failed.append("%s %s" % (name, detail))


def run(script, *args, cwd=None):
    """Run one script as a command, in the empty working folder unless another is given."""
    r = subprocess.run([sys.executable, "-B", str(SCRIPTS / script)] + [str(a) for a in args],
                       capture_output=True, text=True, cwd=str(cwd or CWD))
    return r.returncode, r.stdout, r.stderr


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def notes_for(report):
    """The notes file that belongs to a report, as the scripts name it."""
    report = Path(report)
    return report.with_name(report.stem + ".notes.md")


def counts(out):
    found = {}
    for title in TITLES:
        m = re.search(r"^\s*(\d+)\s+%s\s*$" % re.escape(title), out, re.M)
        found[title] = int(m.group(1)) if m else None
    return found


def section(out, title):
    """The lines printed under one heading of the scan."""
    m = re.search(r"^%s \(\d+\)\n(.*?)(?=^\S|\Z)" % re.escape(title), out, re.M | re.S)
    return m.group(1) if m else ""


def table_rows(text, first="ID"):
    """The rows of the tables of a report whose header starts with the given cell, each as
    {column name: cell}, read by the names in the header row."""
    out, cols = [], None
    for line in text.split("\n"):
        if not line.startswith("|"):
            cols = None
            continue
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", line)[1:-1]]
        if cells and cells[0] == first:
            cols = cells
        elif cols and cells and re.match(r"^[A-Z]-\d+$", cells[0]) and len(cells) == len(cols):
            out.append(dict(zip(cols, cells)))
    return out


def ok_run(code, out, err):
    """A command ended normally: a result (0 or 3), no traceback, no script reported as failed."""
    return code in (0, 3) and "Traceback" not in err and not re.search(r"The script \S+ failed", out)


def main():
    global CWD
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        CWD = tmp / "cwd"
        CWD.mkdir()
        samples = tmp / "samples"
        for name, text in SAMPLES.items():
            write(samples / name, text)

        # ================================================================ the scan
        def scan(name):
            code, out, err = run("scan_code.py", samples / name)
            check("%s: runs" % name, code == 0 and not err, err[-300:])
            return counts(out), out

        cond, unset = TITLES[0], TITLES[1]

        c, out = scan("defects.js")
        check("js: assignment in a condition", c[cond] == 1 and "line 5" in section(out, cond), c)
        check("js: misspelt name", "taxrate" in section(out, unset) and "close to taxRate" in out)
        check("js: only the misspelt name is unset", c[unset] == 1, section(out, unset))
        check("js: value overwritten at once", c[TITLES[T]] == 1)
        check("js: entity", c[TITLES[E]] == 1)
        check("js: tag", c[TITLES[G]] == 1)
        check("js: placeholder", c[TITLES[P]] == 1)

        c, out = scan("clean.js")
        check("clean js: nothing reported", sum(v or 0 for v in c.values()) == 0, c)

        c, out = scan("defects.py")
        check("py: no assignment in a condition", c[cond] == 0, section(out, cond))
        check("py: misspelt name", "taxrate" in section(out, unset), section(out, unset))
        check("py: // is not a comment", c[unset] == 2 and "bonus" in section(out, unset), section(out, unset))
        check("py: unused value", "unused" in section(out, TITLES[R]))
        check("py: placeholder", c[TITLES[P]] == 1)

        c, out = scan("Defects.java")
        check("java: assignment in a condition", c[cond] == 1 and "line 7" in section(out, cond), c)
        check("java: misspelt name only", c[unset] == 1 and "taxrate" in section(out, unset), section(out, unset))
        check("java: entity", c[TITLES[E]] == 1)

        c, out = scan("defects.php")
        check("php: assignment in a condition", c[cond] == 1 and "line 7" in section(out, cond), c)
        check("php: misspelt name only", c[unset] == 1 and "$taxrate" in section(out, unset), section(out, unset))

        c, out = scan("defects.c")
        check("c: assignment in a condition, for loop left alone",
              c[cond] == 1 and "line 7" in section(out, cond), section(out, cond))
        check("c: undeclared name only", c[unset] == 1 and "offset" in section(out, unset), section(out, unset))

        for name in ("deploy.sh", "report.sql"):
            c, out = scan(name)
            check("%s: = compares, check 1 not applied" % name,
                  c[cond] == 0 and "not applied" in out, out[:300])

        c, out = scan("rules.src")
        lines = section(out, cond)
        check("rules: both conditions found", c[cond] == 2 and "line 2" in lines and "line 5" in lines, lines)
        check("rules: misspelt name", "sumary" in section(out, unset))
        check("rules: missing prefix", "also written @Node" in section(out, unset), section(out, unset))
        check("rules: entity, tag, placeholder",
              (c[TITLES[E]], c[TITLES[G]], c[TITLES[P]]) == (1, 1, 1), c)
        check("scan: every known check has a count line", all(v is not None for v in c.values()),
              [t for t, v in c.items() if v is None])

        # small variations of each kind of defect
        for n, case in enumerate(VARIATIONS, 1):
            text, kind, expected, must_show = case[:4]
            sample = samples / (case[4] if len(case) > 4 else "variation.x")
            sample.write_text(text + "\n")
            code, out, err = run("scan_code.py", sample)
            sample.unlink()
            got = counts(out)[TITLES[kind]]
            check("variation %d: %s -> %s %d" % (n, text.replace("\n", " / "), TITLES[kind], expected),
                  code == 0 and not err and got == expected and must_show in out, "got %s\n%s" % (got, out[-400:]))

        # the same input gives the same output
        again = [run("scan_code.py", samples / "rules.src")[1] for _ in range(3)]
        check("same output every run", len(set(again)) == 1)

        # input that is not code, or broken
        (samples / "blob.bin").write_bytes(b"\0\1\2if (a = 1)\0")
        (samples / "empty.js").write_text("")
        (samples / "broken.js").write_text("if (a = (b\n\"never closed\n/* never closed\n")
        for name in ("blob.bin", "empty.js", "broken.js"):
            code, out, err = run("scan_code.py", samples / name)
            check("%s: no crash" % name, code == 0 and not err, err[-300:])
        check("binary file left out", "left out" in run("scan_code.py", samples / "blob.bin")[1])
        code, out, err = run("scan_code.py", samples)
        check("folder of mixed languages: no crash", code == 0 and not err, err[-300:])

        # the one way every script scans: scan_code.run gives the scan and the files it read
        r = subprocess.run([sys.executable, "-B", "-c", "import sys; sys.path.insert(0, %r); import scan_code; "
                            "scan, files = scan_code.run([%r]); print(len(files), len(scan.hits['cond']), scan.docs)"
                            % (str(SCRIPTS), str(samples / "rules.src"))], capture_output=True, text=True, cwd=str(CWD))
        check("scan_code.run: gives the scan and the files, and finds no document where there is none",
              r.returncode == 0 and r.stdout.strip() == "1 2 []", r.stdout + r.stderr)

        # ================================================================ check_report
        fixtures = tmp / "fixtures"
        write(fixtures / "full.md", "| Line | Code |\n|---|---|\n| 2 | cond |\n| 5 | cond |\n"
                                    "| 8 | sumary, Summary |\n| 9 | Node is missing its prefix |\n"
                                    "| 10 | Payload: tag, entity, placeholder |\n")
        write(fixtures / "partial.md", "| Line | Code |\n|---|---|\n| 2 | cond |\n| 8 | sumary |\n")
        code, out, err = run("check_report.py", fixtures / "full.md", samples / "rules.src")
        check("check_report: complete report accepted", code == 0 and "Result: complete" in out, out + err)
        code, out, err = run("check_report.py", fixtures / "partial.md", samples / "rules.src")
        check("check_report: incomplete report refused", code == 1 and "Result: not complete" in out, out + err)
        check("check_report: names the missing line", "line 5" in out, out)

        # ================================================================ review: the first run
        # The report is written by the script from the scan and from the notes next to it.
        rv = tmp / "review"
        write(rv / "rules.src", SAMPLES["rules.src"])
        report = rv / "reports" / "register.md"
        notes = notes_for(report)
        code, out, err = run("run.py", "review", rv / "rules.src", "--out", report)
        text = report.read_text() if report.exists() else ""
        skel = notes.read_text() if notes.exists() else ""
        check("review: first run ends normally and writes the report",
              ok_run(code, out, err) and not err and "| S-01 |" in text, out + err)
        check("review: first run writes the notes and stops at the gate",
              notes.exists() and "Gate: not passed yet" in out and "expected on the first run" in out
              and "written now" in out, out)
        check("review: the state of each part is printed",
              all(re.search(r"%s:\s+(TO DO|done)" % x, out) for x in
                  ("Decisions", "Findings from reading", "Coverage of the intent", "Lines read"))
              and out.count("TO DO") == 3 and "no document came with the code: not needed" in out, out)
        rows = table_rows(text)
        by_id = {r["ID"]: r for r in rows}
        check("review: every row has the same number of cells",
              len({l.count(" | ") for l in text.split("\n") if l.startswith("| S-")}) == 1
              and "&& and \\|\\| mixed" in text, text[-900:])
        check("review: the report has the tables and columns of its form",
              all(x in text for x in ("| Where it lands |", "| Fix: the line after the fix |", "## Findings from reading",
                                      "## Scan hits that are not defects", "## Checks performed", "## Coverage of the code",
                                      "## Coverage of the intent", "## Not checked", "## Questions for the owner of the code"))
              and text.startswith("# Review — rules.src"), text[:800])
        check("review: corrected line in the report",
              by_id.get("S-01", {}).get("Fix: the line after the fix") == "`if (@Severity == 5) {`", str(by_id.get("S-01")))
        check("review: missing prefix settled by the script",
              any(r["Fix: the line after the fix"] == "`Summary = Summary + \" at \" + @Node;`" and r["Decision"] == "Finding"
                  for r in rows), text)
        check("review: a placeholder that is the whole text goes to the owner, with its question",
              any(r["Kind"].startswith("Placeholder text in strings") and r["Decision"] == "Finding, to be confirmed by the owner"
                  for r in rows) and "(line 10): The text is only the placeholder Test1, Test2. What is the real value?" in text,
              text[-600:])
        open_rows = [r for r in rows if r["Decision"] == "To judge"]
        check("review: the misspelt name is left to judge, and where it lands is said",
              len(open_rows) == 1 and open_rows[0]["Line"] == "8" and open_rows[0]["Where it lands"] == "sets `Summary`, which goes into `Payload` (line 10)"
              and open_rows[0]["Kind"].startswith("Name read, never assigned: sumary"), str(open_rows))
        open_id = open_rows[0]["ID"] if open_rows else "S-03"
        check("review: the notes skeleton lists the row to decide with its code and question",
              "## Decisions" in skel and "- %s, line 8 — Name read, never assigned: sumary" % open_id in skel
              and ">     8  Summary = Title + \" \" + sumary;" in skel and "Decision: ?" in skel
              and "to answer: Does the platform, the caller or another file set this name?" in skel, skel[:1500])
        check("review: the notes skeleton has the form of each part",
              all(x in skel for x in ("## Findings from reading", "### line 120", "## Coverage of the intent", "## Effect",
                                      "## Lines read", "## Questions for the owner", "## Not checked"))
              and "run.py review" in skel, skel)
        check("review: the skeleton says where a name is set and where it is read, apart",
              "sumary: never set; read on line(s) 8" in skel and "Summary: set on line(s) 8, 9; read on line(s) 9, 10" in skel,
              [l for l in skel.split("\n") if "ummary:" in l])
        code, out, err = run("check_report.py", report, rv / "rules.src")
        check("review: the first report accounts for every place the scan points at",
              "Missing: 0." in out and "Rows still marked \"To judge\": 1" in out, out)
        code, out, err = run("run.py", "review", rv / "rules.src", "--out", report)
        check("review: a later run with empty notes is not passed, and the notes are kept",
              code == 3 and "Gate: not passed yet" in out and "expected on the first run" not in out
              and notes.read_text() == skel, out + err)

        # ---- decisions and findings from reading, with mistakes the script must report
        write(notes, """# Notes for the review register.md

## Decisions
- %s, line 8 — Name read, never assigned: sumary
  Decision: not a defect: the collector sets sumary before the rules run, as its manual says
S-99: finding
S-01: not a defect: the single = is meant here

## Findings from reading
### line 3
severity: High
code: Title = "Critical: "
what: the title holds the node only, so two alarms of one node share a title
fix: add the alarm key to the title
confidence: proven from the code

### line 6
severity: Medium
code: nothing like this is on the line
what: a block whose quoted words are not on the cited line
fix: none
confidence: none

## Lines read
1-11

## Verdict
The rules file has two assignments in conditions and a misspelt name; it is not ready to deploy until they are corrected.

## Questions for the owner
Is the Collector manager name fixed, or does it vary by site?

## Not checked
The lookup tables were not available.
""" % open_id)
        code, out, err = run("run.py", "review", rv / "rules.src", "--out", report)
        text = report.read_text()
        rows = table_rows(text)
        check("review: mistakes in the notes are listed and keep the gate closed",
              code == 3 and "To correct in the notes:" in out and "Gate: not passed yet" in out, out + err)
        check("review: an unknown ID is reported", "S-99 (line 6 of the notes): the report has no row with this ID" in out, out)
        check("review: a decision that contradicts what the scan settled is reported", "S-01 is settled by the scan (finding)" in out, out)
        check("review: a reading block whose words are not on its line is refused",
              "the finding for line 6" in out and "are not on line 6" in out and not any(r["ID"] == "R-02" for r in rows), out)
        check("review: a row that is not a defect moves to its table, with its reason and ID",
              not any(r["ID"] == open_id for r in rows)
              and "| 8 | the collector sets sumary before the rules run, as its manual says (%s, decided by the reviewer) |" % open_id
              in text, text)
        r01 = next((r for r in rows if r["ID"] == "R-01"), None)
        check("review: a reading block on the right line is a row, with the line quoted and where it lands",
              r01 is not None and r01["Line"] == "3" and r01["Code (quoted)"] == "`Title = \"Critical: \" + @Node;`"
              and r01["Where it lands"] == "sets `Title`, which goes into `Summary` (line 8) and from there into `Payload`; "
                                           "inside `if (@Severity = 5)` (line 2)" and r01["Severity"] == "High"
              and r01["Decision"] == "Finding" and r01["Kind"] == "Found by reading", str(r01))
        check("review: verdict, lines read, question and not checked are in the report",
              "it is not ready to deploy" in text and "| 1-11 | 11 |" in text
              and "2. Is the Collector manager name fixed, or does it vary by site?" in text
              and "- The lookup tables were not available." in text, text[-1200:])
        code, out, err = run("check_report.py", report, rv / "rules.src")
        check("review: the report with decisions accounts for every place the scan points at",
              "Missing: 0." in out and "Result: complete" in out, out)

        # ---- the notes corrected: the gate passes
        write(notes, """# Notes for the review register.md

## Decisions
- %s, line 8 — Name read, never assigned: sumary
  Decision: not a defect: the collector sets sumary before the rules run, as its manual says

## Findings from reading
### line 3
severity: High
code: Title = "Critical: "
what: the title holds the node only, so two alarms of one node share a title
fix: add the alarm key to the title
confidence: proven from the code

## Lines read
1-11

## Verdict
The rules file has two assignments in conditions and a misspelt name; it is not ready to deploy until they are corrected.
""" % open_id)
        code, out, err = run("run.py", "review", rv / "rules.src", "--out", report)
        text = report.read_text()
        check("review: the gate passes once the notes are complete and correct",
              code == 0 and "Gate: passed" in out and "To correct" not in out, out + err)
        check("review: the counts follow the decisions",
              "1 are explained as not defects, and 0 still need a decision. Reading the code added 1 finding(s)." in text
              and "The rules file has two assignments" in text, text[:900])
        code, out, err = run("run.py", "check", report, rv / "rules.src")
        check("review: the check of the finished report passes", code == 0 and "Gate: passed" in out, out + err)

        # ================================================================ review: the words of a decision
        wr = tmp / "wr"
        write(wr / "rules.src", SAMPLES["rules.src"])
        rep = wr / "r.md"
        code, out, err = run("write_register.py", wr / "rules.src", "--out", rep)
        check("write_register: the first run exits 0 and writes the notes",
              code == 0 and notes_for(rep).exists() and "Gate: not passed yet" in out, out + err)
        code, out, err = run("write_register.py", wr / "rules.src", "--out", rep)
        check("write_register: a later run that is still incomplete exits 3", code == 3 and "Gate: not passed yet" in out,
              out + err)
        for word, message in (("maybe", "the decision is not understood: \"maybe\""),
                              ("not a defect: ok", "\"not a defect\" needs its reason after a colon"),
                              ("owner: why?", "\"owner\" needs the question after a colon")):
            write(notes_for(rep), "## Decisions\n- S-03, line 8\n  Decision: %s\n## Findings from reading\nnone\n" % word)
            code, out, err = run("write_register.py", wr / "rules.src", "--out", rep)
            check("write_register: the decision \"%s\" is reported and the row stays open" % word,
                  code == 3 and message in out and "still open: S-03" in out, out + err)
        write(notes_for(rep), "## Decisions\nS-03: owner: Does the collector set sumary before these rules run?\n"
                              "## Findings from reading\nnone\n")
        code, out, err = run("write_register.py", wr / "rules.src", "--out", rep)
        text = rep.read_text()
        rows = {r["ID"]: r for r in table_rows(text)}
        check("write_register: \"none\" under findings from reading counts as done; the lines read are still to do",
              code == 3 and re.search(r"Decisions:\s+done", out) and re.search(r"Findings from reading:\s+done\s+none found", out)
              and re.search(r"Lines read:\s+TO DO", out) and "None found by reading." in text, out)
        check("write_register: an owner decision moves the row to the owner, with its question in the report",
              rows.get("S-03", {}).get("Decision") == "Finding, to be confirmed by the owner"
              and rows.get("S-03", {}).get("Severity") == "High"
              and "1. S-03 (line 8): Does the collector set sumary before these rules run?" in text, str(rows.get("S-03")))
        with open(notes_for(rep), "a") as fh:
            fh.write("## Lines read\n1-11\n")
        code, out, err = run("write_register.py", wr / "rules.src", "--out", rep)
        check("write_register: the verdict is written by the script, from the tables; the gate does not wait for one",
              code == 0 and re.search(r"Lines read:\s+done", out) and "Gate: passed" in out
              and "Findings by severity: High" in rep.read_text() and "Nothing was run" in rep.read_text(), out)
        with open(notes_for(rep), "a") as fh:
            fh.write("## Verdict\nOne name is for the owner to confirm; the rest is corrected by the script.\n")
        code, out, err = run("write_register.py", wr / "rules.src", "--out", rep)
        check("write_register: the gate passes when decisions, findings from reading, lines read and verdict are there",
              code == 0 and "Gate: passed" in out, out + err)
        code, out, err = run("run.py", "review", wr / "rules.src", "--out", rep)
        check("run.py review: exit code 0 when the gate passes", code == 0 and "Gate: passed" in out, out + err)
        code, out, err = run("check_report.py", rep, wr / "rules.src")
        check("write_register: the finished report accounts for every place the scan points at", "Missing: 0." in out, out)

        # a file at --out that is not a review report is not replaced
        own = tmp / "own"
        write(own / "rules.src", SAMPLES["rules.src"])
        write(own / "own.md", "my own notes\n")
        code, out, err = run("write_register.py", own / "rules.src", "--out", own / "own.md")
        check("write_register: a file that is not a review report is not replaced",
              code not in (0, 3) and "is not a review report" in out + err and "Traceback" not in err
              and (own / "own.md").read_text() == "my own notes\n", out + err)

        # ================================================================ review: a folder of files
        many = tmp / "many"
        write(many / "one.js", SPLIT_A)
        write(many / "two.js", SPLIT_B)
        rep = many / "reports" / "register.md"
        code, out, err = run("write_register.py", many, "--out", rep)
        rows = table_rows(rep.read_text())
        check("review of a folder: rows name their file",
              code == 0 and rows and all(re.match(r"^(one|two)\.js: \d", r["Line"]) for r in rows), str([r["Line"] for r in rows]))
        block = "severity: Low\ncode: rowCount > 0\nwhat: the count is never set in this file\nfix: pass it in\nconfidence: needs a test\n"
        write(notes_for(rep), "## Decisions\n## Findings from reading\n### line 4\n" + block)
        code, out, err = run("write_register.py", many, "--out", rep)
        check("review of a folder: a reading block without its file is refused", "say which file" in out, out)
        write(notes_for(rep), "## Decisions\n## Findings from reading\n### two.js: 4\n" + block)
        code, out, err = run("write_register.py", many, "--out", rep)
        rows = table_rows(rep.read_text())
        check("review of a folder: a reading block with its file is read, and joins the scan row of its line",
              "restate a scan row and were added to it (line two.js: 4" in out.replace("line 4", "line two.js: 4")
              and "say which file" not in out and not any(r["ID"].startswith("R-") for r in rows), out)

        # ================================================================ review: a list of names next to the code
        dc = tmp / "doc"
        write(dc / "fields.src", FIELDS_CODE)
        write(dc / "fields.md", FIELDS_DOC)
        rep = dc / "register.md"
        code, out, err = run("write_register.py", dc / "fields.src", "--out", rep)
        text = rep.read_text()
        rows = table_rows(text)
        check("document: the list of names is read and said",
              code == 0 and "Names checked against the 7 names listed in" in out and "(lines 4-10)" in out, out + err)
        check("document: a name used once that the list holds is cleared by the scan",
              "| 6 | Mode is in the list of names in fields.md, line 10. (S-01, settled by the scan) |" in text
              and "Name used once, close to another name: @Mode" in text, text)
        unl = next((r for r in rows if r["Kind"].startswith("Name not in the list of names: @Severty")), None)
        check("document: an unlisted misspelt name is a finding with the corrected line",
              unl is not None and unl["Decision"] == "Finding" and unl["Severity"] == "High"
              and unl["Fix: the line after the fix"] == "`@Identifier = @Node + @Severity;`"
              and unl["Confidence"].startswith("Proven from the list of names in fields.md"), str(unl))
        check("document: a query that joins a number is cleared by the scan",
              "cannot hold a quote: Severity is listed as Integer in fields.md, line 4" in text and "settled by the scan" in text,
              text)
        check("document: the checks performed name the list",
              "| Names checked against a list | fields.md, lines 4-10 | 7 names listed |" in text, text)
        check("document: nothing is left to decide, and the coverage of the intent is to do",
              "None: the scan settled every row." in notes_for(rep).read_text()
              and re.search(r"Coverage of the intent:\s+TO DO", out) and "one line for each requirement of fields.md" in out
              and "fields.md" in notes_for(rep).read_text(), out)
        wb = next((r for r in rows if r["Kind"].startswith("Data from outside the code is changed: @Identifier")), None)
        check("document: a row about outside data changed on a line that also holds a misspelt name keeps its own text "
              "and goes to the owner",
              wb is not None and wb["What it does"].startswith("The code assigns a value of the data it was given")
              and wb["Decision"] == "Finding, to be confirmed by the owner" and wb["Severity"] == "Medium", str(wb))
        code, out, err = run("check_report.py", rep, dc / "fields.src")
        check("document: the report accounts for every place the scan points at", "Missing: 0." in out, out)
        write(notes_for(rep), "## Decisions\n## Findings from reading\nnone\n## Lines read\n1-10\n## Verdict\n"
                              "The rules read one field that the list does not hold; the other fields are in the list.\n")
        code, out, err = run("write_register.py", dc / "fields.src", "--out", rep)
        check("document: without the coverage of the intent the gate stays closed",
              code == 3 and re.search(r"Coverage of the intent:\s+TO DO", out) and "Gate: not passed yet" in out, out)
        with open(notes_for(rep), "a") as fh:
            fh.write("## Coverage of the intent\nEvery field used exists\n")
        code, out, err = run("write_register.py", dc / "fields.src", "--out", rep)
        check("document: a coverage line without \" | \" is reported",
              code == 3 and "has no \" | \" between the requirement and what was found" in out, out)
        write(notes_for(rep), notes_for(rep).read_text().replace(
            "Every field used exists\n", "Every field used exists | one misspelt field, corrected; the others are listed\n"))
        code, out, err = run("write_register.py", dc / "fields.src", "--out", rep)
        text = rep.read_text()
        check("document: the gate passes with the coverage of the intent",
              code == 0 and "Gate: passed" in out
              and "| Every field used exists | one misspelt field, corrected; the others are listed |" in text, out)
        code, out, err = run("run.py", "check", rep, dc / "fields.src", "--intent", dc / "fields.md")
        check("document: the check of the report with the intent passes",
              code == 0 and "Gate: passed" in out and "Coverage of the intent: 1 row(s)" in out, out + err)

        # ================================================================ fix
        # The copy and the change log are written by the script from the scan, the notes and the review.
        fx = tmp / "fix"
        write(fx / "rules.src", SAMPLES["rules.src"])
        reg = fx / "register.md"
        write(notes_for(reg), "## Decisions\nS-03: finding\n## Findings from reading\nnone\n## Lines read\n1-11\n"
                              "## Verdict\nTwo assignments in conditions and one misspelt name make the rules unsafe to deploy.\n")
        code, out, err = run("write_register.py", fx / "rules.src", "--out", reg)
        check("register for the fix: the short form of a decision is read and the gate passes",
              code == 0 and "Gate: passed" in out and "| S-03 | High | 8 |" in reg.read_text(), out + err)
        fixed_dir, log = fx / "out", fx / "log.md"
        fix_args = ("run.py", "fix", fx / "rules.src", "--out", fixed_dir, "--log", log, "--register", reg)
        original = (fx / "rules.src").read_text()
        code, out, err = run(*fix_args)
        fixed = (fixed_dir / "rules.src").read_text() if (fixed_dir / "rules.src").exists() else ""
        logtext = log.read_text() if log.exists() else ""
        fnotes = notes_for(log).read_text() if notes_for(log).exists() else ""
        check("fix: first run ends normally and writes copy, log and notes",
              code == 0 and not err and "expected on the first run" in out and fixed and logtext and fnotes, out + err)
        check("fix: original untouched", (fx / "rules.src").read_text() == original)
        check("fix: comparisons corrected", "if (@Severity == 5) {" in fixed and "@Manager == 'Collector'" in fixed, fixed)
        check("fix: prefix, entity and tag corrected", '" at " + @Node;' in fixed and '"&lt;"' in fixed
              and "+ '</param>' +" in fixed, fixed)
        check("fix: what needs a decision is left alone", "sumary" in fixed and "Test1,Test2" in fixed)
        check("fix: same number of lines", fixed.count("\n") == original.count("\n"))
        check("fix: the change log has the rows of the script and the sections of a report",
              logtext.startswith("# Change log") and all(x in logtext for x in (
                  "## Changes made", "| C-01 | rules.src | 2 | 2 | Assignment in a condition | `if (@Severity = 5) {` | `if (@Severity == 5) {` |",
                  "| C-04 | rules.src | 10 | 10 | Entity without its closing ;, Tag not closed |",
                  "## Findings of the review that were not corrected", "## Checks performed", "## Not checked",
                  "## Questions for the owner of the code", "checksum of the copy")), logtext)
        check("fix: an open High finding of the review keeps the fix incomplete",
              "High findings neither corrected nor left to the owner: 1" in out and "S-03  line 8" in out
              and "Corrections: not complete" in out and "Gate: not passed yet" in out
              and "| S-03 | High | 8 |" in logtext and "NOT DECIDED" in logtext, out)
        check("fix: the comparison of the copy with the original is shown",
              "5. Places where lines differ: 4" in out and "Result: nothing to settle" in out, out)
        check("fix: the notes skeleton shows the form of a correction and the open finding",
              all(x in fnotes for x in ("## Corrections", "### line 120", "after:", "why:", "## Left for the owner", "S-03: Nothing in this code sets sumary, which line 8 reads.",
                                        "## Questions for the owner")) and "run.py fix" in fnotes, fnotes)
        code, out, err = run(*fix_args)
        check("fix: with the notes untouched, the open High finding stays with the owner and the fix is complete",
              code == 0 and "Gate: passed" in out and "NOT DECIDED" not in log.read_text()
              and "For the owner: Nothing in this code sets sumary" in log.read_text(), out + err)
        write(notes_for(log), "## Corrections\n## Left for the owner\n")
        code, out, err = run(*fix_args)
        check("fix: a later run that is still incomplete exits 3",
              code == 3 and "Gate: not passed yet" in out and "expected on the first run" not in out, out + err)

        write(notes_for(log), "## Corrections\n## Left for the owner\nS-03: Who sets sumary before these rules run?\n")
        code, out, err = run(*fix_args)
        logtext = log.read_text()
        check("fix: a High finding left to the owner with its question completes the fix",
              code == 0 and "Corrections: complete" in out and "Gate: passed" in out
              and "| S-03 | High | 8 |" in logtext and "For the owner: Who sets sumary before these rules run?" in logtext
              and "1. S-03 (line 8): Who sets sumary before these rules run?" in logtext, out + logtext[-800:])
        copy1, log1 = (fixed_dir / "rules.src").read_bytes(), log.read_bytes()
        code, out, err = run(*fix_args)
        check("fix: running it again gives the same bytes",
              code == 0 and (fixed_dir / "rules.src").read_bytes() == copy1 and log.read_bytes() == log1)

        (fixed_dir / "rules.src").write_text(fixed.replace("Critical", "CRITICAL"))
        code, out, err = run(*fix_args)
        aside = fx / "log.edited-by-hand" / "rules.src"
        check("fix: a copy edited by hand is set aside and written again from the notes",
              "had been edited by hand" in out and str(aside) in out and aside.exists() and "CRITICAL" in aside.read_text()
              and (fixed_dir / "rules.src").read_bytes() == copy1, out + err)

        write(notes_for(log), "## Corrections\n### line 3\nafter: Title = \"Critical alarm: \" + @Node;\nwhy: x\n"
                              "## Left for the owner\nS-03: Who sets sumary before these rules run?\n")
        code, out, err = run(*fix_args)
        check("fix: a correction whose \"why:\" is too short is refused",
              code == 3 and "\"why:\" is missing or too short" in out and "Corrections: not complete" in out
              and "Critical alarm" not in (fixed_dir / "rules.src").read_text(), out)

        write(notes_for(log), FIX_NOTES)
        code, out, err = run(*fix_args)
        got = (fixed_dir / "rules.src").read_text()
        logtext = log.read_text()
        check("fix: corrections of the notes are applied with the indentation of the original", got == FIX_EXPECTED, got)
        check("fix: the change log has the rows of the notes, in the order of the lines",
              re.search(r"^\| C-01 \| rules\.src \| 2 \| 2 \| Assignment in a condition \|", logtext, re.M)
              and "| H-01 | rules.src | 3 | 3 | Wording | `Title = \"Critical: \" + @Node;` | `Title = \"Critical alarm: \" + @Node;` | the desk asked" in logtext
              and "| H-02 | rules.src | 5 | 5 | Branch rewritten | `elseif (@Severity == 4 && @Manager = 'Collector') {` | `elseif (@Severity == 4) {` |" in logtext
              and "| H-02 | rules.src |  | 8 | Branch rewritten | (no line) | `}` | As above. |" in logtext
              and "| H-03 | rules.src | 8 | 9 | Misspelt name | `Summary = Title + \" \" + sumary;` | `Summary = Title + \" \" + @Summary;` |" in logtext
              and "| H-04 | rules.src | 9 |  |" in logtext and "| `Summary = Summary + \" at \" + Node;` | (removed) |" in logtext
              and "| C-02 | rules.src | 10 | 10 |" in logtext, logtext)
        check("known fault (fix_code.py): a removed line is labelled \"Line removed\" even when the removal is not the "
              "last block of the notes", "| H-04 | rules.src | 9 |  | Line removed |" in logtext,
              [l for l in logtext.split("\n") if l.startswith("| H-04")], known=True)
        check("fix: with every High finding corrected the gate passes, and the verdict and question are in the log",
              code == 0 and "Corrections: complete" in out and "Gate: passed" in out and "0 left as they are" in out
              and "Every High finding is corrected" in logtext and "Should the Collector check stay?" in logtext, out)
        check("fix: the change log says the findings corrected and the scan counts before and after",
              "| Assignment in a condition | scan_code.py, original and copy | 2 | 0 |" in logtext
              and "Of the findings of the review," in logtext, logtext)
        code, out, err = run("scan_code.py", fixed_dir / "rules.src")
        check("fix: nothing left that the script could correct",
              counts(out)[cond] == 0 and counts(out)[TITLES[E]] == 0 and counts(out)[TITLES[G]] == 0 and counts(out)[unset] == 0, out)

        # a name given a value without its prefix goes through the whole fix command
        sp = tmp / "setprefix"
        write(sp / "setprefix.x", "@Severity = 1;\nx = @Severity;\nSeverity = 2;\nprint(x + @Severity);\n")
        code, out, err = run("run.py", "fix", sp / "setprefix.x", "--out", sp / "out", "--log", sp / "log.md")
        got = (sp / "out" / "setprefix.x").read_text() if (sp / "out" / "setprefix.x").exists() else ""
        check("fix: a name given a value without its prefix is corrected, logged, and the gate passes",
              code == 0 and "\n@Severity = 2;\n" in got and "Name given a value without its prefix" in (sp / "log.md").read_text()
              and "Gate: passed" in out, out + err)

        # the corrected copy keeps the line endings and the encoding of the original, byte for byte
        cr = tmp / "crlf"
        raw = SAMPLES["rules.src"].replace("\n", "\r\n").encode("latin-1").replace(b"sample rules", b"r\xe8gles")
        write(cr / "crlf.src", "")
        (cr / "crlf.src").write_bytes(raw)
        code, out, err = run("fix_code.py", cr / "crlf.src", "--out", cr / "out", "--log", cr / "log.md")
        got = (cr / "out" / "crlf.src").read_bytes() if (cr / "out" / "crlf.src").exists() else b""
        check("fix: runs on a file that is not UTF-8", code == 0 and not err and "Result: complete" in out, out + err)
        check("fix: line endings kept", got.count(b"\r\n") == raw.count(b"\r\n") and got.count(b"\n") == raw.count(b"\n"))
        check("fix: bytes outside the corrections kept", b"r\xe8gles" in got and b"@Severity == 5" in got
              and len(got) == len(raw) + 2 + 1 + 1 + 1, "%d %d" % (len(got), len(raw)))
        write(notes_for(cr / "log.md"), "## Corrections\n### line 8\nafter: Summary = Title + \" \" + @Summary;\n"
                                        "why: sumary is never set; the field @Summary holds the summary of the event.\n"
                                        "### line 3\nafter: Title = \"Critique : \" + @Node;\n"
                                        "why: the title is in French for this desk, as the requirement for the French desk says.\n")
        code, out, err = run("fix_code.py", cr / "crlf.src", "--out", cr / "out", "--log", cr / "log.md")
        got = (cr / "out" / "crlf.src").read_bytes()
        check("fix: corrections of the notes keep CRLF, the encoding and the indentation",
              code == 0 and got.count(b"\r\n") == raw.count(b"\r\n") and got.count(b"\n") == got.count(b"\r\n")
              and b"r\xe8gles" in got and b'    Title = "Critique : " + @Node;\r\n' in got
              and b'Summary = Title + " " + @Summary;\r\n' in got, repr(got[:200]))
        write(notes_for(cr / "log.md"), "## Corrections\n### line 3\nafter: Title = \"\u20ac \" + @Node;\n"
                                        "why: the euro sign is wanted here by the requirement for prices.\n")
        code, out, err = run("fix_code.py", cr / "crlf.src", "--out", cr / "out", "--log", cr / "log.md")
        check("fix: a correction with a character the encoding cannot hold is refused plainly",
              code not in (0, 3) and "cannot hold" in out + err and "Traceback" not in err, out + err)
        code, out, err = run("scan_code.py", cr / "crlf.src")
        check("scan: lines counted as an editor counts them", "1 file(s), 11 lines" in out, out[:200])

        # a review report whose columns were renamed and moved is still read by its header names
        mv = tmp / "moved"
        write(mv / "rules.src", SAMPLES["rules.src"])
        moved = mv / "moved.md"
        out_lines = []
        for line in reg.read_text().split("\n"):
            c = re.split(r"(?<!\\)\|", line)
            if len(c) >= 10 and (c[1].strip() in ("ID", "---") or re.match(r"\s*S-\d+", c[1])):
                extra = " Owner " if c[1].strip() == "ID" else "---" if c[1].strip() == "---" else " NOC team "
                c[6] = c[6].replace("What it does", "Effect on the event")
                c = c[:2] + [extra] + c[2:]                   # a new second column: every other one moves
            out_lines.append("|".join(c))
        moved.write_text("\n".join(out_lines))
        code, out, err = run("run.py", "check", moved, mv / "rules.src")
        check("moved columns: the check of the report finds the decision column by its name",
              code == 0 and "Gate: passed" in out and "NOC team" in moved.read_text(), out + err)
        code, out, err = run("run.py", "fix", mv / "rules.src", "--out", mv / "out", "--log", mv / "log.md", "--register", moved)
        check("moved columns: fix reads the severity, line and kind of each finding from the right columns",
              code == 0 and "High findings neither corrected nor left to the owner: 1" in out and "S-03  line 8" in out
              and "| S-03 | High | 8 | Name read, never assigned" in (mv / "log.md").read_text(), out + err)

        # a change made by hand in the copy, outside the fix, is caught by the comparison with the log
        hd = tmp / "hand"
        write(hd / "rules.src", SAMPLES["rules.src"])
        code, out, err = run("fix_code.py", hd / "rules.src", "--out", hd / "out", "--log", hd / "log.md")
        hand = (hd / "out" / "rules.src").read_text().replace("sumary", "Summary")
        (hd / "out" / "rules.src").write_text(hand)
        code, out, err = run("run.py", "change", hd / "rules.src", hd / "out", "--report", hd / "log.md", "--lines")
        check("change: a line changed by hand that is not in the log closes the gate",
              code == 3 and "Lines that differ: line 8" in out, out + err)
        with open(hd / "log.md", "a") as fh:
            fh.write("| H-01 | rules.src | 3 | 3 | by hand | x | `Summary = Title + \" \" + Summary;` | wrong line |\n")
        code, out, err = run("run.py", "change", hd / "rules.src", hd / "out", "--report", hd / "log.md", "--lines")
        check("change: a row that quotes the change under another line number does not settle it",
              code == 3 and "Lines that differ: line 8" in out, out + err)
        with open(hd / "log.md", "a") as fh:
            fh.write("| H-02 | rules.src | 8 | 8 | by hand | `Summary = Title + \" \" + sumary;` | `Summary = Title + \" \" + Summary;` | right line |\n")
        code, out, err = run("run.py", "change", hd / "rules.src", hd / "out", "--report", hd / "log.md", "--lines")
        check("change: a row with the line number and the line as it is now settles it",
              code == 0 and "Gate: passed" in out, out + err)

        # ================================================================ edit: a change made from a plan
        ed = tmp / "edit"
        write(ed / "code.js", "")
        raw = EDIT_CODE.replace("\n", "\r\n").encode("latin-1")
        (ed / "code.js").write_bytes(raw)
        ereport, emap = ed / "change.md", ed / "map.md"
        plan = notes_for(ereport)
        code, out, err = run("run.py", "edit", ed / "code.js", "--out", ed / "out", "--report", ereport, "--map", emap)
        ptext = plan.read_text() if plan.exists() else ""
        check("edit: first run ends normally, writes the report, the plan and an unchanged copy",
              code == 0 and not err and "Plan: not complete" in out and "Gate: not passed yet" in out
              and "expected on the first run" in out and ereport.read_text().startswith("# Change — code.js")
              and (ed / "out" / "code.js").read_bytes() == raw and not emap.exists(), out + err)
        check("edit: the plan skeleton has the form of each part and the facts of the code",
              all(x in ptext for x in ("## Corrections", "### rule prefix-logs", "## Renames", "accept the proposals",
                                       "Names that are not camelCase (2):", "order_total, row_count",
                                       "## Files", "## Explanations", "## Verdict", "Line endings: CRLF", "Logging calls: 1, on lines 5"))
              and "run.py edit" in ptext, ptext)
        write(plan, "# Plan for the change change.md\n\n" + EDIT_PLAN_PARTS + EDIT_PLAN_REFUSED + EDIT_PLAN_TAIL % "row_count -> label")
        code, out, err = run("edit_code.py", ed / "code.js", "--out", ed / "out", "--report", ereport)
        got = (ed / "out" / "code.js").read_bytes()
        rtext = ereport.read_text()
        check("edit: a bad regular expression, a rule that changes no line and a rename to a name in use are refused",
              code == 3 and "Result: not complete" in out
              and re.search(r"rule broken \(line \d+ of the notes\): the regular expression is not valid", out)
              and re.search(r"rule nothing \(line \d+ of the notes\): changes no line", out)
              and "rename row_count -> label: the code already uses label for something else" in out, out + err)
        check("edit: correction, insertion, rule with a group and rename are applied; the rename leaves strings and members "
              "alone; CRLF and the encoding are kept byte for byte",
              got == EDIT_EXPECTED.replace("\n", "\r\n").encode("latin-1"), repr(got))
        check("edit: the report lists the corrections, the rule and the rename",
              "| E-01 | code.js | 7 | Replaced | `let label = \"Total: \";` | `let label = \"Sum: \";` |" in rtext
              and "| E-02 | code.js | 1 | Inserted after line 1 | (no line) | `// generated from the plan` |" in rtext
              and "| E-02 | code.js |  | Inserted after line 1 | (no line) | `'use strict';` | As above. |" in rtext
              and "| constants | `let (\\w+) = fetchRows` | `const \\1 = fetchRows` | 2 (on lines 3-4) |" in rtext
              and "| nothing | `zzz_never_there` | `y` | 0 |" in rtext
              and "| `order_total` | `orderRows` | 4 |" in rtext, rtext)
        write(plan, "# Plan for the change change.md\n\n" + EDIT_PLAN_PARTS + EDIT_PLAN_TAIL % "")
        code, out, err = run("run.py", "edit", ed / "code.js", "--out", ed / "out", "--report", ereport, "--map", emap)
        mtext = emap.read_text() if emap.exists() else ""
        check("edit: with the plan corrected the change is complete, every difference is explained and the gate passes",
              code == 0 and "Plan: applied in full" in out and "Gate: passed" in out
              and (ed / "out" / "code.js").read_bytes() == EDIT_EXPECTED.replace("\n", "\r\n").encode("latin-1"), out + err)
        check("edit: the command traces the lines and writes the map with the explanations of the plan",
              "Where each line went" in out and "What the change did" in out and mtext.startswith("# Traceability map")
              and "## Notes and assumptions" in mtext
              and "The keyword `const` replaces let for the two lookups" in mtext.split("## Notes and assumptions")[-1], mtext)
        check("edit: the report of the change holds the explanations and the verdict",
              "The label text \"Total: \" becomes \"Sum: \"" in ereport.read_text()
              and "The plan renames the lookup result" in ereport.read_text(), ereport.read_text())

        # a split into files
        sd = tmp / "split-edit"
        write(sd / "big.js", SPLIT_CODE)
        sreport, smap = sd / "change.md", sd / "map.md"
        code, out, err = run("run.py", "edit", sd / "big.js", "--out", sd / "out", "--report", sreport, "--map", smap)
        ptext = notes_for(sreport).read_text()
        check("edit split: the plan proposes a camelCase form for each name that is not camelCase",
              code == 0 and "Names that are not camelCase (1):" in ptext and "order_total" in ptext
              and re.search(r"nothing in this code reads them.*?\n\s+TT_Check_Data", ptext, re.S)
              and "Line endings: LF" in ptext, ptext)
        write(notes_for(sreport), SPLIT_PLAN % ("7-11", SPLIT_PLAN_OUTSIDE))
        code, out, err = run("edit_code.py", sd / "big.js", "--out", sd / "out", "--report", sreport)
        lookups = (sd / "out" / "lib" / "lookups.js").read_text() if (sd / "out" / "lib" / "lookups.js").exists() else ""
        labels = (sd / "out" / "lib" / "labels.js").read_text() if (sd / "out" / "lib" / "labels.js").exists() else ""
        check("edit split: a range outside the code is refused, and a line placed in no file is reported",
              code == 3 and "the range 40-45 is outside big.js (13 lines)" in out
              and "1 line(s) of big.js are in no file and not removed: lines 12" in out, out + err)
        check("edit split: the files hold their ranges, with the accepted renames, the prepended and the appended lines",
              lookups == "// part one: lookups\nfunction load(key) {\n  let orderTotal = fetchRows(table, \"name = '\" + key + \"'\");\n"
                         "  TT_Check_Data = orderTotal.length;\n  return orderTotal;\n}\n"
              and labels.startswith("// labels, split from big.js\n// part two: labels\nfunction build(rows) {\n")
              and labels.endswith("  return label;\nsend(build(load(key)));\n"), lookups + "\n----\n" + labels)
        check("edit split: the report lists the files written and the renames applied",
              "| lib/lookups.js | 1-6 | 6 | 0 |" in sreport.read_text() and "| lib/labels.js | 7-11 | 7 | 2 |" in sreport.read_text()
              and "| `order_total` | `orderTotal` | 3 |" in sreport.read_text()
              and "ttCheckData" not in sreport.read_text(), sreport.read_text())
        write(notes_for(sreport), SPLIT_PLAN % ("7-12", ""))
        code, out, err = run("run.py", "edit", sd / "big.js", "--out", sd / "out", "--report", sreport, "--map", smap)
        labels = (sd / "out" / "lib" / "labels.js").read_text()
        mtext = smap.read_text() if smap.exists() else ""
        check("edit split: with every line placed the plan is complete, and a file of the earlier plan is removed",
              code in (0, 3) and "Plan: applied in full" in out and not (sd / "out" / "lib" / "outside.js").exists()
              and labels.endswith("  return label;\n}\nsend(build(load(key)));\n")
              and sorted(p.name for p in (sd / "out" / "lib").iterdir()) == ["labels.js", "lookups.js"], out + err)
        check("edit split: the trace finds every earlier line, and the map holds the explanations",
              "Earlier lines found in the later version: 9 of 9" in out and "labels.js <- 5 lines of big.js" in out
              and "lookups.js <- 4 lines of big.js" in out
              and "`send`, `build` and `load` are called from the new last line of labels.js" in mtext, out + mtext)
        check("edit split: the gate of the split passes", code == 0 and "Gate: passed" in out, out)

        # ================================================================ run.py: every command on every sample
        for name in sorted(SAMPLES):
            work = tmp / ("all-" + name.replace(".", "-"))
            for step, extra, gate in (("review", ["--out", work / "register.md"], True),
                                      ("check", [work / "register.md"], True),
                                      ("fix", ["--out", work / "fixed", "--log", work / "log.md", "--register", work / "register.md"], True),
                                      ("look", [], False),
                                      ("edit", ["--out", work / "edited", "--report", work / "change.md", "--map", work / "map.md"], True)):
                args = [step] + ([work / "register.md", samples / name] if step == "check" else [samples / name] + extra)
                code, out, err = run("run.py", *args)
                check("%s on %s: ends normally" % (step, name),
                      ok_run(code, out, err) and (not gate or "Gate:" in out), (out + err)[-400:])
            code, out, err = run("run.py", "change", samples / name, work / "fixed", "--map", work / "map2.md",
                                 "--report", work / "log.md")
            check("change on %s: ends normally" % name, ok_run(code, out, err) and "Gate:" in out, (out + err)[-400:])

        # more languages: the planted defects are found, and the only name reported as never set is the misspelt one
        for name, text, expected, unset_names in MORE_LANGUAGES:
            write(samples / name, text)
            code, out, err = run("scan_code.py", samples / name)
            c = counts(out)
            check("%s: scan runs" % name, code == 0 and not err, err[-300:])
            for index, want in expected.items():
                check("%s: %s = %d" % (name, TITLES[index], want), c[TITLES[index]] == want,
                      "got %s\n%s" % (c[TITLES[index]], section(out, TITLES[index])[:400]))
            listed = re.findall(r"^  line \d+  (\S+) — read", section(out, TITLES[1]), re.M)
            check("%s: the only name never set is the misspelt one" % name, listed == unset_names,
                  "listed %s\n%s" % (listed, section(out, TITLES[1])[:500]))
            work = tmp / ("more-" + name.replace(".", "-"))
            for step, extra in (("review", ["--out", work / "register.md"]),
                                ("fix", ["--out", work / "fixed", "--log", work / "log.md"]),
                                ("look", []),
                                ("edit", ["--out", work / "edited", "--report", work / "change.md"])):
                code, out, err = run("run.py", step, samples / name, *extra)
                check("%s on %s: ends normally" % (step, name), ok_run(code, out, err), (out + err)[-400:])

        # a fault inside a script is reported as a fault, never as a result
        broken = tmp / "broken-scripts"
        shutil.copytree(SCRIPTS, broken, ignore=shutil.ignore_patterns("__pycache__"))
        (broken / "fix_code.py").write_text("raise RuntimeError('deliberate fault for the test')\n")
        r = subprocess.run([sys.executable, "-B", str(broken / "run.py"), "fix", str(samples / "rules.src"), "--out",
                            str(tmp / "nowhere"), "--log", str(tmp / "nowhere.md")], capture_output=True, text=True, cwd=str(CWD))
        check("a script that stops on a fault is reported as a fault",
              r.returncode == 1 and "The script fix_code.py failed" in r.stdout and "Gate:" not in r.stdout
              and not (tmp / "nowhere.md").exists(), r.stdout + r.stderr)

        # ================================================================ compare, trace, inventory, change
        cmp = tmp / "cmp"                            # code only; the documents these tests write go to cmp-docs
        docs = tmp / "cmp-docs"
        write(cmp / "before.js", BEFORE)
        write(cmp / "same.js", BEFORE)
        write(cmp / "swap.js", AFTER_SWAP)
        write(cmp / "split" / "one.js", SPLIT_A)
        write(cmp / "split" / "two.js", SPLIT_B)

        code, out, err = run("compare_code.py", cmp / "before.js", cmp / "same.js")
        check("compare identical: runs", code == 0 and not err, err[-300:])
        check("compare identical: gate holds", "Result: nothing to settle" in out, out)
        check("compare identical: nothing listed",
              all(x in out for x in ("new after the change: 0", "0 new to the code, 0 gone from it, 0 with",
                                     "new to the code: 0", "0 gone, 0 used fewer times, 0 used more times, 0 new")), out)

        code, out, err = run("compare_code.py", cmp / "before.js", cmp / "swap.js")
        check("compare swap: runs", code == 0 and not err, err[-300:])
        check("compare swap: call gone", re.search(r"Gone from the code.*\n\s+fetchRows\s+2 -> 0", out) is not None, out)
        check("compare swap: call new", re.search(r"New to the code.*\n\s+runQuery\s+0 -> 1", out) is not None, out)
        check("compare swap: new operator", re.search(r"operator\s+\?", out) is not None, out)
        check("compare swap: gate says so",
              re.search(r"TO SETTLE\s+Calls gone.*fetchRows 2 -> 0", out) is not None
              and "to settle before the task is finished" in out, out)
        check("compare swap: text gone and new, spaces kept", '"Total: "' in out and '"Total = "' in out, out)

        # a rename between naming styles is not a new scan hit; functions of the later version are listed apart
        write(cmp / "snake.js", "order_total = 1;\nrow_count = 2;\nlog(row_count + grand_total);\n")
        write(cmp / "camel.js", "function show(n) {\n  log(n);\n}\norderTotal = 1;\nrowCount = 2;\nshow(rowCount + grandTotal);\n")
        code, out, err = run("compare_code.py", cmp / "snake.js", cmp / "camel.js")
        check("compare rename: runs", code == 0 and not err, err[-300:])
        check("compare rename: renamed hits are not new", "Scan hits that are new after the change: 0" in out, out)
        check("compare rename: functions of the later version listed apart",
              "Functions the later version defines: 1" in out and "0 new to the code" in out, out)
        check("compare rename: a new keyword is still reported", re.search(r"keyword\s+function", out) is not None, out)
        write(cmp / "more.js", BEFORE.replace('label + b.length;', 'label + b.length + "none";'))
        code, out, err = run("compare_code.py", cmp / "before.js", cmp / "more.js")
        check("compare: a string used more often is listed", "1 used more times" in out and '1 -> 2  "none"' in out, out)

        # a new scan hit on a short line is settled by naming the place, not by quoting the code
        write(cmp / "a" / "short.js", "x = 1;\nuse(x);\n")
        write(cmp / "b" / "short.js", "x = 1;\nif (x) { }\nuse(x);\n")
        write(docs / "bytext.md", "The line if (x) { } is an empty block kept on purpose; `if`, `{` and `}` are new.\n")
        write(docs / "byplace.md", "short.js:2 is an empty block kept on purpose; `if`, `{` and `}` are new.\n")
        code, out, err = run("compare_code.py", cmp / "a" / "short.js", cmp / "b" / "short.js", "--report", docs / "bytext.md")
        check("compare: a new hit on a line shorter than 12 characters is not settled by its text",
              code == 0 and "TO SETTLE  Scan hits that are new, and scan counts that went up: short.js:2 Block with nothing in it" in out,
              out + err)
        code, out, err = run("compare_code.py", cmp / "a" / "short.js", cmp / "b" / "short.js", "--report", docs / "byplace.md")
        check("compare: the same hit is settled by file:line", "Result: nothing to settle" in out, out + err)
        write(cmp / "a" / "long.js", "count = 1;\nuse(count);\n")
        write(cmp / "b" / "long.js", "count = 1;\nif (count) { }\nuse(count);\n")
        write(docs / "longtext.md", "The line if (count) { } is an empty block kept on purpose; `if`, `{` and `}` are new.\n")
        code, out, err = run("compare_code.py", cmp / "a" / "long.js", cmp / "b" / "long.js", "--report", docs / "longtext.md")
        check("compare: a new hit on a longer line is settled by quoting the line", "Result: nothing to settle" in out, out + err)

        code, out, err = run("compare_code.py", cmp / "before.js", cmp / "split")
        check("compare split: runs", code == 0 and not err, err[-300:])
        check("compare split: value that lost its source", "rowCount" in out, out)
        check("compare split: link broken by a rename", "wirelessType" in out and "WIRELESSTYPE" in out, out)
        check("compare split: counts marked as gone up", "went up" in out)

        # line endings changed by an edit are reported
        (cmp / "crlf.js").write_bytes(BEFORE.replace("\n", "\r\n").encode())
        (cmp / "lf.js").write_bytes(BEFORE.encode())
        code, out, err = run("run.py", "change", cmp / "crlf.js", cmp / "lf.js")
        check("change: line endings that changed are marked", code == 3 and "TO SETTLE  Line endings: CRLF -> LF" in out, out + err)

        # the list of changed names is applied to names only, and lines that did not move stay paired
        write(cmp / "r1.js", "region = 'north';\nlabel = 'region : ' + region;\nobj.region = region;\nsend(label);\n")
        write(cmp / "r2.js", "area = 'north';\nlabel = 'region : ' + area;\nobj.region = area;\nsend(label);\n")
        write(docs / "r.md", "region -> area\n")
        code, out, err = run("trace_code.py", cmp / "r1.js", cmp / "r2.js", "--renames", docs / "r.md")
        check("trace: a renamed name is followed, but not inside a string or after a dot",
              "found in the later version: 4 of 4 (4 with the same text" in out, out + err)
        write(cmp / "r3.js", "area = 'north';\ntag = 'region : ' + area;\nobj.region = area;\nsend(tag);\n")
        write(docs / "plan.md", "# Plan\n## Renames\nregion -> area\n## Explanations\nlabel -> tag is not a rename here\n")
        code, out, err = run("trace_code.py", cmp / "r1.js", cmp / "r3.js", "--renames", docs / "plan.md")
        check("trace: a file with a \"## Renames\" section gives only the names of that section",
              "Names followed to their new name: 1," in out and "(2 with the same text, 2 with other names)" in out, out + err)
        write(docs / "flat.md", "region -> area\nlabel -> tag\n")
        code, out, err = run("trace_code.py", cmp / "r1.js", cmp / "r3.js", "--renames", docs / "flat.md")
        check("trace: a plain list of names is read whole",
              "Names followed to their new name: 2," in out and "4 of 4 (4 with the same text" in out, out + err)
        write(cmp / "p1.js", "if (a) {\n  x = 1;\n} else {\n  x = 2;\n}\nif (b) {\n  y = 1;\n} else {\n  y = 2;\n}\n")
        write(cmp / "p2.js", "if (a) {\n  x = 1;\n} else {\n  x = 2;\n}\nif (b) {\n  y = 1;\n}\n")
        code, out, err = run("trace_code.py", cmp / "p1.js", cmp / "p2.js")
        check("trace: of two identical lines, the one that is gone is the one reported",
              "p1.js:8-9 (2)" in out and "p1.js:3" not in out, out + err)

        # inventory and trace
        code, out, err = run("run.py", "look", cmp / "before.js")
        check("look: repeated calls listed", code == 0 and re.search(r"fetchRows\(table, \.\.\.\)\s+x2", out), out + err)
        check("look: lines counted as an editor counts them; a definition is not a call",
              re.search(r"Lines\s+8\n", out) and not re.search(r"^  load\s+1$", out, re.M), out)
        write(cmp / "loop.js", "var i = 0;\nwhile (i < n) {\n  var row = fetchRow(i);\n  log(row);\n  i = i + 1;\n}\n")
        code, out, err = run("run.py", "look", cmp / "loop.js")
        check("look: a call inside a loop is listed",
              "line 3  fetchRow(...)  in the loop that starts on line 2" in out and "log(...)" not in out, out + err)
        write(cmp / "old.js", "// totals\norder_total = price * qty;\nif (order_total > 100) {\n  discount = 5;\n}\nlog(order_total);\n")
        write(cmp / "new" / "a.js", "orderTotal = price * qty;\nif (orderTotal > 100) {\n")
        write(cmp / "new" / "b.js", "    discount = 5;\n}\naudit(orderTotal);\n")
        code, out, err = run("trace_code.py", cmp / "old.js", cmp / "new", "--out", docs / "map.md")
        check("trace: runs", code == 0 and not err, out + err)
        check("trace: renamed and moved lines are found", "found in the later version: 3 of 4" in out, out)
        # names changed to other words: found by the second pass, or through a list of the names
        write(cmp / "v1.js", "rows = fetchRows(table, key);\nfirst_row = rows[0];\nsend(first_row, 'done');\ntotal = total + 1;\n")
        write(cmp / "v2.js", "records = fetchRows(table, key);\nleading = records[0];\nsend(leading, 'done');\ncount = count + 1;\n")
        code2, out2, err2 = run("trace_code.py", cmp / "v1.js", cmp / "v2.js")
        check("trace: a line whose variables were renamed is found by its calls and strings",
              "2 with other names" in out2 and "Not found: 2" in out2, out2 + err2)
        write(docs / "names.md", "| Old | New |\n|---|---|\n| `rows` | `records` |\n| first_row | leading |\ntotal -> count\n")
        code2, out2, err2 = run("trace_code.py", cmp / "v1.js", cmp / "v2.js", "--renames", docs / "names.md")
        check("trace: with the list of changed names every line is found",
              "found in the later version: 4 of 4 (4 with the same text" in out2 and "Names followed to their new name" in out2,
              out2 + err2)
        code2, out2, err2 = run("run.py", "change", cmp / "v1.js", cmp / "v2.js", "--renames", docs / "names.md")
        check("change: renamed names are not new scan hits", "holds      Scan hits that are new" in out2, out2 + err2)
        write(cmp / "v3.js", "a = 1;\nb = 2;\nc = 3;\nkeep(a);\nd = 4;\ne = 5;\n")
        write(cmp / "v4.js", "keep(a);\n")
        code2, out2, err2 = run("trace_code.py", cmp / "v3.js", cmp / "v4.js")
        check("trace: lines that are gone are grouped into runs", "Not found: 5, in 2 run(s)" in out2
              and "v3.js:1-3 (3)" in out2 and "v3.js:5-6 (2)" in out2, out2 + err2)
        check("trace: a lost line is named", "log(order_total);" in out)
        check("trace: a new line is named", "audit(orderTotal);" in out)
        check("trace: map written", (docs / "map.md").exists() and "## Where the earlier code is now" in (docs / "map.md").read_text())
        filled = (docs / "map.md").read_text().replace("| `log(order_total);` | Logging removed or reworded |  |",
                                                        "| `log(order_total);` | Logging removed or reworded | Removed: replaced by audit |")
        (docs / "map.md").write_text(filled.replace("1. None yet.", "1. The audit call replaces the log call."))
        run("trace_code.py", cmp / "old.js", cmp / "new", "--out", docs / "map.md")
        again = (docs / "map.md").read_text()
        check("trace: a map written again keeps what was filled in by hand",
              "Removed: replaced by audit" in again and "The audit call replaces the log call." in again, again)
        write(docs / "expl.md", "# Plan\n## Renames\norder_total -> orderTotal\n## Explanations\n"
                                "<!-- guidance that is not read -->\nThe `audit` call replaces `log`, as the requirement asks.\n## Verdict\nDone.\n")
        code, out, err = run("trace_code.py", cmp / "old.js", cmp / "new", "--out", docs / "map2.md", "--renames", docs / "expl.md",
                             "--notes", docs / "expl.md")
        again = (docs / "map2.md").read_text() if (docs / "map2.md").exists() else ""
        check("trace: with --notes the explanations of the notes go into the map, without the guidance",
              code == 0 and "The `audit` call replaces `log`, as the requirement asks." in again.split("## Notes and assumptions")[-1]
              and "guidance that is not read" not in again and "Names followed to their new name: 1," in out, out + again[-500:])
        code, out, err = run("run.py", "change", cmp / "before.js", cmp / "swap.js")
        check("change: one command gives counts, trace and gate",
              all(x in out for x in ("Counts before and after", "Where each line went", "Gate:")) and not err, out + err)
        check("change: gate not passed on a swapped call, and the exit code says so",
              code == 3 and "Gate: not passed yet" in out, out)
        code, out, err = run("run.py", "change", cmp / "before.js", cmp / "same.js")
        check("change: gate passes on an identical copy", code == 0 and "Gate: passed" in out, out)
        own_map = docs / "own-map.md"
        code, out, err = run("run.py", "change", cmp / "before.js", cmp / "swap.js", "--map", own_map, "--report", own_map)
        check("change: a map with empty notes does not explain anything", code == 3 and "under \"Notes and assumptions\"" in out
              and "fetchRows 2 -> 0" in out, out + err)
        explained = ("The requirement asks for one query: `fetchRows` is replaced by `runQuery`, which is new and needs a test.\n"
                     "The operators `?` and `:` are new and need a test.\n"
                     "Strings: \"name = '\", \"owner = '\", \"Total: \" are gone; \" where name = '\", "
                     "\"select * from \" and \"Total = \" are new.\n"
                     "`rows` is new and is assigned from the query; `a` and `b` are gone.\n"
                     "swap.js:3 joins the key into the query text, as the earlier filter did.\n")
        own_map.write_text(own_map.read_text().replace("1. None yet.", explained))
        code, out, err = run("run.py", "change", cmp / "before.js", cmp / "swap.js", "--map", own_map, "--report", own_map)
        check("change: notes written in the map are kept and settle the gate", code == 0 and "Gate: passed" in out, out + err)
        write(docs / "vague.md", "We replaced fetchRows by runQuery, used ? and : and changed some strings.\n")
        code, out, err = run("run.py", "change", cmp / "before.js", cmp / "swap.js", "--report", docs / "vague.md")
        check("change: a call named in passing, without backticks or its count line, is not settled",
              code == 3 and "TO SETTLE  Calls gone from the code or new to it: fetchRows 2 -> 0" in out, out + err)
        write(cmp / "often.js", BEFORE.replace("return label + b.length;", "b = fetchRows(table, key);\n  return label + b.length;"))
        code, out, err = run("run.py", "change", cmp / "before.js", cmp / "often.js")
        check("change: a call made more often than before is marked",
              "TO SETTLE  Calls made more often than before: fetchRows 2 -> 3" in out, out + err)
        # a difference is settled when the report mentions it
        write(docs / "why.md", "Nothing explained yet.\n")
        code, out, err = run("run.py", "change", cmp / "before.js", cmp / "swap.js", "--report", docs / "why.md")
        check("change: with a report that explains nothing, the gate stays closed",
              code == 3 and "fetchRows 2 -> 0" in out and "Gate: not passed yet" in out, out + err)
        write(docs / "why.md", explained)
        code, out, err = run("run.py", "change", cmp / "before.js", cmp / "swap.js", "--report", docs / "why.md")
        check("change: once the report names every difference, the gate passes", code == 0 and "Gate: passed" in out, out + err)
        write(docs / "why.md", explained.replace(", which is new and needs a test", ""))
        code, out, err = run("run.py", "change", cmp / "before.js", cmp / "swap.js", "--report", docs / "why.md")
        check("change: a call the earlier version never made is not settled until its line says it needs a test",
              code == 3 and "runQuery 0 -> 1" in out and "Gate: passed" not in out, out + err)

        # a rename of a name the code never sets, or never reads, is refused: something outside may use that name
        rn = tmp / "rename-edit"
        write(rn / "job.x", "Job_State = Lookup(Event_Handle);\nOut_Record = Job_State;\nif (Job_State == 1) {\n"
                             "    Out_Record = 2;\n}\nfinish(Event_Handle);\n")
        rreport = rn / "change.md"
        run("edit_code.py", rn / "job.x", "--out", rn / "out", "--report", rreport, cwd=rn)
        rplan = notes_for(rreport).read_text()
        check("edit: the plan says which names are left alone because something outside may use them",
              "Names that are not camelCase (1):" in rplan and re.search(r"never gives them a value.*?\n\s+Event_Handle", rplan, re.S)
              and re.search(r"nothing in this code reads them.*?\n\s+Out_Record", rplan, re.S), rplan)
        write(notes_for(rreport), "# Plan\n\n## Renames\naccept the proposals\nEvent_Handle -> eventHandle\nOut_Record -> outRecord\n")
        code, out, err = run("edit_code.py", rn / "job.x", "--out", rn / "out", "--report", rreport, cwd=rn)
        got = (rn / "out" / "job.x").read_text()
        check("edit: a name the code never sets, and a name the code never reads, are not renamed",
              code == 3 and "never gives Event_Handle a value" in out and "nothing in this code reads Out_Record" in out
              and "jobState = Lookup(Event_Handle);" in got and "Out_Record = jobState;" in got, out + err + got)

        # a defect in a value that nothing uses: said in the row, and never rated above Low
        nu = tmp / "unused"
        write(nu / "job.x", "queue = \"ORDERS_UAT\";\nlabel = '<b>' + @Name + '<b>';\nsend(label);\n")
        nrep = nu / "review.md"
        run("write_register.py", nu / "job.x", "--out", nrep, cwd=nu)
        nnotes = notes_for(nrep)
        body = nnotes.read_text()
        check("review: an environment name in a value that nothing uses is a question for the owner, written by the script",
              "Decision: ?" not in body and "which nothing in this code uses. Is the assignment still needed?" in nrep.read_text(),
              body[:600] + nrep.read_text()[-600:])
        body = body.replace("## Lines read\n", "## Lines read\n1-3\n", 1).replace(
            "## Questions for the owner\n", "## Verdict\nThe sample has 3 defects, 2 of them High.\n\n## Questions for the owner\n", 1).replace(
            "## Coverage of the intent\n", "none\n\n## Coverage of the intent\n", 1).replace(
            "column:\n", "column: Effect on the order\n", 1)
        body = re.sub(r"^(Tag opened and closed a different number of times):$", r"\1: none found", body, flags=re.M)
        body = re.sub(r"^(Name assigned, never read|Environment name, address or credential in a string):$",
                      r"\1: The order is sent to the wrong queue.", body, flags=re.M)
        nnotes.write_text(body)
        code, out, err = run("write_register.py", nu / "job.x", "--out", nrep, cwd=nu)
        check("review: a verdict that holds counts is refused", code == 3 and "The verdict holds a count (\"3 defects\")" in out, out + err)
        check("review: an effect line that says none for a kind that has rows is refused",
              "says there are none, and the report has 1 row(s) of that kind" in out, out + err)
        nrows = table_rows(nrep.read_text())
        check("review: a row whose value nothing uses is Low, says so where it lands, and its effect is none",
              any(r["Severity"] == "Low: the value is not used" and "which nothing in this code uses" in r["Where it lands"]
                  and r["Effect on the order"] == "None in this code: nothing uses `queue`." for r in nrows
                  if r["Kind"].startswith("Environment name")), str(nrows))

        # a value replaced before it is read, and a replacement made twice
        dz = tmp / "discard"
        write(dz / "msg.x", "if (@Kind == 1) {\n    text = \"a\" + @Name;\n    text = text + \"b\";\n}\n"
                            "text = \"start\";\nbody = Replace(body, \"&\", \"&amp;\", 5);\n"
                            "if (@Kind == 2) {\n    other = 1;\n} else {\n    other = 2;\n}\n"
                            "i = 0;\nwhile (i < 3) {\n    i = i + 1;\n}\ni = 0;\n"
                            "body = Replace(body, \"&\", \"&amp;\", 5);\nsend(text, body, other, i);\n")
        code, out, err = run("scan_code.py", dz / "msg.x", cwd=dz)
        check("scan: a value built in a block and replaced after it, before anything reads it, is reported",
              re.search(r"^\s+1\s+Value replaced before it is read\s*$", out, re.M)
              and "text — set on lines 2-3, replaced here before anything reads it" in out, out)
        check("scan: two branches of one condition, and a counter set again after its loop, are not reported",
              "other —" not in section(out, "Value replaced before it is read")
              and "i —" not in section(out, "Value replaced before it is read"), out)
        check("scan: a replacement that puts back what it looks for, made twice on one value, is reported",
              re.search(r"^\s+1\s+Replacement made twice on the same value\s*$", out, re.M) and "on line 6 and again here" in out, out)
        # a review started under another report name: its notes are taken over by the report the user asked for
        ad = tmp / "adopt"
        write(ad / "job.x", "if (@A = 1) {\n    send(@A, missing);\n}\n")
        run("write_register.py", ad / "job.x", "--out", ad / "reports" / "review.md", cwd=ad)
        first_notes = notes_for(ad / "reports" / "review.md")
        first_notes.write_text(re.sub(r"Decision: \?", "Decision: finding", first_notes.read_text()).replace(
            "## Coverage of the intent\n", "### line 2\nseverity: Low\ncode: send(@A, missing)\nwhat: the name missing is never set\n"
            "fix: set it\nconfidence: proven\n\n## Coverage of the intent\n", 1).replace(
            "## Lines read\n", "## Lines read\n1-3\n", 1).replace(
            "## Questions for the owner\n", "## Questions for the owner\n- Is R-01 what was meant?\n", 1))
        code, out, err = run("write_register.py", ad / "job.x", "--out", ad / "reports" / "wanted.md", cwd=ad)
        wanted = (ad / "reports" / "wanted.md").read_text() if (ad / "reports" / "wanted.md").exists() else ""
        check("review: run again under the name the user asked for, the notes are taken over and the earlier report goes",
              code == 0 and "Gate: passed" in out and "this report replaces review.md" in out
              and notes_for(ad / "reports" / "wanted.md").exists() and not first_notes.exists()
              and not (ad / "reports" / "review.md").exists(), out + err)
        check("review: the reviewer's number for a finding that joined a scan row is replaced by that row's ID",
              re.search(r"Is S-\d+ what was meant\?", wanted) and "Is R-01" not in wanted, wanted[-500:])
        check("review: the last lines name the report to hand over and say not to write another",
              "The report to hand over is" in out and out.rstrip().endswith("Gate: passed"), out)

        # ---- what is the owner's to decide is proposed, not applied
        pr = tmp / "proposals"
        write(pr / "job.x", "mode = 'batch';\nkind = 'batch';\nif (a == 1 && b == 2 || c == 3) {\n    out = '<q>' + region + '</q>';\n}\n"
                            "tag = '<r>' + batch + '</r>';\nelse_value = limit;\nsend(mode, kind, out, tag, else_value, total);\n")
        prep, plog = pr / "review.md", pr / "log.md"
        run("write_register.py", pr / "job.x", "--out", prep, cwd=pr)
        ptext = prep.read_text()
        prow = {r["Line"]: r for r in table_rows(ptext)}
        check("scan: a word written without quotes, which the code writes as text elsewhere, is corrected by the script",
              "6" in prow and prow["6"]["Decision"] == "Finding" and "`tag = '<r>' + 'batch' + '</r>';`" in prow["6"]["Fix: the line after the fix"],
              ptext[:1500])
        check("scan: a condition that mixes && and || is a question for the owner",
              prow["3"]["Decision"] == "Finding, to be confirmed by the owner" and "Which parts belong together?" in ptext, str(prow.get("3")))
        body = notes_for(prep).read_text()
        body = re.sub(r"Decision: \?", "Decision: finding", body).replace("## Coverage of the intent\n", "none\n\n## Coverage of the intent\n", 1)
        body = body.replace("## Lines read\n", "## Lines read\n1-8\n", 1).replace("## Verdict\n", "## Verdict\nThe sample is not ready.\n", 1)
        notes_for(prep).write_text(body)
        code, out, err = run("write_register.py", pr / "job.x", "--out", prep, cwd=pr)
        check("proposals: the review of the sample passes its gate", code == 0 and "Gate: passed" in out, out + err)
        pargs = ("run.py", "fix", pr / "job.x", "--out", pr / "fixed", "--log", plog, "--register", prep)
        code, out, err = run(*pargs, cwd=pr)
        pnotes = notes_for(plog).read_text()
        check("fix: the open High findings are left to the owner in the notes as they stand",
              re.search(r"^S-\d+: Nothing in this code sets region, which line 4 reads\. Which value is meant there\?$", pnotes, re.M), pnotes[-900:])
        notes_for(plog).write_text(pnotes.replace("## Left for the owner\n", (
            "### line 4\nafter: out = '<q>' + mode + '</q>';\nwhy: mode is the nearest value that is set, so it is used for the region.\n\n"
            "### line 3\nafter: if (a == 1 && (b == 2 || c == 3)) {\nwhy: the two last tests belong together, as the layout suggests.\n\n"
            "### line 7\nafter: else_value = 0;\nwhy: a default is safer than an unset limit; the owner should confirm.\nowner: Is 0 the right limit?\n\n"
            "## Left for the owner\n"), 1))
        code, out, err = run(*pargs, cwd=pr)
        fixed = (pr / "fixed" / "job.x").read_text()
        check("fix: a value put in the place of an unset name, a grouping the review left to the owner, and a correction "
              "that asks the owner are proposals and are not applied",
              "3 correction(s) of your notes are the owner's to decide" in out and "'<q>' + region + '</q>'" in fixed
              and "a == 1 && b == 2 || c == 3" in fixed and "else_value = limit;" in fixed
              and "## Proposed, not applied: for the owner to confirm" in plog.read_text() and "Gate: passed" in out, out + err)
        id3 = prow["3"]["ID"]
        notes_for(plog).write_text(pnotes.replace("## Left for the owner\n", (
            "### line 7\nafter: else_value = 0;\nwhy: a default is safer than an unset limit; the owner should confirm.\n"
            "owner: Is 0 the right limit?\nfor: %s\n\n"
            "### line 3\nafter: if (a == 1 && (b == 2 || c == 3)) {\nwhy: the two last tests belong together, as the layout suggests.\n\n"
            "## Left for the owner\n") % id3, 1))
        code, out, err = run(*pargs, cwd=pr)
        check("fix: \"for:\" naming a finding whose own line has a correction of its own is refused",
              "\"for: %s\" names the finding on line 3, which has a correction of its own" % id3 in out
              and "Gate: passed" not in out, out + err)
        notes_for(plog).write_text("## Corrections\n### line 1\nafter: mode = 'batch' + later;\nwhy: test of a correction that reads "
                                   "a name before it is set, which adds a defect.\n### after line 9\n\n## Left for the owner\n"
                                   + "\n".join(re.findall(r"^S-\d+: .*$", pnotes, re.M)) + "\n")
        write(pr / "job.x", (pr / "job.x").read_text() + "later = 1;\n")
        code, out, err = run("fix_code.py", pr / "job.x", "--out", pr / "fixed2", "--log", pr / "log2.md", cwd=pr)
        write(notes_for(pr / "log2.md"), "## Corrections\n### line 1\nafter: mode = 'batch' + later;\nwhy: test of a correction that "
                                         "reads a name before the line that sets it.\n")
        code, out, err = run("fix_code.py", pr / "job.x", "--out", pr / "fixed2", "--log", pr / "log2.md", cwd=pr)
        check("fix: a correction whose new line adds a scan hit is refused",
              code == 3 and "adds a defect that was not there: Name read before the line that first sets it" in out, out + err)
        sw = tmp / "switched"
        write(sw / "job.x", "if (level == 3) {\n    log(\"dropping\");\n    // drop();\n    log(\"kept for a test\");\n}\nsend(level);\n")
        code, out, err = run("fix_code.py", sw / "job.x", "--out", sw / "fixed", "--log", sw / "log.md", cwd=sw)
        write(notes_for(sw / "log.md"), "## Corrections\n### lines 3-4\nafter:\n```\ndrop();\n```\nwhy: the block says it drops the "
                                        "event, so the switched-off call is put back and the test log taken out.\n")
        code, out, err = run("fix_code.py", sw / "job.x", "--out", sw / "fixed", "--log", sw / "log.md", cwd=sw)
        swlog = (sw / "log.md").read_text() if (sw / "log.md").exists() else ""
        check("fix: switching a commented-out line back on is a proposal for the owner, not applied",
              "owner's to decide" in out and "// drop();" in (sw / "fixed" / "job.x").read_text()
              and "was switched off in the code (commented out)" in swlog, out + err + swlog[-800:])

        # ---- code whose variables carry a prefix, with tables in files that it includes
        inc = tmp / "includes"
        write(inc / "tables" / "levels.tbl", 'table Levels =\n{\n {"1","low"},\n {"2","high"}\n}\n')
        write(inc / "route.rules", 'include "/opt/app/etc/tables/levels.tbl"\ninclude "/opt/app/etc/absent.tbl"\n'
                                   'table Nearby = "/opt/app/etc/local.tbl"\narray parts;\n# a comment\n'
              + "".join("$v%d = @in%d\n" % (k, k) for k in range(1, 23))
              + '%count = 1\n%count2 = 2\n$n = split($v1, parts, ":")\n@Level = lookup($v2, Levels)\n'
                '@Other = lookup($v3, Nowhere)\n@Stamp = getdate\nlog(DEBUG, "seen " + $v4)\n'
                'if (match($v5, "a")) {\n    discard\n}\n@Key = parts[1] + lookup($n, Nearby)\n')
        code, out, err = run("scan_code.py", inc / "route.rules", cwd=inc)
        check("scan: in code whose variables carry a prefix, a declared array, a table of an included file, a log level and "
              "the words of the language are not names that were never set; a table that nothing defines is",
              re.search(r"^\s+1\s+Name read, never assigned\s*$", out, re.M) and "Nowhere — read on line 32" in out
              and not re.search(r"\b(Levels|parts|DEBUG|discard|getdate|Nearby|table) — read", out), out + err)
        check("scan: a name with % first on its line keeps its prefix", "count2" not in out, out)
        code, out, err = run("write_register.py", inc / "route.rules", "--out", inc / "review.md", cwd=inc)
        itext = (inc / "review.md").read_text() if (inc / "review.md").exists() else ""
        check("review: the report names the included file whose names were used, and the one that was not given",
              "| Names defined in an included file | levels.tbl | 1 names defined |" in itext
              and "- Line 2 includes `/opt/app/etc/absent.tbl`, which is not among the files given" in itext, itext[-1500:] + out + err)
        write(inc / "flat.x", "a = 1;\nb = a + 2;\nc = spare;\nsend(b, c);\n")
        code, out, err = run("scan_code.py", inc / "flat.x", cwd=inc)
        check("scan: in code whose variables carry no prefix, a word that is never set is still reported",
              "spare — read on line 3" in out, out)

        # ---- added with the notes flow: what the first real runs and the dry run asked for
        extra = tmp / "extra"
        code_file = extra / "order.x"
        write(code_file, "@Qty = Trim(@Qty);\n"
                         "total = @Price * @Qty;\n"
                         "if (@Status = 'open') {\n"
                         "    label = Replace(@Label, \"&\", \"and\", 10);\n"
                         "    msg = '<note>' + label + '<note>';\n"
                         "}\n"
                         "send(total, msg, extraName);\n")
        code, out, err = run("scan_code.py", code_file, cwd=extra)
        check("scan: data given to the code that is assigned is reported, once per name",
              re.search(r"^\s+1\s+Data from outside the code is changed\s*$", out, re.M) and "@Qty — assigned on line 1" in out, out)
        check("scan: a replace call limited to a count is reported",
              re.search(r"^\s+1\s+Replace limited to a count\s*$", out, re.M) and "limited to 10 replacements — on line 4" in out, out)
        report = extra / "reports" / "review.md"
        code, out, err = run("run.py", "review", code_file, "--out", report, cwd=extra)
        check("review: the first run of the command ends with exit code 0", code == 0 and "expected on the first run" in out, out + err)
        notes = notes_for(report)
        skeleton = notes.read_text()
        check("review: the notes say which lines already have a scan row, and the rows of each kind",
              re.search(r"Lines that already have a scan row: [\d, -]*\b3\b", skeleton)
              and re.search(r"<!-- 1 row\(s\): lines 3 -->\nAssignment in a condition:", skeleton), skeleton[-1500:])
        open_ids = re.findall(r"^- (S-\d+), line", skeleton, re.M)
        filled = re.sub(r"Decision: \?", "Decision: finding, Low: nothing else reads it", skeleton)
        filled = filled.replace("## Coverage of the intent\n", (
            "### line 3\nseverity: High\ncode: @Status = 'open'\nkind: wrong operator\n"
            "what: restates the scan row with the same corrected line\nfix: if (@Status == 'open') {\nconfidence: proven\n\n"
            "### line 5\nseverity: High\ncode: '<note>' + label\nkind: markup\n"
            "what: the tag is written twice, the second one was meant to close the first\nfix: close it\nconfidence: proven\n\n"
            "### line 2\nseverity: High\ncode: @Price * @Qty\nkind: arithmetic\n"
            "what: the total is computed before the quantity is validated\nfix: validate first\nconfidence: needs a test\n\n"
            "## Coverage of the intent\n"), 1)
        filled = filled.replace("## Lines read\n", "## Lines read\n1-7\n", 1).replace(
            "## Verdict\n", "## Verdict\nThe sample has the defects the scan lists and one more from reading.\n", 1)
        notes.write_text(filled)
        code, out, err = run("run.py", "review", code_file, "--out", report, cwd=extra)
        text = report.read_text()
        rows = table_rows(text)
        check("review: a finding from reading that gives the corrected line of a scan row is added to that row",
              code == 0 and "Gate: passed" in out and "2 more restate a scan row" in out
              and sum(1 for r in rows if r["ID"].startswith("R-")) == 1
              and any("Reviewer: restates the scan row" in r["What it does"] for r in rows if r["ID"].startswith("S-")), out + err)
        check("review: the finding that is new keeps its own row, numbered R-01",
              any(r["ID"] == "R-01" and r["Line"] == "2" for r in rows), str([(r["ID"], r["Line"]) for r in rows]))
        check("review: a decision can give the severity", bool(open_ids)
              and all(r["Severity"] == "Low" for r in rows if r["ID"] in open_ids), str([(r["ID"], r["Severity"]) for r in rows]))
        check("review: the changed data and the limited replace are questions for the owner, written by the script",
              "Which of them are meant to be stored" in text and "stop after a fixed number of replacements" in text, text[-900:])
        # the fix: a correction can name the finding it closes, and the command prints a short comparison
        log = extra / "reports" / "log.md"
        fix_args = ("run.py", "fix", code_file, "--out", extra / "fixed", "--log", log, "--register", report)
        code, out, err = run(*fix_args, cwd=extra)
        check("fix: the first run of the command ends with exit code 0", code == 0 and "Gate: not passed yet" in out, out + err)
        check("fix: the comparison printed by the command leaves out the list of changed lines",
              "5. Places where lines differ" in out and "- if (@Status = 'open') {" not in out
              and "Assignment in a condition" in out, out)
        todo = re.findall(r"^\s+([SR]-\d+)  line", out, re.M)
        fnotes = notes_for(log)
        body = fnotes.read_text().replace("## Left for the owner\n", (
            "### line 2\nkind: arithmetic\nafter: total = @Price * Valid(@Qty);\n"
            "why: the quantity is validated where it is used; for a quantity of -1 the total was negative and is now 0. "
            "The call `Valid` is new and needs a test.\n\n## Left for the owner\n"
            + "".join("%s: Which value is meant here?\n" % i for i in todo if i != "R-01")), 1)
        fnotes.write_text(body)
        code, out, err = run(*fix_args, cwd=extra)
        logtext = log.read_text()
        check("fix: a correction that names a finding on another line with \"for:\" closes it",
              "R-01" not in re.findall(r"^\s+([SR]-\d+)  line", out, re.M) and "NOT DECIDED" not in logtext, out + err)
        check("fix: the change log says what each correction of the script changes when the code runs",
              "The condition now compares instead of assigning" in logtext, logtext[:1500])
        check("fix: a call new to the code is settled once the notes name it", code == 0 and "Gate: passed" in out, out + err)
        # two names used once each that share a numbered stem are both candidates; a series in use is not
        write(extra / "series.x", "a = @Line1 + @Line1 + @Line2 + @Line2;\nb = @Lime3;\nc = @Colour1 + @Colour1;\nd = @Coluor2;\n"
                                  "e = @Size + @Size;\nf = @Sise;\nsend(a, b, c, d, e, f);\n")
        code, out, err = run("scan_code.py", extra / "series.x", cwd=extra)
        once = section(out, "Name used once, close to another name")
        check("scan: a misspelt name is a candidate; a numbered name whose series is in use is not",
              "@Sise" in once and "@Line2" not in once and "@Line1" not in once, once + out[:300])

        # ---- a workspace that holds two bodies of code, each in its own folder with its own document
        two = tmp / "two"
        write(two / "billing" / "inputs" / "fields.src", FIELDS_CODE)
        write(two / "billing" / "inputs" / "fields.md", FIELDS_DOC)
        write(two / "routing" / "inputs" / "route.x", "a = @Node + @Node;\nsend(a);\n")
        write(two / "routing" / "inputs" / "standards.txt", "The routing code keeps the node.\n")
        write(two / "routing" / "fixed" / "route.x", "a = @Node + @Node;\nsend(a);\n")
        write(two / "notes" / "shared.txt", "Conventions shared by both.\n")
        left = "document not used, because it sits with other code in the workspace: "
        code, out, err = run("run.py", "review", "routing/inputs/route.x", "--out", "routing/reports/review.md", cwd=two)
        skeleton = notes_for(two / "routing" / "reports" / "review.md").read_text()
        check("documents: the document of other code in the workspace is not used, and the command says so",
              ok_run(code, out, err) and "Names checked against" not in out and left + "billing/inputs/fields.md" in out, out + err)
        check("documents: the notes name the document next to the code and one in a folder that holds no code",
              "standards.txt" in skeleton and "shared.txt" in skeleton and "fields.md" not in skeleton,
              "\n".join(x for x in skeleton.split("\n") if "document" in x))
        code, out, err = run("run.py", "review", "billing/inputs/fields.src", "--out", "billing/reports/review.md", cwd=two)
        check("documents: the other body of code keeps its own list of names",
              "Names checked against the 7 names listed in billing/inputs/fields.md" in out
              and left + "routing/inputs/standards.txt" in out, out + err)
        code, out, err = run("scan_code.py", "routing/fixed", cwd=two)
        check("documents: a copy of the code in the same folder of the workspace is treated as the original is",
              left + "billing/inputs/fields.md" in out, out + err)
        one = tmp / "one"
        write(one / "inputs" / "fields.src", FIELDS_CODE)
        write(one / "inputs" / "fields.md", FIELDS_DOC)
        write(one / "fixed" / "fields.src", FIELDS_CODE)
        code, out, err = run("run.py", "review", "fixed/fields.src", "--out", "reports/review.md", cwd=one)
        check("documents: with one body of code, a copy in a folder with no document uses the document of the original",
              "Names checked against the 7 names listed in inputs/fields.md" in out and left not in out, out + err)

        # ---- a split of several earlier files into small files
        sp = tmp / "split"
        write(sp / "src" / "main.rules", "\n".join(
            ["# rules for the node"] + ["@Field%d = $in%d" % (i, i) for i in range(1, 26)]
            + ["# example = \"text in a comment\"", "if (match(@Field1, \"down\"))", "{", "    discard", "}",
               "@Last = \"kept\""]) + "\n")
        write(sp / "src" / "tables.rules", "# tables\ntable t1 = \"a.lookup\"\ntable t2 = \"b.lookup\"\n")
        sargs = ("run.py", "edit", "src", "--out", "out", "--report", "reports/split.md", "--map", "reports/map.md")
        run(*sargs, cwd=sp)
        plan = notes_for(sp / "reports" / "split.md")
        skeleton = plan.read_text()
        check("split: the plan file says how to name the earlier file and how to write a file with no earlier line",
              "lines: rules.js: 1-57, 3100-3338" in skeleton and "holds no earlier line" in skeleton, skeleton[-1500:])
        head, tail = skeleton[:skeleton.index("## Files")], skeleton[skeleton.index("## Explanations"):]
        why = "why: the requirement asks for one file for each stage; every line keeps its place in the order\n\n"
        blocks = ("### stage/first.rules\nlines: main.rules: 1-27\n" + why
                  + "### stage/discard.rules\nlines: main.rules:28-30, main.rules:31-32\n" + why
                  + "### config/tables.rules\nlines: tables.rules: all\n" + why)
        empty = "### stage/empty_stage.rules\nprepend:\n```\n# no rule of this stage exists in the earlier code\n```\n" + why
        tail = tail.replace("## Verdict", "stage/first.rules, stage/discard.rules, config/tables.rules, stage/empty_stage.rules "
                            "and stage/nothing.rules are read by the entry file of the platform, which is not in this code.\n\n## Verdict", 1)
        plan.write_text(head + "## Files\n\n" + blocks + empty + tail)
        code, out, err = run(*sargs, cwd=sp)
        check("split: ranges that name their earlier file, a whole file and a file with no earlier line are written",
              code == 0 and "Gate: passed" in out and (sp / "out" / "config" / "tables.rules").read_text()
              == (sp / "src" / "tables.rules").read_text() and (sp / "out" / "stage" / "empty_stage.rules").read_text()
              == "# no rule of this stage exists in the earlier code\n", out + err)
        check("split: a small file is read as the other files of its type are (comments, words of the language)",
              "0 used more times, 0 new" in out and "never assigned" not in out, out + err)
        plan.write_text(head + "## Files\n\n" + blocks + "### stage/nothing.rules\n" + why + tail)
        code, out, err = run(*sargs, cwd=sp)
        check("split: a file block with no line and no content is refused, not a fault of the script",
              ok_run(code, out, err) and "the file would be empty" in out and "Gate: passed" not in out, out + err)
        plan.write_text(head + "## Files\n\n" + blocks.replace("tables.rules: all", "other.rules: 1-3") + tail)
        code, out, err = run(*sargs, cwd=sp)
        check("split: a range that names a file that is not one of the earlier files is refused",
              ok_run(code, out, err) and "other.rules is not one of the earlier files" in out, out + err)

        # ---- split: the order of the lines, whole blocks in each file, every file read by another
        hs = tmp / "handover"
        write(hs / "src" / "main.rules", "# header\n@A = 1\nif (match(@K, \"x\"))\n{\n    @B = 2\n    @C = 3\n}\n@Z = 9\n")
        hargs = ("run.py", "edit", "src", "--out", "out", "--report", "reports/split.md")
        run(*hargs, cwd=hs)
        hplan = notes_for(hs / "reports" / "split.md")
        hskel = hplan.read_text()
        hhead, hmid = hskel[:hskel.index("## Corrections")], hskel[hskel.index("## Renames"):hskel.index("## Files")]
        htail = hskel[hskel.index("## Explanations"):].replace(
            "## Verdict", "The string \"body.rules\" is the name of the new file in the line that reads it; `include` is the "
            "statement that reads it and needs a test.\n\n## Verdict", 1)
        hwhy = "why: the requirement asks for the body in a file of its own; the statements keep their order\n\n"
        late = ("## Corrections\n" + hmid + "## Files\n### master.rules\nlines: 1-2, 8\nappend:\n```\ninclude \"body.rules\"\n```\n"
                + hwhy + "### body.rules\nlines: 3-7\n" + hwhy)
        hplan.write_text(hhead + late + htail)
        code, out, err = run(*hargs, cwd=hs)
        check("split: lines that read another file, appended after lines that used to follow that file's lines, are refused",
              code == 3 and "its \"append:\" lines come after its last range, but lines 3-7" in out
              and "\"### after line 2\"" in out and "Gate: passed" not in out, out + err)
        cut = ("## Corrections\n### after line 2\ninsert:\n```\ninclude \"body.rules\"\ninclude \"rest.rules\"\n```\n" + hwhy + hmid
               + "## Files\n### master.rules\nlines: 1-2, 8\n" + hwhy + "### body.rules\nlines: 3-5\n" + hwhy
               + "### rest.rules\nlines: 6-7\n" + hwhy)
        hplan.write_text(hhead + cut + htail.replace("## Verdict", "body.rules:3 and rest.rules:2 hold the two halves of one block, "
                                                     "which is read in one piece; \"rest.rules\" is the second file.\n\n## Verdict", 1))
        code, out, err = run(*hargs, cwd=hs)
        check("split: a block cut in two between files is listed as a broken file, and no explanation settles it",
              code == 3 and "TO SETTLE  Files the change left broken" in out and "Brackets that do not balance" in out, out + err)
        orphaned = ("## Corrections\n" + hmid + "## Files\n### master.rules\nlines: 1-2, 8\n" + hwhy + "### body.rules\nlines: 3-7\n" + hwhy)
        hplan.write_text(hhead + orphaned + hskel[hskel.index("## Explanations"):])
        code, out, err = run(*hargs, cwd=hs)
        check("split: a file of the result that no other file names is listed",
              code == 3 and "nothing in the result reads body.rules" in out, out + err)
        good = ("## Corrections\n### after line 2\ninsert:\n```\ninclude \"body.rules\"\n```\n" + hwhy + hmid
                + "## Files\n### master.rules\nlines: 1-2, 8\n" + hwhy + "### body.rules\nlines: 3-7\n" + hwhy)
        hplan.write_text(hhead + good + htail)
        code, out, err = run(*hargs, cwd=hs)
        check("split: with the line that reads the next file put where its lines stood, the order is kept and the gate passes",
              code == 0 and "Gate: passed" in out
              and (hs / "out" / "master.rules").read_text() == "# header\n@A = 1\ninclude \"body.rules\"\n@Z = 9\n", out + err)
        write(hs / "src" / "tables.rules", "table t1 = \"a.lookup\"\n")
        code, out, err = run("run.py", "edit", "src/main.rules", "--out", "out2", "--report", "reports/split.md", cwd=hs)
        check("split: one file of a folder given as the code, with other files beside it, is refused",
              code == 3 and "is one file of src, which holds 1 more: tables.rules" in out, out + err)

        # ---- fix: a finding left to the owner with the question as the script wrote it is not settled
        gq = tmp / "asked"
        write(gq / "job.x", "@Total = @Price * @Qty;\nif (@Kind == 1) {\n    @Total = @Total;\n}\nsend(@Total);\n")
        run("run.py", "review", "job.x", "--out", "reports/review.md", cwd=gq)
        gargs = ("run.py", "fix", "job.x", "--out", "fixed", "--log", "reports/log.md", "--register", "reports/review.md")
        run(*gargs, cwd=gq)
        gnotes = notes_for(gq / "reports" / "log.md")
        code, out, err = run(*gargs, cwd=gq)
        check("fix: notes left as the command wrote them do not pass: the question of the script is not a decision",
              code == 3 and "with the question as the script wrote it: 1" in out and "Gate: passed" not in out, out + err)
        gnotes.write_text(re.sub(r"(S-\d+: ).*What should the code do there\?",
                                 r"\1Is the total meant to be reset here, or is the line left over from an edit?",
                                 gnotes.read_text()))
        code, out, err = run(*gargs, cwd=gq)
        check("fix: a finding left to the owner with a question of the reader's own passes",
              code == 0 and "Gate: passed" in out and "as the script wrote it" not in out, out + err)

        # ---- status: where the work in a workspace stands, read from what the commands recorded
        code, out, err = run("run.py", "status", cwd=gq)
        check("status: lists each task started, says which gate passed, and gives the command of the one that did not",
              code == 3 and re.search(r"NOT PASSED\s+review\s+reports/review\.md", out)
              and re.search(r"passed\s+fix\s+reports/log\.md", out) and "run.py review job.x --out reports/review.md" in out
              and "Gate: not passed yet. 1 task(s)" in out, out + err)
        (gq / ".code-review-tasks.json").unlink()
        code, out, err = run("run.py", "status", cwd=gq)
        check("status: a task started before the record existed is found by its notes file and shown as not known",
              code == 3 and re.search(r"not known\s+fix\s+reports/log\.md", out), out + err)
        bare = tmp / "bare"
        bare.mkdir()
        code, out, err = run("run.py", "status", cwd=bare)
        check("status: a workspace where nothing was started passes", code == 0 and "No task has been started" in out, out + err)

        # ---- change: a character outside ASCII that the earlier version does not hold is listed by the gate
        na = tmp / "ascii"
        write(na / "job.x", "@Total = @Price * @Qty;\nlog(\"total: \" + @Total);\nsend(@Total);\n")
        nargs = ("run.py", "edit", "job.x", "--out", "out", "--report", "reports/tidy.md")
        run(*nargs, cwd=na)
        nplan = notes_for(na / "reports" / "tidy.md")
        nskel = nplan.read_text()
        block = ("### line 2\nafter: log(\"job — total: \" + @Total);\n"
                 "why: the requirement asks for the name of the job at the start of each log line; the value logged is the same\n\n")
        at_ = nskel.index("## Renames")
        nplan.write_text(nskel[:at_] + block + nskel[at_:])
        code, out, err = run(*nargs, cwd=na)
        check("change: a character outside ASCII that is new to the code is listed, and the gate does not pass",
              ok_run(code, out, err) and "Characters outside ASCII" in out and "U+2014" in out and "Gate: passed" not in out,
              out + err)
        nplan.write_text(nskel[:at_] + block.replace("—", "-") + nskel[at_:])
        code, out, err = run(*nargs, cwd=na)
        check("change: the same line written with a plain hyphen passes",
              code == 0 and "Gate: passed" in out and "Characters outside ASCII" not in out, out + err)

        # ---- a rule accounts for the strings it rewrote: nothing to name by hand
        rl = tmp / "ruled"
        write(rl / "job.rules", "# tables\ntable a = \"/opt/x/one.lookup\"\ntable b = \"/opt/x/two.lookup\"\n"
                                "include \"/opt/x/three.rules\"\n@A = 1\n")
        largs = ("run.py", "edit", "job.rules", "--out", "out", "--report", "reports/paths.md")
        run(*largs, cwd=rl)
        lplan = notes_for(rl / "reports" / "paths.md")
        lplan.write_text(lplan.read_text().replace("## Renames", "### rule prefix\nmatch: /opt/x\nwith: $HOME_DIR\n"
                         "why: the requirement asks for the variable in place of the fixed folder; folder and file names stay\n\n## Renames", 1))
        code, out, err = run(*largs, cwd=rl)
        ltext = (rl / "reports" / "paths.md").read_text()
        check("rule: the strings a rule rewrote are listed in the report and need no explanation by hand",
              code == 0 and "Gate: passed" in out and "1 rule(s) changed 3 line(s)" in out
              and "- rule prefix, line 2: the string \"/opt/x/one.lookup\" became \"$HOME_DIR/one.lookup\"" in ltext, out + err)

        # ---- commented-out code: a statement switched off, the signs of a block, and what is only an example
        cc = tmp / "commented"
        write(cc / "job.rules", "# rules\n" + "".join("@F%d = $v%d\n" % (i, i) for i in range(1, 24))
              + "if (match(@F1, \"x\"))\n{\n    discard\n}\n#discard\n## example = \"value\"\n# sample = \"value\"\n#@F2 = 5\n")
        code, out, err = run("inventory.py", cc / "job.rules", cwd=cc)
        listed = out.split("Comment lines that look like code:", 1)[1] if "Comment lines that look like code:" in out else ""
        check("commented-out code: a bare statement the code uses and an assignment to a variable of the code are listed",
              listed.strip().startswith("2") and "#discard" in listed and "#@F2 = 5" in listed, out + err)
        check("commented-out code: an example after a doubled sign, or with a name that carries no prefix, is not listed",
              "example" not in listed.split("\n\n")[0] and "sample" not in listed.split("\n\n")[0], listed[:600])
        write(cc / "job.x", "a = 1;\n/*\nb = 2;\nc = 3;\n*/\nsend(a);\n")
        code, out, err = run("inventory.py", cc / "job.x", cwd=cc)
        listed = out.split("Comment lines that look like code:", 1)[1] if "Comment lines that look like code:" in out else ""
        check("commented-out code: the signs that open and close a block of code are listed with it",
              listed.strip().startswith("4"), out + err)
        cu = tmp / "cleanup"
        write(cu / "job.x", "a = 1;\n// old way\n//b = 2;\n// the total of a\nsend(a);\n// 12/3(a=1) or example\nc = fetch(a);\n")
        cargs = ("run.py", "edit", "job.x", "--out", "out", "--report", "reports/clean.md")
        run(*cargs, cwd=cu)
        cplan = notes_for(cu / "reports" / "clean.md")
        cskel = cplan.read_text()
        check("commented-out code: a comment that starts with a number is an example of values, not code",
              "commented-out code): 1, on lines 3" in cskel, cskel[-600:])
        cplan.write_text(cskel.replace("## Renames", "### lines 2-4\nremove: yes\nwhy: commented-out code, as the requirement asks.\n\n"
                                       "### line 6\nremove: yes\nwhy: commented-out code, as the requirement asks.\n\n## Renames", 1))
        code, out, err = run(*cargs, cwd=cu)
        check("clean-up: a removed comment right above a live line that stays explains that line and is refused",
              code == 3 and "line(s) 4 are a comment, not commented-out code, and stand right above line 5" in out
              and "line(s) 6 are a comment, not commented-out code, and stand right above line 7" in out, out + err)
        cplan.write_text(cskel.replace("## Renames", "### lines 2-3\nremove: yes\nwhy: commented-out code with the comment that "
                                       "introduces it, as the requirement asks.\n\n## Renames", 1))
        code, out, err = run(*cargs, cwd=cu)
        check("clean-up: a comment that introduces the commented-out code removed with it is not refused",
              "stand right above line" not in out, out + err)

        # ---- renames: a name the code reads before it gives it a value comes from outside, and keeps its name
        rn2 = tmp / "readfirst"
        write(rn2 / "job.x", "My_Source = lookup(My_Source);\nmy_total = 1 + fetch(My_Source);\nsend(my_total);\n")
        r2args = ("run.py", "edit", "job.x", "--out", "out", "--report", "reports/names.md")
        run(*r2args, cwd=rn2)
        r2plan = notes_for(rn2 / "reports" / "names.md")
        r2skel = r2plan.read_text()
        check("renames: a name read before the line that first sets it is listed as not renamed",
              "the code reads them before the line that first gives them" in r2skel and "My_Source" in r2skel.split("the code reads them before")[1][:200],
              r2skel[:2500])
        r2plan.write_text(r2skel.replace("## Files", "My_Source -> mySource\nmy_total -> myTotal\n\n## Files", 1))
        code, out, err = run(*r2args, cwd=rn2)
        check("renames: asking to rename such a name is refused, with the reason",
              code == 3 and "the code reads My_Source before the line that first gives it a value" in out, out + err)
        r2plan.write_text(r2skel.replace("## Files", "my_total -> myTotal\n\n## Files", 1))
        code, out, err = run(*r2args, cwd=rn2)
        check("renames: the report counts each line a rename changed once",
              code == 0 and "1 rename(s) on 2 line(s)" in out
              and (rn2 / "out" / "job.x").read_text() == "My_Source = lookup(My_Source);\nmyTotal = 1 + fetch(My_Source);\nsend(myTotal);\n",
              out + err)

        # ---- copy: a new item made like an existing one, wherever the model is, with only the replacements listed
        cp = tmp / "copied"
        page = ("<div>\n  <input id=\"bbb\"> BBB\n  <div onclick=\"show('F_BBB_Critical', 'Type = BBB')\" id=\"bbbCritical\"></div>\n</div>\n"
                "<div>\n  <input id=\"abbb\"> ABBB\n  <div onclick=\"show('F_ABBB_Critical', 'Type = ABBB')\" id=\"abbbCritical\"></div>\n</div>\n"
                "<script>\nfunction all(){\n  $j(\"#bbb\").prop('checked',true);\n  $j(\"#abbb\").prop('checked',true);\n}\n</script>\n")
        write(cp / "page.html", page)
        cargs2 = ("run.py", "edit", "page.html", "--out", "out", "--report", "reports/add.md")
        run(*cargs2, cwd=cp)
        cplan2 = notes_for(cp / "reports" / "add.md")
        cskel2 = cplan2.read_text()
        check("copy: the plan form shows how to make a new item like an existing one", "### copy sw1 as sw2" in cskel2, cskel2[:3000])
        good = "### copy bbb as ddd\nlines: 1-4\nreplace:\n  F_BBB_ -> F_DDD_\n  BBB -> DDD\nwhy: the owner asks for a device DDD made like BBB.\n\n"
        cplan2.write_text(cskel2.replace("## Renames", good + "## Renames", 1))
        code, out, err = run(*cargs2, cwd=cp)
        made = (cp / "out" / "page.html").read_text() if (cp / "out" / "page.html").exists() else ""
        check("copy: the block and every other line that names the model are copied right after themselves, with only "
              "the replacements, and the gate passes",
              code == 0 and "Gate: passed" in out
              and made == page.replace("</div>\n<div>\n  <input id=\"abbb\">",
                                       "</div>\n<div>\n  <input id=\"ddd\"> DDD\n  <div onclick=\"show('F_DDD_Critical', 'Type = DDD')\" "
                                       "id=\"dddCritical\"></div>\n</div>\n<div>\n  <input id=\"abbb\">", 1)
                                 .replace("  $j(\"#bbb\").prop('checked',true);\n",
                                          "  $j(\"#bbb\").prop('checked',true);\n  $j(\"#ddd\").prop('checked',true);\n", 1),
              out + err + made)
        cplan2.write_text(cskel2.replace("## Renames", good.replace("  F_BBB_ -> F_DDD_\n", "") + "## Renames", 1))
        code, out, err = run(*cargs2, cwd=cp)
        check("copy: a copy that still holds a name of the model is refused",
              code == 3 and "the copy of line 3 still holds \"BBB\"" in out, out + err)
        cplan2.write_text(cskel2.replace("## Renames", good.replace("BBB -> DDD", "BBB -> ABBB") + "## Renames", 1))
        code, out, err = run(*cargs2, cwd=cp)
        check("copy: a copy that would use a name the code already has is refused",
              code == 3 and "\"ABBB\" is already in the code (line 6)" in out, out + err)
        cplan2.write_text(cskel2.replace("## Renames", good.replace("lines: 1-4", "lines: 2-4") + "## Renames", 1))
        code, out, err = run(*cargs2, cwd=cp)
        check("copy: a block that closes a tag it does not open is refused",
              code == 3 and "lines 2-4 are not a whole block: </div> closed 1 more time(s) than opened" in out, out + err)
        bare = "### copy bbb as ddd\nlines: 1-4\nwhy: the owner asks for a device DDD made like BBB.\n\n"
        cplan2.write_text(cskel2.replace("## Renames", bare + "## Renames", 1))
        code, out, err = run(*cargs2, cwd=cp)
        check("copy: the model's name in another letter case is still the model's, and is refused in the copy",
              code == 3 and "the copy of line 2 still holds \"BBB\"" in out and "the copy of line 3 still holds" in out, out + err)
        cplan2.write_text(cskel2.replace("## Renames", good + good.replace("lines: 1-4", "lines: 10") + "## Renames", 1))
        code, out, err = run(*cargs2, cwd=cp)
        check("copy: a second block for the same model is refused, since one block copies every line that names it",
              code == 3 and "already copies bbb as ddd, with every line that names bbb" in out, out + err)
        sty = tmp / "styled"
        write(sty / "page.html", "<div id=\"aa\" style=\"margin-left:72px\">AA</div>\n"
                                 "<div id=\"bbbbbb\" style=\"margin-left:50px\">BBBBBB</div>\n"
                                 "<div id=\"cc\" style=\"margin-left:72px\">CC</div>\n")
        sargs = ("run.py", "edit", "page.html", "--out", "out", "--report", "reports/add.md")
        run(*sargs, cwd=sty)
        splan = notes_for(sty / "reports" / "add.md")
        sskel = splan.read_text()
        sblock = "### copy aa as dddddd\nlines: 1\nreplace:\n  AA -> DDDDDD\n%swhy: the owner asks for DDDDDD made like AA.\n\n"
        splan.write_text(sskel.replace("## Renames", sblock % "" + "## Renames", 1))
        code, out, err = run(*sargs, cwd=sty)
        check("copy: a style value that fits the name takes the value of the items whose name is as long as the new one's",
              code == 3 and "the model's margin-left:72px fits its own name; the items whose name is as long as the new "
              "one's use margin-left:50px" in out, out + err)
        splan.write_text(sskel.replace("## Renames", (sblock % "").replace("why:", "keep: margin-left:72px\nwhy:") + "## Renames", 1))
        code, out, err = run(*sargs, cwd=sty)
        check("copy: keeping the model's value is refused when the items with a name as long use another",
              code == 3 and "Put \"margin-left:72px -> margin-left:50px\" under \"replace:\"" in out, out + err)
        splan.write_text(sskel.replace("## Renames", sblock % "  margin-left:72px -> margin-left:50px\n" + "## Renames", 1))
        code, out, err = run(*sargs, cwd=sty)
        check("copy: with the value of an item with a name as long, the copy passes, sharing that style value",
              code == 0 and "Gate: passed" in out and "<div id=\"dddddd\" style=\"margin-left:50px\">DDDDDD</div>"
              in (sty / "out" / "page.html").read_text(), out + err)

        write(cp / "scan" / "page.html", "<html>\n<meta charset=\"utf-8\">\n<div onclick=\"pick('a')\">A</div>\n"
                                         "<script>\nfunction pick(x){\n  if (x = 'a') { show(x); }\n}\n</script>\n</html>\n")
        code, out, err = run("scan_code.py", cp / "scan" / "page.html", cwd=cp)
        check("scan: in a web page only the script and the event attributes are code, with the lines of the page",
              re.search(r"^\s*1\s+Assignment in a condition", out, re.M) and "line 6" in out
              and not re.search(r"^\s*[1-9]\d*\s+Function defined and never called", out, re.M), out + err)

        # ---- diagnose: from the symptom to the line, with the lines that name what it involves; nothing is changed
        dg = tmp / "diagnosed"
        dsrc = "@Kind = $kind\nif (@Kind = 5) {\n    @Summary = \"Disk full on \" + @Node\n}\nsend(@Summary)\n"
        write(dg / "job.x", dsrc)
        dargs = ("run.py", "diagnose", "job.x", "--out", "reports/diagnosis.md")
        code, out, err = run(*dargs, cwd=dg)
        dnotes = notes_for(dg / "reports" / "diagnosis.md")
        check("diagnose: the first run writes the notes with the form of a cause", code == 0 and dnotes.exists()
              and "### cause line 120" in dnotes.read_text() and "expected on the first run" in out, out + err)
        dform = dnotes.read_text().replace("## Symptom\n", "## Symptom\nEvery event shows the summary Disk full, whatever its kind.\n", 1) \
            .replace("## Look for\n", "## Look for\nDisk full\nKind\n", 1)
        cause = ("## Causes\n### cause line 2\nquote: @Kind = 5\nhow: the single = gives @Kind the value 5, so the condition holds "
                 "for every event and the summary is always Disk full\nstatus: shown: line 2 assigns where it should compare\n")
        dnotes.write_text(dform.replace("## Causes\n", cause.replace("quote: @Kind = 5", "quote: @Kind == 5"), 1))
        code, out, err = run(*dargs, cwd=dg)
        check("diagnose: a cause whose quote is not on its line is refused",
              code == 3 and "\"quote:\" must be words that are on line 2 of job.x" in out, out + err)
        dnotes.write_text(dform.replace("## Causes\n", cause, 1))
        code, out, err = run(*dargs, cwd=dg)
        dtext = (dg / "reports" / "diagnosis.md").read_text()
        check("diagnose: with the cause shown on its line the gate passes, the lines that name what the symptom involves "
              "and the scan hit on them are listed, and the code is unchanged",
              code == 0 and "Gate: passed" in out and "| K-01 | 2 | `if (@Kind = 5) {`" in dtext and "| shown |" in dtext
              and "- line 3: `@Summary = \"Disk full on \" + @Node`" in dtext and "Assignment in a condition" in dtext
              and (dg / "job.x").read_text() == dsrc, out + err + dtext)

        # ---- review of a change: the script writes the report, the reviewer judges each difference in the notes
        rv = tmp / "reviewed"
        write(rv / "v1" / "job.x", "@Total = @Price * @Qty;\nif (@Kind = 1) {\n    label = \"Total: \";\n}\nsend(@Total, label);\n")
        write(rv / "v2" / "job.x", "@Total = @Price * @Qty;\nif (@Kind == 1) {\n    label = \"Sum: \";\n}\nsend(@Total, label);\n")
        rargs = ("run.py", "change", "v1", "v2", "--out", "reports/review.md")
        code, out, err = run(*rargs, cwd=rv)
        rnotes = notes_for(rv / "reports" / "review.md")
        rskel = rnotes.read_text()
        check("review of a change: the first run lists every difference in the notes and says how the two versions differ",
              code == 0 and "expected on the first run" in out and "Assignment in a condition 1 -> 0" in out
              and re.search(r"^D-01:\s+<!-- Line rewritten: job\.x:2 `if \(@Kind = 1\) \{` is now line 2 `if \(@Kind == 1\) \{`", rskel, re.M)
              and re.search(r"^D-02:\s+<!-- Line rewritten: job\.x:3 `label = \"Total: \";`", rskel, re.M)
              and re.search(r"^D-03:\s+<!-- Operators, keywords and member names new to the code: ==", rskel, re.M)
              and "Strings gone" not in rskel and "## Checks performed" in rskel,
              out + err + rskel[:900])
        code, out, err = run(*rargs, cwd=rv)
        check("review of a change: with nothing judged the gate does not pass, and the differences to judge are named",
              code == 3 and "Differences still to judge: D-01, D-02, D-03" in out and "Gate: passed" not in out, out + err)
        filled = re.sub(r"^D-01:.*$", "D-01: intended: the single = in the condition on line 2 assigned where it should compare", rskel, flags=re.M)
        filled = re.sub(r"^D-02:.*$", "D-02: unintended: the label of the total was reworded, see V-01", filled, flags=re.M)
        filled = re.sub(r"^D-03:.*$", "D-03: intended: the operator of the corrected condition on line 2", filled, flags=re.M)
        filled = filled.replace("\n## Checks performed", "### job.x: 3\nseverity: High\nquote: label = \"Sum: \"\n"
                                "what: the text sent with the total was changed from Total to Sum\n"
                                "introduced: yes: the earlier version sends \"Total: \" on line 3\n\n## Checks performed", 1)
        filled = re.sub(r"^([A-Z][^|\n]* \| )$", r"\1read lines 1-5 of v2/job.x against v1/job.x: only lines 2 and 3 differ", filled, flags=re.M)
        filled = filled.replace("\n## Questions for the owner", "The later version corrects the condition and rewords a text it "
                                "was not asked to change, so it is not fit to replace the earlier one as it stands.\n\n"
                                "## Questions for the owner\nShould the label read Total or Sum?\n", 1)
        rnotes.write_text(filled.replace("quote: label = \"Sum: \"", "quote: label = \"Amount: \""))
        code, out, err = run(*rargs, cwd=rv)
        check("review of a change: a finding that quotes words that are not on its line is refused",
              code == 3 and "\"quote:\" must be words that are on line 3 of job.x" in out, out + err)
        rnotes.write_text(filled)
        code, out, err = run(*rargs, cwd=rv)
        rtext = (rv / "reports" / "review.md").read_text()
        check("review of a change: with every difference judged and the finding written, the gate passes and the report holds them",
              code == 0 and "Gate: passed" in out and "| D-02 | Line rewritten" in rtext and "| unintended |" in rtext
              and "2 intended, 1 unintended" in rtext and "| Rewritten | 2 |" in rtext
              and "2 string(s) that are gone, new or used a different number of times stand on the lines rewritten, added or removed" in rtext
              and "1. Should the label read Total or Sum?" in rtext
              and "| V-01 | High | job.x:3 |" in rtext and "| Assignment in a condition | 1 | 0 | went down |" in rtext,
              out + err + rtext[:1500])
        code, out, err = run("run.py", "status", cwd=rv)
        check("status: says which task was worked on last, so that the reply is about the latest request",
              code == 0 and "Last worked on: reports/review.md" in out and "not about the first message" in out, out + err)
        code, out, err = run("run.py", "fix", "v2", "--out", "fixed", "--log", "reports/fix.md", "--register",
                             "reports/review.md", cwd=rv)
        fnotes = notes_for(rv / "reports" / "fix.md")
        check("fix: the findings of a review of a change are the findings to fix",
              fnotes.exists() and "V-01" in fnotes.read_text(), out + err)
        rm2 = tmp / "reviewed-names"
        write(rm2 / "v1" / "job.x", "Unit_Price = fetch(1);\nUnit_Count = fetch(2);\n// the bill\n"
                                    "send(Unit_Price, Unit_Count, Unit_price);\nlog(Total);\n")
        write(rm2 / "v2" / "job.x", "unitPrice = fetch(1);\nunitCount = fetch(2);\nsend(unitPrice, unitCount, unitPrice);\nlog(@Total);\n")
        code, out, err = run("run.py", "change", "v1", "v2", "--out", "reports/review.md", cwd=rm2)
        mskel = notes_for(rm2 / "reports" / "review.md").read_text()
        check("review of a change: two earlier names that became one, and a name that gained its prefix, are corrections, "
              "not renames",
              "Lines: 2 rewritten, 2 changed in names only (2 name(s))" in out
              and "Line rewritten: job.x:4 `send(Unit_Price, Unit_Count, Unit_price);`" in mskel
              and "Line rewritten: job.x:5 `log(Total);`" in mskel, out + err + mskel[:1500])
        check("review of a change: a removed comment that is not code is listed on its own, with the line it explained",
              "1 comment line(s) removed (1 of them explanations, not code)" in out
              and "Comment removed that is not commented-out code: job.x:3 `// the bill` - it stood above line 4 "
                  "`send(Unit_Price, Unit_Count, Unit_price);`, which stays" in mskel, out + err + mskel[:1500])

        # ---- scan: an else left inside a block, in code that writes comments with # and blocks with braces
        ob = tmp / "orphan"
        chain = "".join("%sif (match(@Kind, \"%d\"))\n{\n    @Grade = %d\n}\n" % ("else " if i else "", i, i) for i in range(6))
        write(ob / "good.rules", "# grades\n" + chain + "else\n{\n    @Grade = 9\n}\n")
        write(ob / "bad.rules", "# grades\n" + chain + "else if (match(@Kind, \"7\"))\n{\nelse if (match(@Kind, \"8\"))\n}\n")
        code, out, err = run("scan_code.py", ob / "good.rules", cwd=ob)
        check("scan: a chain of else-if blocks in code with # comments has no else without its if",
              re.search(r"^\s*0\s+else or else-if with no if before it\s*$", out, re.M), out + err)
        code, out, err = run("scan_code.py", ob / "bad.rules", cwd=ob)
        check("scan: an else-if left inside the block of another, with the brackets still in balance, is reported",
              re.search(r"^\s*1\s+else or else-if with no if before it\s*$", out, re.M), out + err)

        # ---- change: with a document next to the code, the plan says what it does about each thing the document asks
        cv = tmp / "covered"
        write(cv / "job.x", "@Total = @Price * @Qty;\nlog(\"total: \" + @Total);\nsend(@Total);\n")
        write(cv / "requirement.txt", "1. Every log line starts with the name of the job.\n2. Totals are kept in a table.\n")
        cargs = ("run.py", "edit", "job.x", "--out", "out", "--report", "reports/tidy.md")
        run(*cargs, cwd=cv)
        cplan = notes_for(cv / "reports" / "tidy.md")
        cskel = cplan.read_text()
        check("change: the plan file has a part for the coverage of the requirement, and names the document",
              "## Coverage of the requirement" in cskel and "requirement.txt" in cskel, cskel[:1500])
        fix = ("### line 2\nafter: log(\"job - total: \" + @Total);\n"
               "why: the requirement asks for the name of the job at the start of each log line; the value logged is the same\n\n")
        at_r, at_c = cskel.index("## Renames"), cskel.index("## Explanations")

        def with_coverage(lines):
            return cskel[:at_r] + fix + cskel[at_r:at_c] + lines + "\n" + cskel[at_c:]

        cplan.write_text(with_coverage(""))
        code, out, err = run(*cargs, cwd=cv)
        check("change: a plan that does not say what it does about the requirement does not pass",
              code == 3 and "\"Coverage of the requirement\" has no line yet" in out, out + err)
        cplan.write_text(with_coverage("Every log line starts with the name of the job | done: the correction on line 2\n"
                                       "Totals are kept in a table | not done: needs a new file; kept as it is pending owner approval\n"))
        code, out, err = run(*cargs, cwd=cv)
        check("change: waiting for an approval is not accepted as the reason a requirement is not done",
              code == 3 and "waiting for an approval is not a reason" in out and "Gate: passed" not in out, out + err)
        cplan.write_text(with_coverage("Every log line starts with the name of the job | done: the correction on line 2\n"
                                       "Totals are kept in a table | not done: the code holds one total and no table to keep it in\n"))
        code, out, err = run(*cargs, cwd=cv)
        check("change: each requirement done, or not done with what in the files prevents it, passes and is in the report",
              code == 0 and "Gate: passed" in out
              and "| Totals are kept in a table | not done: the code holds one total" in (cv / "reports" / "tidy.md").read_text(),
              out + err)

    print("%d passed, %d failed, %d known fault(s)" % (passed, len(failed), len(known_faults)))
    for f in failed:
        print("  FAILED: %s" % f)
    for f in known_faults:
        print("  KNOWN FAULT (the test fails until the script is corrected): %s" % f)
    sys.exit(1 if failed or known_faults else 0)


if __name__ == "__main__":
    main()
