# Prompt 3 · Review — the rules against the catalogue, with the simulator

Part of [Use Case 1 — New Integration: from MIBs to Probe Rules](../README.md).

## The prompt

```text
Review rules/ against reports/trap-catalogue.md.
Write reports/rules-review.md.
Do not fix anything.
```

## What it does, and why

| | |
|---|---|
| **Why this step** | Check the rules independently of how they were made, so the same review also works on rules edited by hand later |
| **Reads** | The rules folder and the catalogue |
| **The scripts** | Check the rules as text (syntax, paths through `$NC_RULES_HOME`, the log format, commented-out code, one case per trap, event ids, severities and types, variables, the key of each problem and its clear, the alarm numbers), then run the **simulator**: a small interpreter of the rules language sends one test trap per trap, one per alarm number, each problem followed by its clear, each clear-by-value, and an unknown trap, and compares the events with the catalogue |
| **Bob decides** | For each finding: fix, a question for the owner, or not a defect with the reason the files show |
| **The gate refuses** | A finding without a decision |
| **Writes** | The review |
| **Why these words** | "Do not fix anything" keeps the reviewer apart from the generator; a fix goes back through the notes and prompt 2 |
