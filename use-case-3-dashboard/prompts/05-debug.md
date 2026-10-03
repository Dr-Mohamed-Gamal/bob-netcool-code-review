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
| **The scripts** | List every line that names what the symptom involves (the two devices, their filters), with the scan hits on those lines |
| **Bob decides** | Each possible cause with its line, a quote that is on that line, how the line produces the symptom, and whether it is shown, ruled out, or open with the test that decides it |
| **The gate refuses** | A quote that is not on its line; a diagnosis with no cause shown and an open cause that names no test |
| **Writes** | A diagnosis |
| **Why these words** | The symptom is given as reported; "Do not fix anything" keeps the page unchanged, since the cause may be by design |
