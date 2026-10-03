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
| **The scripts** | Find the trap tables in each sheet; read every MIB (both SMIv1 and SMIv2 traps) and resolve OIDs, variables, value maps and table indexes; match each row by OID and by name; detect OID typos (one digit from a MIB OID), names that differ from the MIB, rows whose name and OID point to two traps, traps no MIB defines, rows that are variables rather than traps, alarm numbers, and remarks; map severity words; find traps listed with two severities; pair problems and clears; write one block per decision, each with its facts and a proposal |
| **Bob decides** | The role of each sheet, each row that disagrees with the MIBs, the severity words, the conflicts, the trap that carries the alarm numbers, the clear groups, and the problems with no clear |
| **The gate refuses** | Any block without a valid decision; any trap left without a severity |
| **Writes** | The catalogue (every trap with its SNMPv1 form, severity, type, clear group and flags; the alarm-number table; the decisions; where the list and the MIBs differ; the questions for the operator) and a machine-readable copy for the next step |
| **Why these words** | "Do not write any rules" keeps one concern per step: the list is settled before anything is generated from it |
