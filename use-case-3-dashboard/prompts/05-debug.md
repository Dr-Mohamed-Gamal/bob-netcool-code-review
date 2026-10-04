# Prompt 5 · Debug — from a reported symptom to the line (separate)

Part of [Use Case 3 — Add a Device to a Dashboard, and Debug It](../README.md).

## The prompt

```text
Diagnose inputs/<page>.html: the <DEVICE> tiles open the alarms of <OTHER DEVICE> instead of those of <DEVICE>.
Write reports/diagnosis.md.
Do not fix anything.
```

## What it does, and why

| | |
|---|---|
| **Why this step** | Show how a reported fault is traced to its cause without touching the page |
| **Reads** | The original page and the symptom in the operator's words |
| **The skill** | List every line that names what the symptom involves (the two devices, their filters), with the scan hits on those lines |
| **Bob decides** | Each possible cause with its line, a quote that is on that line, how the line produces the symptom, and whether it is shown, ruled out, or open with the test that decides it |
| **The gate refuses** | A quote that is not on its line; a diagnosis with no cause shown and an open cause that names no test |
| **Writes** | A diagnosis |
| **Why these words** | The symptom is given as reported; "Do not fix anything" keeps the page unchanged, since the cause may be by design |

## How is the cause found, and what if it is not in the page?

The diagnosis works in two passes:

1. **The skill** lists every line that names what the symptom involves (the two devices, their tiles, their filters), with the scan's hits on those lines.
2. **Bob** reads those lines and compares the faulty tiles with tiles that work. Each possible cause gets its line, a quote from that line, how it produces the symptom, and a status: **shown** (the line itself proves it), **ruled out**, or **open**, with the test that would decide it. The gate checks that every quote is on its line.

- **If the cause is not in the page**, because it is in a script the page loads, in the Impact policy or in the events, the diagnosis says that no cause is shown in the page and names the test that would decide it.
- **If the code may be doing what its owner intended**, for example a filter that covers two devices on purpose, the diagnosis asks the owner instead of calling it a bug. That is why the prompt says "Do not fix anything".

**The limits.** The diagnosis is a reading of the code; nothing is run.
