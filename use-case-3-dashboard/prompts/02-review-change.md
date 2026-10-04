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

## What does the review check, and what can it miss?

The review works in two passes:

1. **The comparison (a script)** lists every line that differs between the copy and the original page, with the strings and calls each difference adds or removes. Nothing that changed can be left out of the list, not even a lost line or a changed line ending.
2. **Bob** judges each difference: intended (part of the request) or unintended, with the reason. It also reads the changed lines and the lines that use the same names, such as the select lists, for problems a comparison cannot show, such as a tile that still opens the model's filter.

The gate does not pass while any difference is left unjudged.

**The limits.** The review sees only this page. It cannot see the scripts the page loads from the server, and it does not open the page in a browser. What only the owner can confirm goes into the report as a question.
