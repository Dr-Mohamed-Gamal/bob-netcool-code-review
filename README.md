# IBM Bob on Netcool code

A one-page description of a pilot use case: five prompts that take a Netcool Impact policy and a set of Netcool probe rules from a defect register to fixed, cleaned, standardized and reviewed code, with IBM Bob in its built-in Agent mode.

Two pages, published with GitHub Pages:

- `index.html`: five prompts that review, fix, clean up, standardize and review Netcool Impact policies and probe rules;
- `skill.html`: the generic code-review skill for IBM Bob: what it is, its five tasks, its gates, and how to use it;
- `dashboard.html`: three prompts that add a device to a Netcool Impact dashboard exactly like an existing one, review the change, and debug a reported fault.

The first page covers:

- the use case and the two pieces of code it works on;
- how Bob is steered: one skill with scripts that do the mechanical work, a short workspace rule, and a gate at the end of every command;
- each of the five prompts, what it does, and its full text;
- what the rehearsals showed, and what was left out of the five prompts and why;
- how to run it.

This repository holds the description only. The client's code, documents and the reports made from them are not published here.
