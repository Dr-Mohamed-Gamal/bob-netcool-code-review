# Prompt 2 · Review the change — the copy against the original

Part of [Use Case 3 — Add a Device to a Dashboard, and Debug It](../README.md).

## The prompt

```text
Review refactored/step-1-device-added against inputs/<page>.html.
Write reports/code-review.md.
Do not fix anything.
```

## What it does, and why

| | |
|---|---|
| **Why this step** | Check the change independently: every line that differs between the copy and the page, and nothing else |
| **Reads** | The step-1 copy, the original page and the add report |
| **The scripts** | Compare the two versions line by line, keeping strings in the alignment so near-identical rows are not mismatched, and list every difference with the strings and calls it adds |
| **Bob decides** | For each difference: intended or not, with the reason; what only the owner can confirm (for example, whether the page's scripts pick up the new checkbox) |
| **The gate refuses** | Any difference left unjudged |
| **Writes** | A review of the change |
| **Why these words** | "Do not fix anything" keeps the reviewer and the author apart |
