# Prompt 2 · Generate — the rules, in the operator's folder tree

Part of [Use Case 1 — New Integration: from MIBs to Probe Rules](../README.md).

## The prompt

```text
Generate the rules for reports/trap-catalogue.md under rules/, following inputs/rules_file_code_standards.txt.
Write reports/rules-generated.md.
Do not decide what is the client's to decide.
```

## What it does, and why

| | |
|---|---|
| **Why this step** | Write the rules from the catalogue only, in the operator's layout, with every value that is data in lookups |
| **Reads** | The catalogue and the standards document, whose folder tree the layout follows |
| **The skill** | Propose the layout, one rules file per vendor, the expiry of events, and every trap's group, key and summary (from the trap list's text, the MIB's summary or the description); flag texts that name a variable the trap does not have or the wrong one; after the decisions, write the entry point, the table declarations, one case per trap, the field normalization and the lookups; then check them and send a test trap of every kind through the simulator |
| **Bob decides** | The folder path, the file names, the expiry, any group, key or summary to change, and the summaries the skill could not propose |
| **The gate refuses** | An open block; a template that names a variable the trap does not have; two clear groups sharing one AlertGroup (a clear of one would close the other's problem); any finding of the check or the simulator |
| **Writes** | The rules folder and a report with the files, how to install them, every trap's key and summary, and the questions for the operator |
| **Why these words** | "Following" the standards document sets the target tree; "Do not decide what is the client's to decide" turns the domain folder, the field for the service-impact flag and the severity conflicts into questions |

## What if the skill cannot propose a value?

The generation also works in two passes:

1. **The skill** proposes, from the catalogue, the file layout, the expiry of events, and each trap's group, key and summary. It flags what it cannot settle: an event text in the trap list that names a variable the trap does not carry, or a trap with no text to build a summary from. Those blocks are left open, with the facts.
2. **Bob** writes the open blocks and accepts or changes the proposals. No rule is written until every block is decided, and the gate refuses a summary that names a variable the trap does not have.

Choices that belong to the operator are not made by Bob: the domain folder the rules go into, the event field that carries the service-impact flag, and which severity wins when two sources disagree. They are proposed and listed as questions in the report.

**The limits.** The rules are generated as text and checked by the review and its simulator (prompt 3). They have not been loaded by a real probe.
