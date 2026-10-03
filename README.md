# IBM Bob on Netcool code

Pages describing three pilot use cases of IBM Bob, in its built-in Agent mode, on Netcool code: reviewing, fixing and standardizing existing code; adding a device to a dashboard; and integrating a new device from its MIBs.

The pages, published with GitHub Pages:

- `index.html`: five prompts that review, fix, clean up, standardize and review Netcool Impact policies and probe rules;
- `skill.html`: the generic code-review skill for IBM Bob: what it is, its five tasks, its gates, and how to use it;
- `dashboard.html`: three prompts that add a device to a Netcool Impact dashboard exactly like an existing one, review the change, and debug a reported fault;
- `integration.html`: three prompts that turn a device's trap list and its vendors' MIBs into probe rules and lookups in the operator's folder tree, and review them with a rules simulator (skill: [bob-trap-rules-skill](https://github.com/Dr-Mohamed-Gamal/bob-trap-rules-skill)).

The first page covers:

- the use case and the two pieces of code it works on;
- how Bob is steered: one skill with scripts that do the mechanical work, a short workspace rule, and a gate at the end of every command;
- each of the five prompts, what it does, and its full text;
- what the rehearsals showed, and what was left out of the five prompts and why;
- how to run it.

This repository holds the description only. The client's code, documents and the reports made from them are not published here.
