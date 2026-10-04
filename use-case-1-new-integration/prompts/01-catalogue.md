# Prompt 1 · Catalogue — the trap list against the MIBs

Part of [Use Case 1 — New Integration: from MIBs to Probe Rules](../README.md).

## The prompt

```text
Catalogue the traps of inputs/<trap list>.xlsx against the MIBs in inputs/mibs.
Write reports/trap-catalogue.md.
Do not write any rules.
```

## What it does, and why

| | |
|---|---|
| **Why this step** | Turn a hand-typed list and a pile of MIBs into one checked list of traps before any rule is written, so every disagreement is settled once, in writing |
| **Reads** | Every sheet of the workbook and every MIB file |
| **The skill** | Find the trap tables in each sheet; read every MIB (both SMIv1 and SMIv2 traps) and resolve OIDs, variables, value maps and table indexes; match each row by OID and by name; detect OID typos (one digit from a MIB OID), names that differ from the MIB, rows whose name and OID point to two traps, traps no MIB defines, rows that are variables rather than traps, alarm numbers, and remarks; map severity words; find traps listed with two severities; pair problems and clears; write one block per decision, each with its facts and a proposal |
| **Bob decides** | The role of each sheet, each row that disagrees with the MIBs, the severity words, the conflicts, the trap that carries the alarm numbers, the clear groups, and the problems with no clear |
| **The gate refuses** | Any block without a valid decision; any trap left without a severity |
| **Writes** | The catalogue (every trap with its SNMPv1 form, severity, type, clear group and flags; the alarm-number table; the decisions; where the list and the MIBs differ; the questions for the operator) and a machine-readable copy for the next step |
| **Why these words** | "Do not write any rules" keeps one concern per step: the list is settled before anything is generated from it |

## What if the trap list and the MIBs do not agree?

The catalogue is built in two passes:

1. **The skill** reads every sheet and every MIB and matches each row of the list to a MIB trap, by OID and by name. Every disagreement it finds becomes a **decision block** in the notes file, with the facts and a proposal. It finds the same things every time.
2. **Bob** decides each block. The gate does not pass while a block is undecided or a trap has no severity.

What happens in each case:

| Case | What happens |
|---|---|
| A trap is in the list but in no MIB that was sent | It is kept, with the OID and the severity from the list. Its variables cannot be named, and the report asks the operator for the MIB |
| An OID one digit away from a MIB OID | The MIB's OID is proposed, and the report lists the correction |
| A row whose name and OID point to two different traps | The trap is chosen by its description, and the report asks the operator to confirm |
| A trap listed twice with two severities | One severity is proposed, and the report asks the operator to confirm |
| A problem with no matching clear | It stays a problem that is cleared by hand, and the report asks whether it should expire instead |
| A trap a MIB defines but the list does not ask for | It is not catalogued: the list sets the scope |

**The limits.** The catalogue checks the list against the MIBs, not against the device. If the device sends a trap that neither the list nor a MIB names, the rules still give it an event, with an event id that marks it as unknown, so it is seen rather than lost. If the list and the MIB are both wrong in the same way, nothing here can tell.
