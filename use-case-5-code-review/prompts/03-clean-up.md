# Prompt 3 · Clean up — commented-out code removed

Part of [Use Case 5 — Code Analysis, Standardization and Optimization](../README.md).

## The prompt

```text
Clean up a copy of each step-1-fixed, one after the other.
Policy: in a copy of impact-policy/refactored/step-1-fixed under impact-policy/refactored/step-2-cleaned, remove the commented-out code as section 3 of the requirement document asks.
Rules: in a copy of probe-rules/refactored/step-1-fixed under probe-rules/refactored/step-2-cleaned, remove the commented-out code as standard 4 of the code standards document asks.
Write impact-policy/reports/clean-up.md and probe-rules/reports/clean-up.md.
Do not change the ticket content or the events.
```

## What it does, and why

| | |
|---|---|
| **Why this step** | Remove the code switched off over the years, so engineers read only what runs. Both documents ask for it, and it is the change most often done carelessly by hand |
| **Reads** | The step-1 copy and the document's item on commented-out code |
| **The scripts** | List every commented-out line and block, telling them apart from comments that explain live code; remove what Bob confirms, in a copy; refuse to remove a comment that stands right above a live line that stays; compare the copy with step 1 |
| **Bob decides** | Which commented-out code goes (normally all of it), and which comment is an explanation to keep |
| **The gate refuses** | A removal that changes a live line or leaves half a block; an item of the document left unaccounted for |
| **Writes** | The cleaned copy (step 2) and a clean-up report per input |
| **Why these words** | "Do not change the ticket content or the events" states the safety condition the comparison checks |
