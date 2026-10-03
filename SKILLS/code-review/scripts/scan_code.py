#!/usr/bin/env python3
"""List the places in some code that a reader most often misses.

    python3 scan_code.py <file-or-folder> [<file-or-folder> ...]

Reads the code as text, in any language with C-like syntax, and lists
candidates for defects of these kinds (and more; see CHECKS):

  1. assignment in a condition     a single = inside if / while
  2. name read, never assigned     nothing in the scanned code sets it
  3. name assigned, never read     the value is not used
  4. name used once, close to another name    possible misspelling
  5. assigned twice in a row       the first value is lost
  6. markup in strings             entity without ';', tag never closed
  7. placeholder text in strings   test, todo, dummy, sample ...

Every line it prints is a candidate, not a finding: read each one and
decide. The same input always gives the same list, so the counts can be
quoted in a report and compared before and after a change. It reads text
only; it does not run the code and knows nothing about the runtime, so a
name it reports as never assigned may be set by the platform.

Names are counted across all the files given, so pass the whole set when
files share variables. In a folder, documents and data files (.txt, .md,
.json and the like) are left out; name a file directly to scan it anyway. Comments are // to end of line and /* ... */. Add
--hash-comments for languages where # starts a comment. Python standard
library only.
"""
import argparse
import os
import re
from collections import defaultdict
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".bob", ".vscode"}
# Documents and data are not code: left out when a folder is scanned.
SKIP_TYPES = {".txt", ".md", ".rst", ".pdf", ".doc", ".docx", ".csv", ".log",
              ".json", ".yaml", ".yml", ".xml", ".png", ".jpg", ".zip"}     # .html is code: pages hold their script
# How comments are written, by file type. Anything not listed uses // and /* */.
HASH_TYPES = {".py", ".rb", ".pl", ".pm", ".r", ".tcl", ".ps1", ".sh", ".bash",
              ".zsh", ".ksh", ".awk", ".mk", ".toml", ".cfg", ".conf", ".ini"}
SLASH_TYPES = {".js", ".jsx", ".ts", ".tsx", ".java", ".c", ".h", ".cpp", ".hpp", ".cc",
               ".cs", ".go", ".kt", ".swift", ".scala", ".rs", ".dart", ".groovy"}
DASH_TYPES = {".sql", ".pls", ".plsql", ".lua", ".hs", ".ada", ".adb", ".vhd"}
BOTH_TYPES = {".php"}
# Languages where a single = inside a condition compares: check 1 does not apply.
EQUALS_COMPARES = {".sql", ".pls", ".plsql", ".vb", ".vbs", ".bas", ".pas", ".sh",
                   ".bash", ".zsh", ".ksh", ".cob", ".cbl", ".abap", ".ada", ".adb"}
SIGILS = "@$%"                            # prefixes that mark a kind of name
COND_WORDS = {"if", "elseif", "elsif", "elif", "while", "until", "unless"}
TYPE_NAMES = {"int", "string", "float", "double", "boolean", "bool", "char", "long",
              "short", "byte", "unsigned", "signed", "auto", "final", "var"}
DECL_WORDS = {"var", "let", "const", "local", "my", "our", "dim", "global", "static", "val"}
FUNC_WORDS = {"function", "def", "sub", "func", "fn", "fun"}
TYPE_WORDS = {"handle", "catch", "except", "throw", "throws", "raise", "new",
              "extends", "implements", "import", "class", "instanceof", "using", "namespace", "package",
              "interface", "struct", "enum", "use"}
LOOP_WORDS = {"for", "foreach"}
KEYWORDS = COND_WORDS | DECL_WORDS | FUNC_WORDS | LOOP_WORDS | {
    "else", "then", "end", "do", "in", "of", "return", "break", "continue",
    "switch", "case", "default", "try", "catch", "finally", "throw", "new",
    "delete", "typeof", "instanceof", "and", "or", "not", "like", "is",
    "true", "false", "null", "nil", "none", "undefined", "this", "self",
    "class", "import", "from", "export", "void", "int", "string", "float",
    "double", "boolean", "bool", "char", "long", "public", "private",
    "protected", "handle", "raise", "pass", "with", "as", "lambda", "yield",
    "short", "byte", "unsigned", "signed", "auto", "final", "abstract", "struct",
    "enum", "interface", "namespace", "package", "using", "include", "define",
    "pragma", "async", "await", "assert", "del", "sizeof", "except", "extends",
    "implements", "throws", "begin", "elif", "elsif", "endif", "fi", "done",
    "readonly", "override", "internal", "sealed", "virtual", "defer", "chan", "esac", "redo", "retry",
    "ensure", "rescue", "nil",
}
# Names of built-in types of typed languages. They are skipped only where a type is written
# (after : or after another name), never where they are used as a variable.
BUILT_IN_TYPES = {"number", "any", "unknown", "never", "object", "str", "float64", "float32", "int64", "int32",
                  "int16", "int8", "uint", "uint64", "uint32", "uint8", "rune", "error", "integer", "decimal",
                  "datetime", "list", "dict", "tuple", "set", "array", "map", "unit", "nothing"} | TYPE_NAMES
INCLUDE_WORDS = {"include", "source", "require", "require_once", "include_once", "load"}
DEFINES = re.compile(r"^[ \t]*(?:[A-Za-z_]\w*[ \t]+)?([@$%]?[A-Za-z_][\w-]*)[ \t]*=(?!=)", re.M)
LOG_CALLS = {"log", "print", "println", "printf", "echo", "debug", "info",
             "warn", "warning", "error", "trace"}
ASSIGN_OPS = {"=", "+=", "-=", "*=", "/=", "%=", "|=", "&=", "^=", ":="}
COMPARE_OPS = {"==", "!=", "===", "!==", "<", ">", "<=", ">="}
# Words that are followed by ( without being a call. Any other name followed by ( is a call,
# including a type name used to convert a value: int(x), string(x).
CONTROL_WORDS = {"if", "elseif", "elsif", "elif", "while", "until", "unless", "for", "foreach", "switch",
                 "catch", "return", "function", "def", "sub", "func", "fn", "and", "or", "not", "in", "of",
                 "typeof", "sizeof", "new", "delete", "throw", "raise", "case", "with", "lambda", "yield",
                 "await", "assert", "else", "do", "try", "finally", "then", "handle", "except", "is", "like"}
SIZE_WORDS = {"length", "len", "count", "size", "sizeof", "isset", "empty", "isempty", "isnull",
              "defined", "exists", "is_null", "is_array"}
HANDLER_WORDS = {"catch", "handle", "except", "rescue"}
COMMAND_WORDS = {"system", "exec", "eval", "popen", "shell_exec", "passthru", "proc_open", "execsync",
                 "spawnsync", "execfile"}
CREDENTIAL_NAME = re.compile(r"(?i)(password|passwd|pwd|secret|api_?key|(auth|access|bearer)_?token)$")
COUNT_WORDS = {"length", "len", "count", "size", "sizeof"}
REPLACE_WORDS = {"replace", "replaceall", "substitute", "sub", "gsub", "regexreplace", "str_replace", "preg_replace"}
# Shell scripts: a word without $ is text or a command, a variable is set as NAME=value and read as $NAME.
SHELL_TYPES = {".sh", ".bash", ".zsh", ".ksh"}
SHELL_GIVEN = {"HOME", "PATH", "USER", "PWD", "SHELL", "HOSTNAME", "LANG", "TERM", "IFS", "OLDPWD", "RANDOM",
               "LINENO", "UID", "PPID", "TMPDIR", "LOGNAME", "OPTARG", "OPTIND", "REPLY", "SECONDS"}
# A variable written inside a string: $name, ${name}, #{name}
IN_STRING = re.compile(r"\$\{?([A-Za-z_]\w*)|#\{\s*([A-Za-z_]\w*)")
LEAVE_WORDS = {"break", "return", "exit", "goto", "last", "throw", "raise", "die"}
# File types where /.../ can be a pattern written without quotes.
REGEX_TYPES = {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".rb", ".pl", ".pm", ".awk", ".groovy"}
ENV = re.compile(r"(?<![A-Za-z])(?:SIT|DEV)(?![A-Za-z])"
                 r"|(?i:(?<![A-Za-z])(?:uat|preprod|stg|localhost|staging|sandbox)(?![A-Za-z]))")
ADDRESS = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])|https?://[^\s'\"<>]+")
CREDENTIAL = re.compile(r"(?i)(password|passwd|pwd|secret|api[_-]?key|token)\s*[=:]\s*[^\s&;,'\"]{3,}")
QUERY = re.compile(r"(?i)^\s*(select\s|insert\s+into\s|update\s+\w+\s+set\s|delete\s+from\s)"
                   r"|(=|<>|!=|\blike)\s*'\s*$")
OPS3 = ("===", "!==", "<<=", ">>=", "**=")
OPS2 = ("==", "!=", "<=", ">=", "=>", "+=", "-=", "*=", "/=", "%=", "|=", "~=", "=~", "!~",
        "&=", "^=", ":=", "&&", "||", "->", "::", "++", "--", "<<", ">>")
ENTITY = re.compile(r"&(?:(?:amp|lt|gt|quot|apos|nbsp)(?![;\w=])|#\d+(?![\d;])|#x[0-9A-Fa-f]+(?![0-9A-Fa-f;]))")
TAG = re.compile(r"<(/?)([A-Za-z][\w.-]*)((?:\s[^<>]*)?)>")
PLACEHOLDER = re.compile(
    r"(?<![A-Za-z])(test\d*|todo|fixme|tbd|dummy|sample|placeholder|changeme"
    r"|foo|bar|baz|lorem|xxx+|example\.(?:com|org|net))(?![A-Za-z])", re.I)
# A string that is a pattern to match text with, not text that is output.
PATTERN_TEXT = re.compile(r"\\[sdwSDWb]|\.\*|\.\+|\(\?[:=!]|\[\^")
# Documents next to the code: read for lists of names (a schema, a list of fields), never scanned as code.
DOC_TYPES = {".txt", ".md", ".rst", ".csv", ".tsv", ".adoc"}
# Pictures and office files: a folder that holds only these and documents holds no code.
NOT_CODE_TYPES = {".svg", ".gif", ".jpeg", ".bmp", ".ico", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".tex"}
DOC_LIMIT = 2000000                          # bytes; a larger document is not read
LIST_MIN = 5                                 # a list of names has at least this many lines
NAME_HEADS = {"name", "names", "field", "fields", "column", "columns", "attribute", "attributes", "variable",
              "variables", "parameter", "parameters", "key", "keys", "property", "properties", "element", "elements"}
# Types whose values cannot hold a quote or any other text.
NUMBER_TYPE = re.compile(r"(?i)^(u?int(eger)?\d*|incr|unsigned\d*|utc|time|timestamp|date|datetime|number|numeric"
                         r"|bigint|smallint|tinyint|long|short|float\d*|double|decimal|real|bool(ean)?|bit|serial)$")
LIST_LINE = re.compile(r"^[\s>*\-•·|]*[`'\"]?([@$%]?[A-Za-z_]\w*)[`'\"]?(?:[\s,;:|=]+(.*?))?[\s|]*$")
TYPE_WORD = re.compile(r"^[A-Za-z_][\w]*(\([\d, ]*\))?$")
WRITTEN_BY_SCRIPT = ("# Review", "# Change log", "# Traceability map", "# Notes", "# Diagnosis", "# Fix", "# Change")


def names_in(path):
    """The lists of names a document holds: {name: (line, type)} and [(first line, last line, count)].

    A list is a run of lines that each hold one name, alone or followed by its type
    (`Severity  Integer`), or a table whose first column is headed Name, Field, Column
    and the like. A name mentioned inside a sentence is not part of a list.
    """
    try:
        raw = Path(path).read_bytes()
    except OSError:
        return {}, []
    if len(raw) > DOC_LIMIT or b"\0" in raw[:8192]:
        return {}, []
    text = raw.decode("utf-8", errors="replace")
    if text.lstrip().startswith(WRITTEN_BY_SCRIPT):
        return {}, []
    names, blocks, run, table = {}, [], [], None
    delimiter = "\t" if Path(path).suffix.lower() == ".tsv" else "," if Path(path).suffix.lower() == ".csv" else None

    def close(in_table=False):
        # In a list of names with their types, a few types come back on many lines.
        # Lines of ordinary text each end differently: such a run is not a list of names.
        typed = {rest for _, _, _, rest in run}
        if len(run) >= LIST_MIN and (in_table or len(typed) <= max(3, len(run) // 3)):
            for n, name, kind, _ in run:
                names.setdefault(name, (n, kind))
            blocks.append((run[0][0], run[-1][0], len(run)))
        del run[:]

    for n, line in enumerate(text.split("\n"), 1):
        line = line.rstrip("\r")
        if not line.strip():
            if table is not None and not delimiter:
                close(table)                      # an empty line ends a table,
                table = None
            continue                              # but not a list written line by line
        cells = None
        if delimiter:
            cells = [c.strip().strip("\"'`") for c in line.split(delimiter)]
        elif line.lstrip().startswith("|"):
            cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
        if cells is not None:
            if set(line.strip()) <= set("|-: "):
                continue                          # the rule under the header of a table
            if table is None:                     # the header row: only a table of names is read
                close()
                table = bool(set(re.findall(r"[a-z]+", cells[0].lower())) & NAME_HEADS)
                continue
            m = re.match(r"^[@$%]?([A-Za-z_]\w*)$", cells[0])
            if table and m:
                kind = cells[1].split("(")[0].strip() if len(cells) > 1 and TYPE_WORD.match(cells[1]) else ""
                run.append((n, m.group(1), kind, kind))
            continue
        if table is not None and not delimiter:
            close(table)
            table = None
        m = LIST_LINE.match(line) if not line.rstrip().endswith(":") else None      # `Fields:` is a heading
        rest = (m.group(2) or "").split() if m else None
        if m and len(rest) <= 3 and all(TYPE_WORD.match(w) for w in rest):
            run.append((n, m.group(1).lstrip("@$%"), rest[0].split("(")[0] if rest else "", " ".join(rest).lower()))
        else:
            close()
    close(bool(table))
    return names, blocks


def holds_code(folder):
    """True when a folder holds a file that is neither a document nor data nor a picture."""
    return any(f.is_file() and not f.name.startswith(".") and f.suffix.lower() not in SKIP_TYPES | NOT_CODE_TYPES
               and not SKIP_DIRS & set(f.relative_to(folder).parts) for f in folder.rglob("*"))


def documents_for(targets, left_out=None):
    """The documents that came with the code: next to it, in the folders above it, and anywhere in the
    workspace (the current folder) when the code is inside the workspace. Reports written by these scripts
    and notes files are not documents.

    A workspace may hold more than one body of code, each in its own folder with its own documents. When
    the folder of the workspace that holds the code has documents, the documents inside another folder of
    the workspace that holds code belong to that other code: they are not used, and are added to `left_out`
    when it is given."""
    docs, roots, mine = [], [], set()
    cwd = Path.cwd().resolve()

    def top(f):                              # the folder of the workspace, one level down, that holds f
        parts = f.relative_to(cwd).parts if cwd in f.parents else ()
        return parts[0] if len(parts) > 1 else None

    for target in targets:
        p = Path(target).resolve()
        folder = p if p.is_dir() else p.parent
        roots.append(folder)
        if cwd in folder.parents or folder == cwd:
            roots.append(cwd)
            mine.add(top(folder / "x"))
        else:
            roots += [a for a in folder.parents if len(a.parts) >= len(cwd.parts)][:2]
    for root in dict.fromkeys(roots):
        found = [f for f in root.rglob("*") if not SKIP_DIRS & set(f.relative_to(root).parts)
                 and not any(part.startswith(".") for part in f.relative_to(root).parts)] if root.is_dir() else []
        for f in sorted(found)[:5000]:
            if f.is_file() and f.suffix.lower() in DOC_TYPES and not f.name.startswith(".") \
                    and not f.name.endswith(".notes.md") and f not in docs and len(docs) < 50 \
                    and not f.name.lower().startswith("readme") and not written_by_script(f):
                docs.append(f)
    mine.discard(None)
    if mine & {top(f) for f in docs}:        # the folder that holds the code has documents of its own
        other = {t for t in {top(f) for f in docs} - mine - {None} if holds_code(cwd / t)}
        if left_out is not None:
            left_out += [f for f in docs if top(f) in other]
        docs = [f for f in docs if top(f) not in other]
    return docs


def written_by_script(path):
    """True for a report one of these scripts wrote: it is not a document that came with the code."""
    try:
        with open(path, "rb") as fh:
            start = fh.read(200).decode("utf-8", errors="replace")
    except OSError:
        return False
    return start.lstrip("﻿ \r\n").startswith(WRITTEN_BY_SCRIPT)


class Tok:
    __slots__ = ("kind", "val", "line", "sigil", "pos", "open")

    def __init__(self, kind, val, line, sigil="", pos=0):
        self.kind, self.val, self.line, self.sigil, self.pos = kind, val, line, sigil, pos
        self.open = False                    # a string whose closing quote is missing

    @property
    def key(self):
        return self.sigil + self.val


NOT_A_COMMENT = re.compile(r"#\s*(include|define|undef|ifdef|ifndef|if|else|elif|endif|pragma|region|endregion)\b|#!")


def style_for(path, hash_comments=False, text=None, fallback=None):
    """The comment style of a file: 'slash', 'hash', 'dash' or 'both'.

    Known file types are looked up. For any other type the file's own lines
    decide: the style most of its comment lines use. A file with no comment
    line takes `fallback`, the style of the other files of its type.
    """
    ext = Path(path).suffix.lower()
    if ext in BOTH_TYPES:
        return "both"
    if ext in HASH_TYPES:
        return "hash"
    if ext in DASH_TYPES:
        return "dash"
    if hash_comments:
        return "both"
    if text is None or ext in SLASH_TYPES:
        return "slash"
    slash = hash_ = dash = 0
    for line in text.split("\n"):
        start = line.lstrip()
        if start.startswith("//") or start.startswith("/*"):
            slash += 1
        elif start.startswith("#") and not NOT_A_COMMENT.match(start):
            hash_ += 1
        elif start.startswith("-- "):
            dash += 1
    if hash_ and slash:
        return "both"
    if hash_:
        return "hash"
    if dash and not slash:
        return "dash"
    return "slash" if slash or not fallback else fallback


def own_names(toks):
    """(the names that carry a prefix, the names without one that the code gives a value)."""
    prefixed = {x.val for x in toks if x.kind == "NAME" and x.sigil}
    bare = {x.val for j, x in enumerate(toks) if x.kind == "NAME" and not x.sigil and j + 1 < len(toks)
            and is_op(toks[j + 1], "=") and not (j and toks[j - 1].kind == "NAME" and toks[j - 1].line == x.line)}
    return prefixed, bare


def all_prefixed(prefixed, bare):
    """True for code whose own variables all carry a prefix."""
    return len(prefixed) >= 20 and len(bare) * 10 <= len(prefixed)


def lex(text, style="slash", patterns=False):
    """Split code into names, numbers, strings and operators; drop comments.

    With patterns=True, /.../ where a value is expected is read as one token,
    so that brackets and names inside a pattern are not taken for code.
    """
    if style is True or style is False:      # earlier callers passed a flag
        style = "both" if style else "slash"
    slash, hash_, dash = style in ("slash", "both"), style in ("hash", "both"), style == "dash"
    block = style != "hash"
    toks, i, n, line = [], 0, len(text), 1
    while i < n:
        c = text[i]
        if c == "\n":
            line += 1
            i += 1
        elif c in " \t\r":
            i += 1
        elif text.startswith("<?php", i):
            i += 5
        elif c == "#" and not hash_ and text[text.rfind("\n", 0, i) + 1:i].strip() == "":
            j = text.find("\n", i)              # a preprocessor or #! line
            i = n if j < 0 else j
        elif (slash and text.startswith("//", i)) or (hash_ and c == "#") \
                or (dash and text.startswith("--", i)):
            j = text.find("\n", i)
            i = n if j < 0 else j
        elif block and text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            line += text[i:j].count("\n")
            i = j
        elif text.startswith('"""', i) or text.startswith("'''", i):
            j = text.find(text[i:i + 3], i + 3)
            j = n if j < 0 else j
            toks.append(Tok("STR", text[i + 3:j], line, pos=i + 3))
            line += text[i:j].count("\n")
            i = min(n, j + 3)
        elif patterns and c == "/" and (not toks or (toks[-1].kind == "OP" and toks[-1].val not in (")", "]", "}"))
                                       or is_word(toks[-1], {"return", "typeof", "case", "in", "of"})):
            j, inside = i + 1, False
            while j < n and text[j] != "\n" and (inside or text[j] != "/"):
                inside = (text[j] == "[") or (inside and text[j] != "]")
                j += 2 if text[j] == "\\" else 1
            if j < n and text[j] == "/":
                j += 1
                while j < n and text[j].isalpha():
                    j += 1
                toks.append(Tok("PATTERN", text[i:j], line, pos=i))
                i = j
            else:
                toks.append(Tok("OP", c, line, pos=i))
                i += 1
        elif c in "\"'`":
            j = i + 1
            while j < n and text[j] != c and (c == "`" or text[j] != "\n"):
                j += 2 if text[j] == "\\" else 1
            toks.append(Tok("STR", text[i + 1:j], line, pos=i + 1))
            toks[-1].open = not (j < n and text[j] == c)
            line += text[i:j].count("\n")
            i = j + 1 if j < n and text[j] == c else j
        elif (c in "@$" or (c == "%" and (not toks or toks[-1].line < line
                                          or (toks[-1].kind == "OP" and toks[-1].val not in (")", "]"))))) \
                and i + 1 < n and (text[i + 1].isalpha() or text[i + 1] == "_"):
            j = i + 1
            while j < n and (text[j].isalnum() or text[j] == "_"):
                j += 1
            toks.append(Tok("NAME", text[i + 1:j], line, c, pos=i))
            i = j
        elif c.isalpha() or c == "_":
            j = i
            while j < n and (text[j].isalnum() or text[j] == "_"):
                j += 1
            toks.append(Tok("NAME", text[i:j], line, pos=i))
            i = j
        elif c.isdigit():
            j = i
            while j < n and (text[j].isalnum() or text[j] == "."):
                j += 1
            toks.append(Tok("NUM", text[i:j], line, pos=i))
            i = j
        else:
            for width, table in ((3, OPS3), (2, OPS2)):
                if text[i:i + width] in table:
                    toks.append(Tok("OP", text[i:i + width], line, pos=i))
                    i += width
                    break
            else:
                toks.append(Tok("OP", c, line, pos=i))
                i += 1
    return toks


def is_op(tok, *vals):
    return tok is not None and tok.kind == "OP" and tok.val in vals


def is_word(tok, words):
    return (tok is not None and tok.kind == "NAME" and not tok.sigil
            and tok.val.lower() in words)


def close_of(toks, i, opener="(", closer=")"):
    """Index of the bracket that closes the one at index i."""
    depth = 0
    for j in range(i, len(toks)):
        if is_op(toks[j], opener):
            depth += 1
        elif is_op(toks[j], closer):
            depth -= 1
            if depth == 0:
                return j
    return len(toks) - 1


def statement_ends(toks):
    """Indexes of the tokens that end a statement.

    A statement ends at a ; and, for code written without them, at the last
    token of a line when no bracket is open, the line does not end with an
    operator and the next line does not start with one.
    """
    ends, depth, n = set(), 0, len(toks)
    for i, t in enumerate(toks):
        if is_op(t, "(", "["):
            depth += 1
        elif is_op(t, ")", "]"):
            depth = max(0, depth - 1)
        if is_op(t, ";"):
            ends.add(i)
            continue
        nxt = toks[i + 1] if i + 1 < n else None
        if depth or (nxt is not None and nxt.line == t.line):
            continue
        if t.kind == "OP" and t.val not in (")", "]", "}", "++", "--"):
            continue                         # { or an operator: not the end of a statement
        if nxt is not None and ((nxt.kind == "OP" and nxt.val not in ("(", "[", "{", "}", "++", "--", "!"))
                                or is_word(nxt, {"and", "or", "in", "like"})):
            continue                         # the next line carries the statement on
        ends.add(i)
    return ends


def same_word(a, b):
    """True when two names are one word written two ways: letter case, or two letters swapped."""
    if a == b or len(a) != len(b) or len(a) < 4:
        return False
    if a.lower() == b.lower():
        return True
    diff = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
    return (len(diff) == 2 and diff[1] == diff[0] + 1
            and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]])


def near(a, b):
    """True when two names differ by letter case only, by one letter, or by two swapped letters."""
    if a == b or min(len(a), len(b)) < 4:
        return False
    if a.lower() == b.lower():
        return True
    a, b = a.lower(), b.lower()
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        diff = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
        if len(diff) == 1:
            return not (a[diff[0]].isdigit() or b[diff[0]].isdigit())
        return (len(diff) == 2 and diff[1] == diff[0] + 1          # two letters swapped
                and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]])
    short, long_ = (a, b) if len(a) < len(b) else (b, a)
    for k in range(len(long_)):
        if long_[:k] + long_[k + 1:] == short:
            return not long_[k].isdigit()
    return False


def structure_checks(scan, name, toks, ends, in_cond, in_log, conds):
    """Checks on the shape of the code: brackets, conditions, blocks, loops, handlers, text in strings."""
    n = len(toks)
    at = lambda i: toks[i] if 0 <= i < n else None
    hit = lambda key, line, note="": scan.hits[key].append((name, line, note))

    # brackets that do not balance
    pairs, stack, match, bad = {")": "(", "]": "[", "}": "{"}, [], {}, []
    for i, t in enumerate(toks):
        if t.kind != "OP":
            continue
        if t.val in ("(", "[", "{"):
            stack.append(i)
        elif t.val in pairs:
            if stack and toks[stack[-1]].val == pairs[t.val]:
                match[stack.pop()] = i
            else:
                bad.append((t.line, "%s closes nothing that is open" % t.val))
    bad += [(toks[i].line, "%s is never closed" % toks[i].val) for i in stack]
    if bad:
        bad.sort()
        hit("brackets", bad[0][0], "%s; %d bracket(s) without a pair in this file" % (bad[0][1], len(bad)))

    # && and || mixed in one group without brackets
    for kw, a, b in conds:
        groups, found = [set()], None
        for j in range(a, b):
            t = toks[j]
            if is_op(t, "("):
                groups.append(set())
            elif is_op(t, ")"):
                if len(groups) > 1:
                    groups.pop()
            else:
                kind = "and" if is_op(t, "&&") or is_word(t, {"and"}) else \
                       "or" if is_op(t, "||") or is_word(t, {"or"}) else None
                if kind:
                    groups[-1].add(kind)
                    if len(groups[-1]) == 2 and found is None:
                        found = t.line
        if found:
            hit("mixed", found)

    # the same condition twice in one if / else-if chain
    cond_at = {kw: (a, b) for kw, a, b in conds}
    words = lambda a, b: " ".join("'%s'" % t.val if t.kind == "STR" else t.sigil + t.val for t in toks[a:b])
    done = set()
    for kw, a, b in conds:
        if kw in done or not is_word(toks[kw], {"if"}) or is_word(at(kw - 1), {"else"}):
            continue
        seen, bodies, cur = {}, {}, kw

        def same_body(j, line):
            """Report a branch whose block holds the same statements as an earlier branch of the chain."""
            body = words(j + 1, match[j])
            if len(body) >= 12:
                if body in bodies:
                    hit("dupbranch", line, "same statements as the branch on line %d" % bodies[body])
                else:
                    bodies[body] = line

        while cur is not None:
            a2, b2 = cond_at[cur]
            done.add(cur)
            text = words(a2, b2)
            if text in seen:
                hit("repeat", toks[cur].line, "same condition as line %d" % seen[text])
            else:
                seen[text] = toks[cur].line
            j = b2 + 1 if is_op(at(b2), ")") else b2
            if not is_op(at(j), "{") or j not in match:
                break
            same_body(j, toks[cur].line)
            nxt = match[j] + 1
            if is_word(at(nxt), {"elseif", "elsif", "elif"}) and nxt in cond_at:
                cur = nxt
            elif is_word(at(nxt), {"else"}) and is_word(at(nxt + 1), {"if"}) and nxt + 1 in cond_at:
                cur = nxt + 1
            else:
                if is_word(at(nxt), {"else"}) and is_op(at(nxt + 1), "{") and nxt + 1 in match:
                    same_body(nxt + 1, at(nxt).line)
                cur = None

    # the same condition twice in a chain written without braces: if ... / elif ... at one indentation
    if not match or scan.styles.get(name) == "hash":
        text = scan.text[name]
        column = lambda tok: tok.pos - (text.rfind("\n", 0, tok.pos) + 1)
        chain = None                                              # (column, {condition: line})
        for kw, a, b in conds:
            word = toks[kw].val.lower()
            if word == "if" and not is_word(at(kw - 1), {"else"}) and (kw == 0 or at(kw - 1).line < toks[kw].line):
                chain = (column(toks[kw]), {words(a, b): toks[kw].line})
            elif word in ("elif", "elsif", "elseif") and chain and column(toks[kw]) == chain[0]:
                cond = words(a, b)
                if cond in chain[1]:
                    hit("repeat", toks[kw].line, "same condition as line %d" % chain[1][cond])
                chain[1].setdefault(cond, toks[kw].line)

    # a value compared with itself, two fixed values compared, a name assigned to itself
    part = (".", "->", "::", "]", ")", "+", "-", "*", "/", "%")
    for i, t in enumerate(toks):
        left, right = at(i - 1), at(i + 1)
        if left is None or right is None or t.kind != "OP":
            continue
        if t.val in COMPARE_OPS:
            if is_op(at(i - 2), *part) or is_op(at(i + 2), ".", "->", "::", "[", "(", "+", "-", "*", "/", "%"):
                continue
            if left.kind == "NAME" and right.kind == "NAME" and left.key == right.key \
                    and (left.sigil or left.val.lower() not in KEYWORDS):
                hit("self", t.line, "%s compared with itself" % left.key)
            elif left.kind in ("NUM", "STR") and right.kind in ("NUM", "STR") and i in in_cond:
                hit("self", t.line, "two fixed values compared")
        elif t.val == "=" and i not in in_cond and left.kind == "NAME" and right.kind == "NAME" \
                and left.key == right.key and (i - 2 < 0 or i - 2 in ends or is_op(at(i - 2), "{", "}")) \
                and (i + 1 in ends or i + 1 == n - 1 or is_op(at(i + 2), ";")):
            hit("self", t.line, "%s assigned to itself" % left.key)

    # else or else-if that does not follow an if (in code that marks blocks with braces: the languages that
    # write comments with // do, and so does any code where four conditions in five are followed by a {)
    with_block = sum(1 for kw, a, b in conds if is_op(at(b + 1), "{"))
    if match and (scan.styles.get(name) in ("slash", "both") or (len(conds) >= 5 and with_block * 5 >= len(conds) * 4)):
        open_of = {c: o for o, c in match.items()}
        keyword_of = {b: kw for kw, a, b in conds}
        for i, t in enumerate(toks):
            if not is_word(t, {"else", "elseif", "elsif", "elif"}) or is_op(at(i - 1), ".", "->", "::"):
                continue
            p, follows_if = i - 1, False
            if is_op(at(p), ";"):            # if (a) x(); else ... : the statement before must hang on an if
                j = p - 1
                while j >= 0 and not follows_if:
                    follows_if = (j in keyword_of and is_word(toks[keyword_of[j]], {"if", "elseif", "elsif", "elif"})) \
                        or is_word(toks[j], {"else"})
                    if j in ends or is_op(toks[j], "{", "}"):
                        break
                    j -= 1
            elif is_op(at(p), "}") and p in open_of:
                before_block = open_of[p] - 1
                follows_if = (before_block in keyword_of
                              and is_word(toks[keyword_of[before_block]], {"if", "elseif", "elsif", "elif"})) \
                    or is_word(at(before_block), {"then"})
            if not follows_if:
                hit("orphan", t.line)

    braces = scan.styles.get(name) in ("slash", "both") and bool(match)
    ext = Path(name).suffix.lower()

    # one name compared with two values in a way that is never true, or always true
    def contradiction(parts, kinds, line):
        if len(kinds) != 1:
            return
        want = "==" if kinds == {"and"} else "!="
        values = {}
        for part in parts:
            if len(part) >= 3 and part[0].kind in ("STR", "NUM"):
                part = part[2:] + [part[1], part[0]]             # 5 == x: put the name first
            k = 1
            while k + 1 < len(part) and part[0].kind == "NAME" and is_op(part[k], ".", "->") \
                    and part[k + 1].kind == "NAME":
                k += 2                                             # row.severity is one name
            if len(part) == k + 2 and part[0].kind == "NAME" and part[k].kind == "OP" \
                    and part[k].val in (want, want + "=") and part[k + 1].kind in ("STR", "NUM"):
                key = "".join(x.sigil + x.val if x.kind == "NAME" else x.val for x in part[:k])
                value = part[k + 1]
                shown = "'%s'" % value.val if value.kind == "STR" else value.val
                if key in values and values[key] != shown:
                    hit("contra", line, "%s %s both %s and %s" % (
                        key, "cannot equal" if want == "==" else "always differs from one of", values[key], shown))
                    return
                values.setdefault(key, shown)

    for kw, a, b in conds:
        groups, kinds = [[[]]], [set()]
        for j in range(a, b):
            t = toks[j]
            if is_op(t, "("):
                groups.append([[]])
                kinds.append(set())
            elif is_op(t, ")"):
                if len(groups) > 1:
                    contradiction(groups.pop(), kinds.pop(), t.line)
                    groups[-1][-1].append(t)     # the bracketed part is one operand of the outer group
            elif is_op(t, "&&", "||") or is_word(t, {"and", "or"}):
                kinds[-1].add("and" if t.val in ("&&", "and") else "or")
                groups[-1].append([])
            else:
                groups[-1][-1].append(t)
        contradiction(groups[0], kinds[0], toks[kw].line)
        # a ; straight after the condition ends the statement: the condition controls nothing
        if is_op(at(b), ")") and is_op(at(b + 1), ";") \
                and not (is_word(toks[kw], {"while", "until"}) and is_op(at(kw - 1), "}")):
            hit("semi", toks[kw].line)
            scan.fixes.append((name, at(b + 1).pos, ";", "", "semi", at(b + 1).line))

    for i, t in enumerate(toks):
        # a statement that only compares: an assignment may have been meant
        if is_op(t, "==", "===") and i not in in_cond and at(i - 1) is not None and at(i - 1).kind == "NAME" \
                and at(i + 1) is not None and at(i + 1).kind in ("NAME", "STR", "NUM") \
                and (i - 2 < 0 or i - 2 in ends or is_op(at(i - 2), "{", "}")) \
                and (i + 1 in ends or i + 1 == n - 1 or is_op(at(i + 2), ";")):
            hit("noeffect", t.line, "%s %s ..." % (at(i - 1).key, t.val))
        # code after a statement that leaves the block
        if braces and is_word(t, {"return", "break", "continue", "exit", "throw"}) \
                and not is_op(at(i - 1), ".", "->", "::") and (i == 0 or i - 1 in ends or is_op(at(i - 1), "{", "}")):
            e = i
            while e < n - 1 and e not in ends:
                e += 1
            nxt = at(e + 1)
            if nxt is not None and not is_op(nxt, "}") and not is_word(
                    nxt, {"case", "default", "else", "elseif", "elsif", "elif", "catch", "finally"}):
                hit("unreach", nxt.line, "after %s on line %d" % (t.val, t.line))
        # the same label twice in one switch
        if is_word(t, {"switch"}) and is_op(at(i + 1), "("):
            j = close_of(toks, i + 1) + 1
            if is_op(at(j), "{") and j in match:
                labels, depth, q = {}, 0, j + 1
                while q < match[j]:
                    depth += is_op(toks[q], "{") - is_op(toks[q], "}")
                    if depth == 0 and is_word(toks[q], {"case"}):
                        e = q + 1
                        while e < match[j] and not is_op(toks[e], ":"):
                            e += 1
                        label = words(q + 1, e)
                        if label in labels:
                            hit("dupcase", toks[q].line, "same label as line %d" % labels[label])
                        labels.setdefault(label, toks[q].line)
                        q = e
                    q += 1
        # a string whose closing quote is missing
        if t.kind == "STR" and t.open and scan.styles.get(name) in ("slash", "both") and ext != ".php":
            hit("strclose", t.line)
        # a command or code run with text joined to a value
        if is_word(t, COMMAND_WORDS) and is_op(at(i + 1), "("):
            inside = toks[i + 2:close_of(toks, i + 1)]
            if any(x.kind == "STR" for x in inside) and any(is_op(x, "+", ".", "&") for x in inside) \
                    and any(x.kind == "NAME" and (x.sigil or x.val.lower() not in KEYWORDS) for x in inside):
                hit("command", t.line, t.val)
        # in a shell script: eval or exec given text and a variable
        if is_word(t, {"eval"}) and ext in SHELL_TYPES and not is_op(at(i + 1), "("):
            rest = [x for x in toks[i + 1:i + 12] if x.line == t.line]
            if any(x.kind == "STR" for x in rest) and any(
                    (x.kind == "NAME" and x.sigil) or (x.kind == "STR" and "$" in x.val) for x in rest):
                hit("command", t.line, t.val)
        # a credential written into the code
        if t.kind == "NAME" and CREDENTIAL_NAME.search(t.val) and is_op(at(i + 1), "=") and i not in in_cond \
                and at(i + 2) is not None and at(i + 2).kind == "STR" and len(at(i + 2).val.strip()) >= 3:
            hit("secret", t.line, "a value for %s" % t.key)
        # x = Replace(x, "a", "b"): remembered, to see whether the same replacement is made twice
        if is_word(t, REPLACE_WORDS) and is_op(at(i + 1), "(") and is_op(at(i - 1), "=") and at(i - 2) is not None \
                and at(i - 2).kind == "NAME" and at(i + 2) is not None and at(i + 2).kind == "NAME" \
                and at(i + 2).key == at(i - 2).key and is_op(at(i + 3), ",") and at(i + 4) is not None \
                and at(i + 4).kind == "STR" and is_op(at(i + 5), ",") and at(i + 6) is not None and at(i + 6).kind == "STR":
            scan.replaces[at(i - 2).key].append((name, t.line, at(i + 4).val, at(i + 6).val,
                                                 tuple(a for a, b in sorted(match.items()) if a < i < b)))
        # a replace call limited to a count: the last argument is a whole number above 1
        if is_word(t, REPLACE_WORDS) and is_op(at(i + 1), "("):
            end = close_of(toks, i + 1)
            last_arg = at(end - 1)
            if end - i > 4 and is_op(at(end - 2), ",") and last_arg is not None and last_arg.kind == "NUM" \
                    and last_arg.val.isdigit() and int(last_arg.val) > 1:
                hit("capped", t.line, "%s limited to %s replacements" % (t.val, last_arg.val))
        # an index compared with <= to a size
        if is_op(t, "<=") and ((is_word(at(i + 1), COUNT_WORDS) and is_op(at(i + 2), "("))
                               or (at(i + 1) is not None and at(i + 1).kind == "NAME" and is_op(at(i + 2), ".")
                                   and is_word(at(i + 3), COUNT_WORDS))):
            hit("bound", t.line)

    # a block with nothing in it
    for i, t in enumerate(toks):
        if is_op(t, "{") and is_op(at(i + 1), "}"):
            p = at(i - 1)
            if is_op(p, ")") or is_word(p, {"else", "try", "do", "finally", "then"}) \
                    or (p is not None and p.kind == "NAME" and (is_op(at(i - 2), ".")
                                                                or is_word(at(i - 2), HANDLER_WORDS))):
                hit("empty", t.line)

    # a loop whose condition nothing inside the loop changes
    for kw, a, b in conds:
        j = b + 1 if is_op(at(b), ")") else b
        if not is_word(toks[kw], {"while", "until"}) or not is_op(at(j), "{") or j not in match:
            continue
        keys, calls = set(), False
        for q in range(a, b):
            x = toks[q]
            if x.kind != "NAME" or (not x.sigil and x.val.lower() in KEYWORDS):
                continue
            if is_op(at(q + 1), "("):
                calls = calls or x.val.lower() not in SIZE_WORDS
            elif not is_op(at(q - 1), ".", "->", "::"):
                keys.add(x.key)
        if not keys or calls or any(is_op(toks[q], "++", "--", *ASSIGN_OPS) for q in range(a, b)):
            continue
        changed = False
        for q in range(j + 1, match[j]):
            x = toks[q]
            if is_word(x, LEAVE_WORDS):
                changed = True
            elif x.kind == "NAME" and x.key in keys and not is_op(at(q - 1), ".", "->", "::"):
                k = q + 1
                while is_op(at(k), "[", ".", "->"):
                    k = close_of(toks, k, "[", "]") + 1 if is_op(at(k), "[") else k + 2
                changed = (is_op(at(k), *ASSIGN_OPS) or is_op(at(q + 1), "++", "--") or is_op(at(q - 1), "++", "--")
                           # handed to a call, which may change it
                           or (q not in in_log and is_op(at(q - 1), "(", ",") and is_op(at(q + 1), ",", ")")))
            if changed:
                break
        if not changed:
            hit("loop", toks[kw].line, "nothing inside the loop assigns %s" % ", ".join(sorted(keys)))

    # an error handler that only logs
    for i, t in enumerate(toks):
        if not is_word(t, HANDLER_WORDS) or is_op(at(i - 1), ".", "->", "::"):
            continue
        j = i + 1
        while j < n and not is_op(toks[j], "{", ";") and toks[j].line <= t.line + 1:
            j = close_of(toks, j) + 1 if is_op(toks[j], "(") else j + 1
        if not is_op(at(j), "{") or j not in match or match[j] == j + 1:
            continue
        q, only_logs = j + 1, True
        while q < match[j] and only_logs:
            k = q
            while at(k) is not None and at(k).kind == "NAME" and is_op(at(k + 1), ".", "->", "::"):
                k += 2
            if at(k) is not None and at(k).kind == "NAME" and at(k).val.lower() in LOG_CALLS \
                    and is_op(at(k + 1), "("):
                q = close_of(toks, k + 1) + 1
                q += is_op(at(q), ";")
            else:
                only_logs = False
        scan.handlers[name].append((t.line, toks[match[j]].line, only_logs))
        for line in range(toks[j].line, toks[match[j]].line + 1):
            scan.handler_of[(name, line)] = t.line
        if only_logs:
            hit("handler", t.line)

    # text in strings, logging left out: a query joined with a value; an environment name,
    # an address or a credential
    for i, t in enumerate(toks):
        if t.kind != "STR" or i in in_log:
            continue
        nxt, after = at(i + 1), at(i + 2)
        if QUERY.search(t.val) and after is not None and (
                (is_op(nxt, "+", "||", "&") and (after.kind == "NAME" or is_op(after, "(")))
                or (is_op(nxt, ".") and after.kind == "NAME" and after.sigil)):
            joined, depth, j = [], 0, i + 1          # what is joined to the text, up to the end of the value
            while j < n:
                x = toks[j]
                if is_op(x, "(", "["):
                    depth += 1
                elif is_op(x, ")", "]"):
                    if depth == 0:
                        break
                    depth -= 1
                elif (is_op(x, ",") and depth == 0) or is_op(x, ";"):
                    break
                elif x.kind == "NAME" and (x.sigil or x.val.lower() not in KEYWORDS):
                    joined.append(x.key + "()" if is_op(at(j + 1), "(") else x.key)
                if j in ends:
                    break
                j += 1
            hit("query", t.line, "joins %s" % ", ".join(dict.fromkeys(joined)) if joined else "")
        found = [m.group(0) for m in ENV.finditer(t.val)]
        found += [m.group(0) for m in ADDRESS.finditer(t.val)
                  if "/" in m.group(0) or all(int(x) < 256 for x in m.group(0).split("."))]
        found += ["a value for %s" % m.group(1) for m in CREDENTIAL.finditer(t.val)]
        if found:
            hit("secret", t.line, ", ".join(dict.fromkeys(found)))

    # functions: where each is defined, and every other place its name appears
    for i, t in enumerate(toks):
        if t.kind != "NAME" or t.sigil:
            continue
        if is_word(at(i - 1), FUNC_WORDS) and is_op(at(i + 1), "("):
            scan.declared[t.val].append((name, t.line))
        else:
            scan.mentioned[t.val] += 1


class Scan:
    def __init__(self):
        self.lines = {}                      # file -> list of source lines
        self.reads = defaultdict(list)       # name -> [(file, line)]
        self.assigns = defaultdict(list)
        self.members = defaultdict(list)     # .name -> [(file, line)], calls left out
        self.bases = defaultdict(list)       # name -> [(file, line)] where a call is made on it
        self.filled = set()                  # names given a value part by part: x.y = ..., x[i] = ...
        self.types = set()                   # names of types: declared in the code, or written as List<Item>
        self.in_strings = []                 # (file, line, name, written with $, shell script)
        self.set_in_code = set()             # prefixes whose names never come from outside the code
        self.hits = defaultdict(list)        # check -> [(file, line, note)]
        self.tags = defaultdict(lambda: [0, 0, []])   # tag -> opens, closes, statements
        self.styles = {}                     # file -> comment style used to read it
        self.encoding = {}                   # file -> encoding it was read with
        self.text = {}                       # file -> its whole text
        self.read_at = defaultdict(list)     # name -> [(file, line, position)] of each read
        self.set_at = defaultdict(list)      # name -> [(file, line, position)] of each plain assignment
        self.fixes = []                      # (file, position, old text, new text, kind, line)
        self.literals = defaultdict(list)    # a word written as text in a string -> the quote of each place
        self.tag_fixes = defaultdict(list)   # tag -> the same, kept until the tag is known to be unbalanced
        self.judge = set()                   # (check, file, line, name): needs a person to decide
        self.early = []                      # (file, name, line of the read, line that first sets it)
        self.set_in_function = defaultdict(set)   # file -> names given a value inside a function
        self.declared = defaultdict(list)    # function name -> [(file, line)]
        self.mentioned = defaultdict(int)    # name -> times it appears other than where it is declared
        self.skipped = []                    # (file, reason)
        self.notes = []                      # checks that were not applied, and why
        self.body_style = {}                 # file type -> how its files write comments, taken together
        self.body_marked = set()             # file types whose own variables all carry a prefix, taken together
        self.docs = []                       # documents next to the code
        self.names = {}                      # a name listed in one of them -> (document, line, type)
        self.name_lists = []                 # (document, first line, last line, how many names)
        self.includes = []                   # (file, line, the file it includes, as written)
        self.given = {}                      # name -> (included file, line) that defines it
        self.not_found = []                  # (file, line, included file that is not next to the code)
        # What the scan can say about a hit by itself, each keyed by (check, file, line, note):
        self.cleared = {}                    # -> why the hit is not a defect
        self.proven = {}                     # -> the evidence that makes the hit a finding as it stands
        self.for_owner = {}                  # -> the question only the owner of the code can answer
        self.handlers = defaultdict(list)    # file -> [(first line, last line, it only logs)]
        self.handler_of = {}                 # (file, line) -> first line of the error handler the line is in
        self.where = {}                      # file -> {line: (what the statement does, [blocks it is in])}
        self.outline = {}                    # file -> [(first line, last line, what introduces the block, depth)]
        self.flows = {}                      # file -> [(first line, last line, name assigned, names read)]
        self.sets = defaultdict(list)        # name -> [(file, line, last line, reads itself, blocks, in a loop)]
        self.replaces = defaultdict(list)    # name -> [(file, line, pattern, replacement, blocks)]
        self._unused = None                  # names whose value is never used, once worked out
        self.external = set()                # prefixes of names that hold data from outside the code

    def add_documents(self, paths):
        """Read the lists of names in the documents that came with the code."""
        for p in paths:
            if str(p) in self.docs:
                continue
            self.docs.append(str(p))
            names, blocks = names_in(p)
            for name, (line, kind) in names.items():
                self.names.setdefault(name, (str(p), line, kind))
            self.name_lists += [(str(p), first, last, count) for first, last, count in blocks]

    def learn(self, files, hash_comments=False):
        """What the files of one type show when taken together, for a file too small to show it by itself
        (one part of code that was split): how comments are written, and whether the code's own variables
        all carry a prefix. Call it before the files are scanned."""
        texts = defaultdict(list)
        for f in files:
            try:
                raw = Path(f).read_bytes()
            except OSError:
                continue
            if b"\0" not in raw[:8192]:
                texts[Path(f).suffix.lower()].append(raw.decode("utf-8", errors="replace"))
        for ext, parts in texts.items():
            if len(parts) < 2:
                continue
            whole = "\n".join(parts)
            style = self.body_style[ext] = style_for("x" + ext, hash_comments, whole)
            if all_prefixed(*own_names(lex(whole, style, ext in REGEX_TYPES))):
                self.body_marked.add(ext)

    def add_file(self, path, hash_comments=False):
        """Scan one file. Returns False, and scans nothing, if it is not readable text."""
        name = str(path)
        try:
            raw = Path(path).read_bytes()
        except OSError:
            self.skipped.append((name, "could not be read"))
            return False
        if b"\0" in raw[:8192]:
            self.skipped.append((name, "not a text file"))
            return False
        try:                                 # keep the file's own encoding, so that a corrected
            text = raw.decode("utf-8")       # copy can be written back byte for byte
            self.encoding[name] = "utf-8"
        except UnicodeDecodeError:
            text = raw.decode("latin-1")
            self.encoding[name] = "latin-1"
        ext = Path(path).suffix.lower()
        style = self.styles[name] = style_for(path, hash_comments, text, self.body_style.get(ext))
        self.lines[name] = text.split("\n")
        self.text[name] = text
        toks = lex(script_of(text) if ext in PAGE_TYPES else text, style, ext in REGEX_TYPES)
        n = len(toks)
        at = lambda i: toks[i] if 0 <= i < n else None

        ends = statement_ends(toks)
        in_cond, in_log, params = set(), set(), set()
        conds = []                           # (index of the keyword, first token, one past the last)
        in_function = set()                  # tokens inside the body of a function

        def body_after(j):
            """Mark the block that opens at or just after token j as the body of a function."""
            if is_word(at(j), {"throws"}):
                while j < n and not is_op(toks[j], "{", ";"):
                    j += 1
            if is_op(at(j), "{"):
                in_function.update(range(j, close_of(toks, j, "{", "}") + 1))

        for i, t in enumerate(toks):
            if is_word(t, COND_WORDS) and not is_op(at(i - 1), ".", "->", "::"):
                if is_op(at(i + 1), "("):
                    close = close_of(toks, i + 1)
                    in_cond.update(range(i + 2, close))
                    conds.append((i, i + 2, close))
                else:
                    j = i + 1
                    while j < n and toks[j].line == t.line and not is_op(toks[j], "{", ":") \
                            and not is_word(toks[j], {"then"}):
                        in_cond.add(j)
                        j += 1
                    conds.append((i, i + 1, j))
            elif is_word(t, LOG_CALLS) and is_op(at(i + 1), "("):
                in_log.update(range(i + 2, close_of(toks, i + 1)))
            elif is_word(t, FUNC_WORDS):
                j = i + 1 if is_op(at(i + 1), "(") else i + 2
                if is_op(at(j), "("):
                    end, first, depth = close_of(toks, j), True, 0
                    for q in range(j + 1, end):
                        depth += is_op(toks[q], "(", "[", "<", "{") - is_op(toks[q], ")", "]", ">", "}")
                        if is_op(toks[q], ",") and depth <= 0:
                            first, depth = True, 0
                        elif toks[q].kind == "NAME" and first and not is_word(toks[q], DECL_WORDS | TYPE_NAMES):
                            sigil_later = any(x.kind == "NAME" and x.sigil for x in toks[q + 1:end]
                                              if not toks[q].sigil) and not toks[q].sigil \
                                and at(q + 1) is not None and at(q + 1).kind == "NAME" and at(q + 1).sigil
                            if not sigil_later:           # `array $items`: the prefixed name is the parameter
                                params.add(q)
                                first = False
                    while end + 1 < n and not is_op(toks[end + 1], "{", ";") and toks[end + 1].line == toks[end].line:
                        end += 1                          # a return type between ) and {
                    body_after(end + 1)
            elif is_word(t, DECL_WORDS) and is_op(at(i + 1), "("):
                params.update(range(i + 2, close_of(toks, i + 1)))   # my ($a, $b) = ...
            elif t.kind == "NAME" and not t.sigil and is_op(at(i + 1), "(") \
                    and (t.val.lower() not in KEYWORDS or t.val.lower() == "catch"):
                end = close_of(toks, i + 1)
                if t.val.lower() != "catch" and (is_op(at(end + 1), "{") or is_word(at(end + 1), {"throws"})):
                    body_after(end + 1)
                if is_op(at(end + 1), "{") or is_word(at(end + 1), {"throws"}):
                    last = None
                    for j in range(i + 2, end + 1):
                        if toks[j].kind == "NAME":
                            last = j
                        elif is_op(toks[j], ",", ")") and last is not None:
                            params.add(last)
                            last = None
            elif is_word(t, LOOP_WORDS):
                j = i + 2 if is_op(at(i + 1), "(") else i + 1
                while is_word(at(j), DECL_WORDS):
                    j += 1
                if at(j) is not None and at(j).kind == "NAME" and is_word(at(j + 1), {"in", "of"}):
                    params.add(j)

        # blocks: which { is closed where, what introduces each block, and which blocks are loops
        pair, opened = {}, []
        for i, t in enumerate(toks):
            if is_op(t, "{"):
                opened.append(i)
            elif is_op(t, "}") and opened:
                pair[opened.pop()] = i
        closers = set(pair.values())

        def header_of(j):
            """(text, line, first word) of what introduces the block that opens at token j; None for a plain block."""
            p = j - 1
            if p < 0:
                return None
            if is_op(toks[p], ")"):              # if (...) { : go back to the word before the (
                depth = 0
                while p >= 0:
                    depth += is_op(toks[p], ")") - is_op(toks[p], "(")
                    if depth == 0:
                        break
                    p -= 1
                p -= 1
            if p < 0:
                return None
            line = toks[p].line                  # ... and to the first token of that line that belongs to it
            while p > 0 and toks[p - 1].line == line and not is_op(toks[p - 1], "{", "}", ";"):
                p -= 1
            word = toks[p].val.lower() if toks[p].kind == "NAME" and not toks[p].sigil else ""
            if word not in COND_WORDS | LOOP_WORDS | HANDLER_WORDS | FUNC_WORDS | {
                    "else", "try", "do", "finally", "switch"}:
                return None
            shown = " ".join(text[toks[p].pos:toks[j].pos].split())
            return (shown if len(shown) <= 90 else shown[:87] + "..."), toks[p].line, word

        # what each line is part of: what its statement does, and the blocks it is inside
        first_of_line, inside, loop_blocks, part_of, outline, flows = {}, [], [], {}, [], []
        for i, t in enumerate(toks):
            first_of_line.setdefault(t.line, i)
        for i, t in enumerate(toks):
            if first_of_line[t.line] == i:
                blocks = [b for b in inside if b is not None][-2:][::-1]       # the innermost first
                if blocks:
                    part_of.setdefault(t.line, ["", []])[1] = blocks
            if is_op(t, "{") and i in pair:
                head = header_of(i)
                if head:                         # the outline of the code: each block that a keyword introduces
                    outline.append((head[1], toks[pair[i]].line, head[0], sum(1 for b in inside if b is not None)))
                inside.append(head[:2] if head else None)
                if head and head[2] in LOOP_WORDS | {"while", "until", "do"}:
                    loop_blocks.append((i, pair[i], head[1]))
            elif is_op(t, "}") and i in closers and inside:
                inside.pop()
            starts = i == 0 or i - 1 in ends or is_op(at(i - 1), "{", "}")
            if starts and t.kind == "NAME" and (t.sigil or t.val.lower() not in KEYWORDS):
                k = i + 1
                while is_op(at(k), "[", ".", "->", "::"):
                    k = close_of(toks, k, "[", "]") + 1 if is_op(at(k), "[") else k + 2
                does = "sets" if is_op(at(k), *ASSIGN_OPS) and i not in in_cond else "calls" if is_op(at(k), "(") else ""
                if does and at(k).pos - t.pos <= 80:
                    last = i
                    while last < n - 1 and last not in ends:
                        last += 1
                    if does == "sets":           # the names this assignment reads: where their values go
                        used = {x.key for q, x in enumerate(toks[k + 1:last + 1], k + 1) if x.kind == "NAME"
                                and (x.sigil or x.val.lower() not in KEYWORDS) and not is_op(at(q - 1), ".", "->", "::")
                                and not (not x.sigil and is_op(at(q + 1), "("))}
                        flows.append((t.line, toks[last].line, t.key, used))
                    for line in range(t.line, toks[last].line + 1):
                        part_of.setdefault(line, ["", []])
                        part_of[line][0] = part_of[line][0] or "%s `%s`" % (does, "".join(text[t.pos:at(k).pos].split()))
        self.where[name] = part_of
        self.outline[name] = outline
        self.flows[name] = flows

        # 1. assignment in a condition
        seen = defaultdict(int)
        if ext in EQUALS_COMPARES:
            self.notes.append("%s: 'Assignment in a condition' not applied; in this language "
                              "a single = in a condition compares" % Path(path).name)
        else:
            depth_at, depth = {}, 0
            for i in sorted(in_cond):
                depth += is_op(toks[i], "(") - is_op(toks[i], ")")
                depth_at[i] = depth
                # in a # language, name=value inside a call is a named argument
                named_arg = style == "hash" and depth > 0 and is_op(at(i - 2), "(", ",")
                if is_op(toks[i], "=") and not named_arg:
                    seen[toks[i].line] += 1
                    self.fixes.append((name, toks[i].pos, "=", "==", "cond", toks[i].line))
        for line, count in sorted(seen.items()):
            self.hits["cond"].append((name, line, "" if count == 1 else "%d times on this line" % count))

        # names: who is read, who is assigned
        last_assign = None                   # (name, index of the ; that ended it)
        # Code whose own variables all carry a prefix: a word without one is then a word of the
        # language, or the name of something declared, and not a variable that was never set.
        # A small file is judged with the other files of its type.
        prefixed, own_bare = own_names(toks)
        marked = ext in self.body_marked or all_prefixed(prefixed, own_bare)
        for j, x in enumerate(toks):
            if is_word(x, INCLUDE_WORDS) and at(j + 1) is not None and at(j + 1).kind == "STR" \
                    and at(j + 1).line == x.line and (j == 0 or at(j - 1).line < x.line or is_op(at(j - 1), ";", "{", "}")):
                self.includes.append((name, x.line, at(j + 1).val))
        first_read, first_set, set_in_function = {}, {}, set()
        from_call = {}                       # name -> line where it was given the result of a call
        shell = ext in SHELL_TYPES
        if shell:
            self.set_in_code.add("$")        # in a shell script every $NAME is set by the script or the shell
        for t in toks:                       # variables written inside strings are read there
            if t.kind == "STR" and (text[t.pos - 1:t.pos] != "'" or not shell):
                for m in IN_STRING.finditer(t.val):
                    self.in_strings.append((name, t.line, m.group(1) or m.group(2), bool(m.group(1)), shell))

        def note_set(t, i):
            if i in in_function or i in params:
                set_in_function.add(t.key)
            first_set.setdefault(t.key, (i, t.line))

        indexed = {}                         # name -> where its hit is, until its size is checked or it is set again

        def note_read(t, i):
            if i not in in_function:
                first_read.setdefault(t.key, (i, t.line))
            sized = (is_op(at(i - 1), "(") and is_word(at(i - 2), SIZE_WORDS)) \
                or (is_op(at(i + 1), ".") and is_word(at(i + 2), SIZE_WORDS))
            if t.key in from_call:           # the result of a call, not yet checked
                if is_op(at(i + 1), "["):
                    self.hits["index"].append((name, t.line, "%s — holds the result of the call on line %d"
                                               % (t.key, from_call.pop(t.key))))
                    indexed[t.key] = len(self.hits["index"]) - 1
                elif i in in_log:
                    pass                     # printing its size is not checking it
                elif i in in_cond or sized:
                    del from_call[t.key]     # its size or presence is looked at first
            elif t.key in indexed and sized and i not in in_log:
                # the size is checked after the index: the code itself expects that the result can be empty
                at_hit = indexed.pop(t.key)
                f, line, note = self.hits["index"][at_hit]
                self.hits["index"][at_hit] = (f, line, "%s; its size is checked on line %d" % (note, t.line))
        for i, t in enumerate(toks):
            if t.kind != "NAME":
                continue
            if not t.sigil and t.val.lower() in KEYWORDS and t.val not in prefixed:
                continue                     # a keyword, unless this code also uses it as a prefixed name
            if not t.sigil and t.val.startswith("__") and t.val.endswith("__"):
                continue                     # a name the language provides: __name__, __file__
            if shell and not t.sigil:
                glued = is_op(at(i + 1), "=") and at(i + 1).pos == t.pos + len(t.val)
                opens = i == 0 or i - 1 in ends or is_op(at(i - 1), "{", "}", ";") \
                    or is_word(at(i - 1), {"export", "local", "readonly", "declare", "typeset"}) \
                    or at(i - 1).line < t.line
                if glued and opens:                          # NAME=value sets $NAME
                    self.assigns["$" + t.val].append((name, t.line))
                    self.set_at["$" + t.val].append((name, t.line, t.pos))
                elif is_op(at(i - 1), "{") and is_op(at(i - 2), "$"):
                    self.reads["$" + t.val].append((name, t.line))       # ${NAME}
                elif is_word(at(i - 1), {"for", "read"}) or (is_word(at(i - 1), {"export", "local", "readonly"})
                                                           and not glued):
                    self.assigns["$" + t.val].append((name, t.line))     # for NAME in ..., read NAME
                continue                     # any other word is text or a command, not a variable
            if not t.sigil and is_op(at(i - 1), "-") and at(i - 2) is not None and at(i - 2).kind == "NAME" \
                    and at(i - 2).sigil == "$" and toks[i - 1].pos == at(i - 2).pos + 1 + len(at(i - 2).val) \
                    and t.pos == toks[i - 1].pos + 1:
                continue                     # the second half of a name written with a hyphen: $first-second
            if is_op(at(i - 1), ".", "->", "::"):
                if not is_op(at(i + 1), "("):
                    self.members["." + t.val].append((name, t.line))
                continue
            if not t.sigil and is_op(at(i + 1), "("):
                continue                     # a call or a declaration, not a variable
            if not t.sigil and is_op(at(i - 1), "(") and is_word(at(i - 2), LOG_CALLS) and t.val.isupper() \
                    and is_op(at(i + 1), ","):
                continue                     # the level of a log call: log(DEBUG, ...)
            if marked and not t.sigil and not is_op(at(i - 1), ".", "->", "::"):
                opens = i == 0 or i - 1 in ends or at(i - 1).line < t.line or is_op(at(i - 1), "{", "}", ";")
                closes = at(i + 1) is None or at(i + 1).line > t.line or is_op(at(i + 1), ";", "}")
                if closes and (opens or (is_op(at(i - 1), "=") and i not in in_cond)):
                    continue                 # a word of the language: a statement of its own, or a value it gives
            if is_word(at(i - 1), TYPE_WORDS):
                self.types.add(t.key)
                continue                     # a type name
            if not t.sigil and t.val.lower() in BUILT_IN_TYPES and not is_op(at(i + 1), *ASSIGN_OPS) \
                    and (is_op(at(i - 1), ":", "]", ">", ")") or (at(i - 1) is not None and at(i - 1).kind == "NAME"
                                                                   and at(i - 1).line == t.line and i not in in_cond)):
                continue                     # a built-in type, written where a type goes
            if is_word(at(i - 1), FUNC_WORDS):
                continue                     # the name of a function being defined, written without ( )
            if not t.sigil and is_op(at(i - 1), "{") and is_op(at(i + 1), "}") and at(i - 2) is not None \
                    and (is_op(at(i - 2), "->") or (at(i - 2).kind == "NAME" and at(i - 2).sigil)):
                continue                     # a key: $row->{price}, $row{price}
            if style == "hash" and not t.sigil:
                following = at(i + 1)
                at_start = i == 0 or i - 1 in ends or is_op(at(i - 1), "{", "}")
                ends_here = following is None or following.line > t.line or is_op(following, ";", "}")
                if at_start and t.val.lower() in ("next", "last", "redo", "pass") and ends_here:
                    continue                 # a statement of its own, not a name
                if at_start and following is not None and following.line == t.line \
                        and following.kind in ("STR", "NUM"):
                    continue                 # a command written without ( ): puts "text"
            if style in ("slash", "both") and not t.sigil and is_op(at(i + 1), "<") and at(i + 2) is not None \
                    and at(i + 2).kind == "NAME" and is_op(at(i + 3), ">", ",") and i not in in_cond:
                self.types.add(t.key)
                self.types.add(at(i + 2).key)
                continue                     # a type with a type inside it: List<Item>
            k = i + 1
            while is_op(at(k), ".", "->", "::") and at(k + 1) is not None and at(k + 1).kind == "NAME":
                k += 2
            if k > i + 1 and is_op(at(k), "("):
                self.bases[t.key].append((name, t.line))
                continue                     # the library or object a call is made on
            nxt = at(i + 1)
            if not t.sigil and nxt is not None and nxt.kind == "NAME" and not nxt.sigil \
                    and nxt.line == t.line and nxt.val.lower() not in KEYWORDS:
                continue                     # a word that introduces the next name: a type, `table x`
            where = (name, t.line)
            before = at(i - 1)
            if not t.sigil and is_op(at(i + 1), ":") and is_op(before, "{", ",", ";") and i not in in_cond \
                    and i not in params:
                continue                     # a key of an object, or a member of a type: `{ price: number }`
            if i not in params and is_op(before, ":") and at(i - 2) is not None and at(i - 2).kind == "NAME" \
                    and (i - 2 in params or is_word(at(i - 3), DECL_WORDS)):
                continue                     # the type in `name: Type`
            if style == "hash" and not t.sigil:
                joined_next = is_op(nxt, "-") and at(i + 2) is not None and at(i + 2).kind == "NAME" \
                    and nxt.pos == t.pos + len(t.val) and at(i + 2).pos == nxt.pos + 1
                joined_prev = is_op(before, "-") and at(i - 2) is not None and at(i - 2).kind == "NAME" \
                    and before.pos == at(i - 2).pos + len(at(i - 2).val) and t.pos == before.pos + 1
                if joined_next or joined_prev:
                    continue                 # a word written with a hyphen: Write-Host, apt-get
                if (is_op(before, "|") and is_op(nxt, "|", ",")) or (is_op(before, ",") and is_op(nxt, "|")):
                    self.assigns[t.key].append(where)
                    note_set(t, i)
                    continue                 # the parameter of a block: do |item|
            typed = (style in ("slash", "both") and before is not None and before.kind == "NAME"
                     and not before.sigil and not t.sigil
                     and (before.val.lower() in TYPE_NAMES or before.val.lower() not in KEYWORDS)
                     and before.line == t.line and not is_op(at(i - 2), ".", "->", "::"))
            declared = is_word(before, DECL_WORDS)
            if not t.sigil and is_word(before, BUILT_IN_TYPES) and before.line == t.line \
                    and (i == 1 or i - 2 in ends or at(i - 2).line < t.line or is_op(at(i - 2), "{", "}", ";")) \
                    and (nxt is None or nxt.line > t.line or is_op(nxt, ";")):
                self.assigns[t.key].append(where)
                note_set(t, i)
                continue                     # a declaration with no value: `array items;`
            if typed and not declared and not is_op(at(i + 1), *ASSIGN_OPS):
                self.assigns[t.key].append(where)
                note_set(t, i)
                continue
            if is_word(before, {"as"}):
                self.assigns[t.key].append(where)
                note_set(t, i)
                continue
            if style == "hash" and is_op(at(i + 1), "=") and is_op(before, "(", ","):
                continue                     # a named argument
            if (i in params or declared) and not is_op(at(i + 1), *ASSIGN_OPS):
                self.assigns[t.key].append(where)
                note_set(t, i)
                continue
            k = i + 1
            while is_op(at(k), "[", ".", "->"):
                k = close_of(toks, k, "[", "]") + 1 if is_op(at(k), "[") else k + 2
            op = at(k)
            if is_op(op, *ASSIGN_OPS) and i not in in_cond:
                self.assigns[t.key].append(where)
                last = k                      # the last token of this statement
                while last < n - 1 and last not in ends:
                    last += 1
                own = op.val != "=" or any(x.kind == "NAME" and x.key == t.key for x in toks[k + 1:last + 1])
                if k == i + 1:                    # x = ...: the blocks it is in, and whether a loop holds it
                    chain = tuple(a for a, b in sorted(pair.items()) if a < i < b)
                    looped = any(a < i < b for a, b, _ in loop_blocks)
                    self.sets[t.key].append((name, t.line, toks[last].line, own, chain, looped or i in in_function))
                if own and t.key not in first_set and t.key not in first_read and i not in in_function:
                    first_read[t.key] = (i - 1, t.line)      # it reads its own value before any line sets it
                if k == i + 1:
                    note_set(t, i)
                    self.set_at[t.key].append((name, t.line, t.pos))
                else:
                    self.filled.add(t.key)
                if k == i + 1 and op.val == "=":
                    indexed.pop(t.key, None)
                    # the whole right side is one call: remember it until its size is checked
                    c = k + 1
                    while at(c) is not None and at(c).kind == "NAME" and is_op(at(c + 1), ".", "->", "::"):
                        c += 2
                    if at(c) is not None and at(c).kind == "NAME" and is_op(at(c + 1), "(") \
                            and close_of(toks, c + 1) in (last, last - 1) \
                            and at(c).val.lower() not in SIZE_WORDS:
                        from_call[t.key] = t.line
                    else:
                        from_call.pop(t.key, None)
                if op.val != "=":
                    self.reads[t.key].append(where)
                    self.read_at[t.key].append((name, t.line, t.pos))
                elif k == i + 1 and (i - declared == 0 or (i - 1 - declared) in ends
                                     or is_op(at(i - 1 - declared), "{", "}")):
                    # 5. assigned twice in a row
                    end = k
                    while end < n - 1 and end not in ends:
                        end += 1
                    reads_itself = any(x.kind == "NAME" and x.key == t.key for x in toks[k + 1:end + 1])
                    if last_assign == (t.key, i - 1 - declared) and not reads_itself:
                        self.hits["twice"].append((name, t.line, t.key))
                    last_assign = (t.key, end)
            elif is_op(op, "++", "--") or is_op(at(i - 1), "++", "--"):
                self.assigns[t.key].append(where)
                self.reads[t.key].append(where)
                note_read(t, i)
                note_set(t, i)
            else:
                self.reads[t.key].append(where)
                self.read_at[t.key].append((name, t.line, t.pos))
                note_read(t, i)

        for key, (i, line) in first_read.items():
            if key in first_set and i < first_set[key][0] and key not in set_in_function:
                # in a loop, the read may be meant for the value of the pass before: that needs a reader.
                # Anywhere else the order of the lines is the order in which they run.
                loop = next((ln for a, b, ln in loop_blocks if a < i < b and a < first_set[key][0] < b), 0)
                sure = style in ("slash", "both") and bool(pair) and not loop
                self.early.append((name, key, line, first_set[key][1], loop, sure))
        self.set_in_function[name] = set_in_function
        structure_checks(self, name, toks, ends, in_cond, in_log, conds)

        # 6 and 7. text held in strings, logging left out
        stmt_tags = defaultdict(lambda: [0, 0, 0])
        stmt_opens = defaultdict(list)
        parts, segments, joined_len, gap = [], [], 0, False
        for i, t in enumerate(toks):
            if t.kind == "STR" and re.match(r"^[A-Za-z_]\w{3,}$", t.val):
                self.literals[t.val].append(text[t.pos - 1:t.pos])
            if t.kind == "STR" and i not in in_log:
                for m in ENTITY.finditer(t.val):
                    self.hits["entity"].append((name, t.line, "%s is not followed by ;" % m.group(0)))
                    typo = ":" if t.val[m.end():m.end() + 1] == ":" else ""      # &amp: for &amp;
                    self.fixes.append((name, t.pos + m.end(), typo, ";", "entity", t.line))
                if parts and gap:
                    joined_len += 1          # a value joined in between two strings
                    parts.append("\0")
                parts.append(t.val)
                segments.append((joined_len, t))
                joined_len += len(t.val)
                gap = False
                words = [] if PATTERN_TEXT.search(t.val) else [m.group(1) for m in PLACEHOLDER.finditer(t.val)]
                if words:
                    shown = re.sub(r"<[^<>]*>", " ", t.val)          # the text between the tags
                    rest = re.sub(r"[\s\d,;:/|+\-_.()\[\]\"'=]", "", PLACEHOLDER.sub("", shown))
                    whole = not rest and PLACEHOLDER.search(shown) is not None
                    self.hits["placeholder"].append((name, t.line, ", ".join(words) + (" — the whole text" if whole else "")))
            elif t.kind != "STR":
                gap = True
            if i in ends or i == n - 1:      # the statement is complete: find its tags and add them up
                for m in TAG.finditer("".join(parts)):
                    if m.group(3).rstrip().endswith("/"):
                        continue
                    start, tok = [seg for seg in segments if seg[0] <= m.start()][-1]
                    entry = stmt_tags[m.group(2)]
                    entry[1 if m.group(1) else 0] += 1
                    entry[2] = entry[2] or tok.line
                    if not m.group(1):       # remember each opening tag of the statement
                        whole = m.end() - start <= len(tok.val)
                        stmt_opens[m.group(2)].append((tok.pos + m.start() - start,
                                                       bool(m.group(3).strip()) or not whole, tok.line))
                parts, segments, joined_len, gap = [], [], 0, False
                for tag, (opens, closes, line) in stmt_tags.items():
                    total = self.tags[tag]
                    total[0] += opens
                    total[1] += closes
                    if opens != closes:
                        total[2].append((name, line))
                        # <x ...>text<x> : the second one was meant to close the first
                        seen_opens = stmt_opens[tag]
                        if opens == 2 and closes == 0 and not seen_opens[-1][1]:
                            self.tag_fixes[tag].append((name, seen_opens[-1][0] + 1, "", "/", "tag", seen_opens[-1][2]))
                stmt_tags = defaultdict(lambda: [0, 0, 0])
                stmt_opens = defaultdict(list)
        return True

    def read_includes(self):
        """The names defined in the files that the code includes, when those files came with the code.

        An included file is looked for by its name: next to the file that includes it, in the folders
        under that one, and in the workspace (the current folder) when the code is inside it.
        """
        cwd = Path.cwd().resolve()
        index = {}
        for f, line, target in self.includes:
            base = re.split(r"[\\/]", target)[-1]
            folder = Path(f).resolve().parent
            roots = [folder] + ([cwd] if cwd in folder.parents else [])
            found = None
            for root in roots:
                if root not in index:
                    index[root] = defaultdict(list)
                    for q in sorted(root.rglob("*"))[:5000]:
                        if not SKIP_DIRS & set(q.relative_to(root).parts) and q.is_file():
                            index[root][q.name].append(q)
                found = found or next(iter(index[root].get(base, [])), None)
            if found is None or not base:
                self.not_found.append((f, line, target))
                continue
            try:
                text = found.read_bytes().decode("utf-8", errors="replace")
            except OSError:
                self.not_found.append((f, line, target))
                continue
            for m in DEFINES.finditer(text):
                self.given.setdefault(m.group(1), (str(found), text.count("\n", 0, m.start()) + 1))

    def finish(self):
        for f, line, word, dollar, shell in self.in_strings:
            # a variable written inside a string is read there, if the code sets a variable of that name
            keys = ["$" + word, word] if dollar else [word, "$" + word, "@" + word]
            known = [k for k in keys if self.assigns.get(k)]
            if known:
                self.reads[known[0]].append((f, line))
            elif shell and dollar and word not in SHELL_GIVEN:
                self.reads["$" + word].append((f, line))     # in a shell script it is read even if never set
        for key, places in self.bases.items():
            if self.assigns.get(key):        # a variable, not a library: the call reads it
                self.reads[key] += places
        self.read_includes()
        for k in [k for k in self.reads if not self.assigns.get(k) and k in self.given]:
            del self.reads[k]                # defined in a file that the code includes
        names = {k for k in set(self.reads) | set(self.assigns) if self.reads.get(k) or self.assigns.get(k)}
        uses = {k: len(self.reads[k]) + len(self.assigns[k]) for k in names}
        # A prefix such as @ or $ of which three names in ten or more are never
        # assigned (inputs) or never read (outputs) marks data that lives outside the code;
        # those names are not reported as never assigned or never read.
        external = set()
        for sigil in {k[0] for k in names if k[0] in SIGILS} - self.set_in_code:
            group = [k for k in names if k[0] == sigil]
            if sum(1 for k in group if not self.assigns[k]) * 10 >= len(group) * 3 \
                    or sum(1 for k in group if not self.reads[k]) * 10 >= len(group) * 3:
                external.add(sigil)
        outside = lambda k: k[0] in external
        self.external = external             # prefixes of names that hold data from outside the code
        bare = lambda k: k[1:] if k[0] in SIGILS else k

        def hint(k):
            notes = []
            for sigil in SIGILS:
                twin = sigil + bare(k)
                if twin != k and twin in names:
                    notes.append("also written %s (%d times)" % (twin, uses[twin]))
            if k[0] in SIGILS and bare(k) in names:
                notes.append("also written %s (%d times)" % (bare(k), uses[bare(k)]))
            alike = sorted((o for o in names if o != k and uses[o] >= uses[k] and near(bare(k), bare(o))),
                           key=lambda o: (-uses[o], o))
            if alike:
                notes.append("close to %s (%d times)" % (alike[0], uses[alike[0]]))
            return "; ".join(notes)

        sort_of = lambda k: k[0] if k[0] in SIGILS else ""
        listed = lambda k: bare(k) in self.names
        cited = lambda n: "%s, line %d" % (Path(self.names[n][0]).name, self.names[n][1])
        biggest = max(self.name_lists, key=lambda b: b[3]) if self.name_lists else None
        the_list = "the list of names in %s (lines %d-%d)" % (Path(biggest[0]).name, biggest[1], biggest[2]) \
            if biggest else ""
        cover = {}                           # prefix -> the share of its names that a list of names holds
        for sigil in {k[0] for k in names if k[0] in SIGILS}:
            group = [k for k in names if k[0] == sigil]
            cover[sigil] = sum(1 for k in group if listed(k)) / len(group) if len(group) >= LIST_MIN else 0.0

        def in_series(k):
            """True for a numbered name whose series the code uses: Detail9 next to Detail2 and Detail4.

            A series needs a member that is used more than once; two names used once each that share a
            stem may both be misspellings.
            """
            m = re.match(r"^(.*\D)\d+$", bare(k))
            return bool(m) and any(o != k and sort_of(o) == sort_of(k) and uses[o] > 1
                                   and re.match(r"^%s\d+$" % re.escape(m.group(1)), bare(o)) for o in names)

        def closest(k):
            """Names of the same sort that are used more often and are one letter away."""
            return sorted((o for o in names if o != k and sort_of(o) == sort_of(k) and uses[o] > uses[k]
                           and near(bare(k), bare(o))), key=lambda o: (-uses[o], o))

        never_read = [k for k in names if not outside(k) and self.assigns.get(k) and not self.reads.get(k)]
        paired = set()                       # names never read that are the other half of a misspelling
        for k in sorted(names, key=str.lower):
            if outside(k):
                alike = closest(k)
                f, line = sorted(self.reads[k] + self.assigns[k])[0]
                candidate = uses[k] == 1 and alike and not in_series(k)
                if listed(k):
                    if candidate:                # it looks misspelt, and a document says that it exists
                        hit = (f, line, "%s — close to %s (%d times)" % (k, alike[0], uses[alike[0]]))
                        self.hits["once"].append(hit)
                        self.cleared[("once",) + hit] = "%s is in the list of names in %s." % (bare(k), cited(bare(k)))
                elif cover.get(k[0], 0.0) >= 0.8:
                    # the documents list the names of this sort, and this one is not among them
                    spelt = sorted(n for n in self.names if near(bare(k), n))
                    hit = (f, line, "%s — not in %s%s" % (k, the_list, "; close to %s%s (line %d of the list)" % (
                        k[0], spelt[0], self.names[spelt[0]][1]) if len(spelt) == 1 else ""))
                    self.hits["unlisted"].append(hit)
                    if len(spelt) == 1 and (uses[k] == 1 or cover[k[0]] >= 0.95):
                        self.fixes += [(g, pos, k, k[0] + spelt[0], "rename", n)
                                       for g, n, pos in self.read_at[k] + self.set_at[k]]
                        self.proven[("unlisted",) + hit] = "Proven from %s: it does not hold %s and it holds %s." % (
                            the_list, bare(k), spelt[0])
                elif candidate:
                    self.hits["once"].append((f, line, "%s — close to %s (%d times)" % (k, alike[0], uses[alike[0]])))
                continue
            if not self.assigns[k] and k in self.types:
                continue                     # the name of a type, not a variable
            if k.startswith("$") and k[1:] in SHELL_GIVEN and not self.assigns[k]:
                continue                     # given by the shell
            if not self.assigns[k]:
                where = sorted(set(self.reads[k]))
                note = "%s — read on line%s %s" % (k, "" if len(where) == 1 else "s",
                                                  ", ".join(str(line) for _, line in where))
                hit = (where[0][0], where[0][1], note + ("; " + hint(k) if hint(k) else ""))
                self.hits["unset"].append(hit)
                handlers = {self.handler_of.get(place) for place in where}
                if None not in handlers and len(handlers) >= 2:
                    self.cleared[("unset",) + hit] = (
                        "It is read only inside error handlers, in %d of them: a name the platform gives to a "
                        "handler, not one the code has to set." % len(handlers))
                # a correction with one possible form: the missing prefix, or the one name
                # given a value earlier in the same file that is the same word written
                # another way (letter case, or two letters swapped)
                twins = [sg + k for sg in SIGILS if sg + k in names] if k[0] not in SIGILS else []
                first = where[0]
                alike = [o for o in names if o != k and not outside(o) and same_word(k, o) and any(
                    f == first[0] and line < first[1] for f, line in self.assigns[o])]
                halves = [o for o in never_read if near(k, bare(o)) and any(
                    f == first[0] and line < first[1] for f, line in self.assigns[o])]
                if len(twins) == 1:
                    self.fixes += [(f, pos, "", twins[0][0], "prefix", line) for f, line, pos in self.read_at[k]]
                elif not twins and len(alike) == 1:
                    self.fixes += [(f, pos, k, alike[0], "rename", line) for f, line, pos in self.read_at[k]]
                    paired.add(alike[0])     # once corrected, that name is read here
                elif not twins and len(halves) == 1:
                    # this name is read and never set; a name one letter away is set and never read:
                    # the two are one name, and the one that is set is the spelling to keep
                    self.fixes += [(f, pos, k, halves[0], "rename", line) for f, line, pos in self.read_at[k]]
                    paired.add(halves[0])
                elif not twins and k[0] not in SIGILS and len(self.literals.get(k, [])) >= 2:
                    # the same word is written as text in other places: here the quotes are missing
                    quotes = [q for q in self.literals[k] if q in ("'", '"')] or ['"']
                    q = max(set(quotes), key=quotes.count)
                    self.fixes += [(f, pos, k, q + k + q, "quote", line) for f, line, pos in self.read_at[k]]
        inputs = {sigil for sigil in external if sum(1 for k in names if k[0] == sigil and not self.assigns[k]) * 10
                  >= sum(1 for k in names if k[0] == sigil) * 3}
        # Where the code also keeps its own working values under a prefix (five names or more that it sets
        # before it reads them), only a name that is read before it is set holds data that was given
        own = lambda k: not self.reads.get(k) or min(self.assigns[k]) < min(self.reads[k])
        mixed_use = {sg for sg in inputs if sum(1 for k in names if k[0] == sg and self.assigns[k] and self.reads[k]
                                                 and min(self.assigns[k]) < min(self.reads[k])) >= 5}
        written = sorted((k for k in names if k[0] in inputs and self.set_at.get(k)
                          and not (k[0] in mixed_use and own(k))), key=str.lower)
        for k in written:
            places = sorted({(f, line) for f, line, _ in self.set_at[k]})
            f, line = places[0]
            hit = (f, line, "%s — assigned on line%s %s" % (k, "" if len(places) == 1 else "s",
                                                           ", ".join(str(n) for _, n in places)))
            self.hits["writeback"].append(hit)
            self.for_owner[("writeback",) + hit] = (
                "The code changes %d value%s of the data it was given (%s). Which of them are meant to be stored for "
                "everything else that reads that data, and which are only meant for use here?"
                % (len(written), "" if len(written) == 1 else "s", ", ".join(written)))
        for k in sorted(names, key=str.lower):
            if not outside(k) and self.assigns[k] and not self.reads[k] and k not in paired:
                f, line = self.assigns[k][0]
                times = len(self.assigns[k])
                note = k if times == 1 else "%s (assigned %d times)" % (k, times)
                self.hits["unread"].append((f, line, note + (" — " + hint(k) if hint(k) else "")))
                twins = [sg + k for sg in SIGILS if sg + k in names] if k[0] not in SIGILS else []
                if len(twins) == 1:              # given a value without its prefix
                    self.fixes += [(g, pos, "", twins[0][0], "prefix_set", n) for g, n, pos in self.set_at[k]]
        for k in sorted(self.members, key=str.lower):
            if len(self.members[k]) != 1:
                continue
            alike = sorted((o for o in self.members if len(self.members[o]) > 1 and near(k[1:], o[1:])),
                           key=lambda o: -len(self.members[o]))
            if alike:
                f, line = self.members[k][0]
                hit = (f, line, "%s — close to %s (%d times)" % (k, alike[0], len(self.members[alike[0]])))
                self.hits["once"].append(hit)
                if k[1:] in self.names:
                    self.cleared[("once",) + hit] = "%s is in the list of names in %s." % (k[1:], cited(k[1:]))
        for tag, (opens, closes, where) in sorted(self.tags.items()):
            if opens != closes:
                for f, line in where:
                    self.hits["tag"].append((f, line, "<%s> opened %d, closed %d in the scanned code"
                                             % (tag, opens, closes)))
                self.fixes += self.tag_fixes[tag]

        for f, key, read_line, set_line, loop, sure in self.early:
            if outside(key) or any(g != f for g, _ in self.assigns[key]):
                continue                     # outside data, or set in another file of the same code
            hit = (f, read_line, "%s — read on line %d, first set on line %d%s" % (
                key, read_line, set_line, "; both are inside the loop that starts on line %d" % loop if loop else ""))
            self.hits["early"].append(hit)
            if sure:
                self.proven[("early",) + hit] = ("Proven from the code: nothing sets the name before this line, and "
                                                 "the line is not inside a loop. What an unset name yields needs a test.")
        for hit in self.hits["index"]:
            m = re.search(r"; its size is checked on line (\d+)", hit[2])
            if m:
                self.proven[("index",) + hit] = (
                    "Proven from the code: the size is checked on line %s, after this line, so the code itself "
                    "expects that the result can be empty. What the index does then needs a test." % m.group(1))
        for hit in self.hits["query"]:
            joined = hit[2][6:].split(", ") if hit[2].startswith("joins ") else []
            kinds = [self.names.get(bare(x)) for x in joined]
            if joined and all(x[0] in SIGILS and cover.get(x[0], 0.0) >= 0.8 for x in joined) \
                    and all(k and NUMBER_TYPE.match(k[2]) for k in kinds):
                self.cleared[("query",) + hit] = "The value joined in is %s, which cannot hold a quote: %s." % (
                    " and ".join(joined), "; ".join("%s is listed as %s in %s" % (bare(x), k[2], cited(bare(x)))
                                                    for x, k in zip(joined, kinds)))
        for f in sorted(self.handlers):
            only = [a for a, _, logs in self.handlers[f] if logs]
            more = [a for a, _, logs in self.handlers[f] if not logs]
            for hit in self.hits["handler"]:
                if hit[0] == f:
                    self.for_owner[("handler",) + hit] = "%s only log%s. Is logging enough for %s?" % (
                        "The error handlers on lines %s" % ", ".join(str(a) for a in only) if len(only) > 1
                        else "The error handler on line %d" % only[0],
                        ("" if len(only) > 1 else "s") + (", while the handler%s on line%s %s also change%s state" % (
                            "s" if len(more) > 1 else "", "s" if len(more) > 1 else "",
                            ", ".join(str(a) for a in more), "" if len(more) > 1 else "s") if more else ""),
                        "these failures" if len(only) > 1 else "this failure")
        for hit in self.hits["placeholder"]:
            if hit[2].endswith(" — the whole text"):
                self.for_owner[("placeholder",) + hit] = "The text is only the placeholder %s. What is the real value?" % (
                    hit[2].split(" — ")[0])
        # two spellings of one name that differ only by letter case, both in use. A spelling
        # all in capitals next to a mixed one is a common convention and is left out.
        spellings = defaultdict(list)
        for k in names:
            if not outside(k):
                spellings[k.lower()].append(k)
        for group in spellings.values():
            mixed = sorted((k for k in group if bare(k) != bare(k).upper()), key=lambda k: (uses[k], k))
            if len(mixed) > 1 and all(self.assigns.get(k) and self.reads.get(k) for k in mixed[:2]):
                f, line = (self.reads[mixed[0]] + self.assigns[mixed[0]])[0]
                self.hits["twins"].append((f, line, "%s — %d times; %s"
                                           % (mixed[0], uses[mixed[0]],
                                              ", ".join("%s %d times" % (k, uses[k]) for k in mixed[1:]))))
        for fn, places in sorted(self.declared.items()):
            if not self.mentioned[fn] and not fn.lower().startswith(("test", "_", "main", "init", "setup")):
                for f, line in places:
                    self.hits["nocall"].append((f, line, fn))
            for f, line in sorted(places)[1:]:
                self.hits["dupfunc"].append((f, line, "%s — also defined in %s on line %d"
                                             % (fn, Path(sorted(places)[0][0]).name, sorted(places)[0][1])))
        grouped = defaultdict(list)
        for f, line, note in self.hits["capped"]:
            grouped[(f, note)].append(line)
        self.hits["capped"] = [(f, min(lines), "%s — on line%s %s" % (note, "" if len(lines) == 1 else "s",
                                                                       ", ".join(str(n) for n in sorted(set(lines)))))
                               for (f, note), lines in grouped.items()]
        # a value replaced before anything reads it: the later assignment is in the same block as the earlier
        # one, or in a block around it, so it runs whenever the earlier one ran; loops are left out
        for k in sorted(self.sets, key=str.lower):
            if outside(k) or k in self.filled:
                continue
            events = sorted(self.sets[k])
            read_lines = defaultdict(set)
            for f, line in self.reads.get(k, []):
                read_lines[f].add(line)
            for n, (f, line, last, own, chain, looped) in enumerate(events):
                if own or looped or not n:
                    continue
                pf, pline, plast, pown, pchain, plooped = events[n - 1]
                if pf != f or plooped or pchain[:len(chain)] != chain or pline == line:
                    continue
                if any(plast < r <= line for r in read_lines[f]) or any(plast < r < line for r in ()):
                    continue                     # something reads it in between
                if (f, line, k) in self.hits["twice"]:
                    continue                     # two statements in a row: reported there
                j = n - 1                        # a value built up line by line: from its first line
                while j > 0 and events[j][3] and events[j - 1][0] == f:
                    j -= 1
                first = events[j][1]
                same = self.lines[f][pline - 1].strip() == self.lines[f][line - 1].strip() and plast == pline
                self.hits["discard"].append((f, line, "%s — set on line%s %s, %s" % (
                    k, "s" if first != pline else "", "%d-%d" % (first, pline) if first != pline else "%d" % pline,
                    "and set again here to the same value" if same else "replaced here before anything reads it")))
        # the same replacement made twice on one name, where the second pass changes what the first produced
        plain = lambda t: t.replace("\\", "")
        for k in sorted(self.replaces, key=str.lower):
            calls = sorted(self.replaces[k])
            for n, (f, line, pattern, repl, chain) in enumerate(calls):
                if not plain(pattern) or plain(pattern) not in plain(repl):
                    continue                     # replacing again changes nothing
                earlier = [c for c in calls[:n] if c[0] == f and plain(c[2]) == plain(pattern)
                           and plain(c[2]) in plain(c[3]) and c[4][:len(chain)] == chain]
                if earlier:
                    self.hits["reapplied"].append((f, line, "%s — \"%s\" is replaced by \"%s\" on line %d and again here" % (
                        k, plain(pattern), plain(earlier[-1][3]), earlier[-1][1])))
        for hit in self.hits["mixed"]:
            self.for_owner[("mixed",) + hit] = (
                "The condition mixes && and || with no brackets. Which parts belong together?")
        for hit in self.hits["capped"]:
            self.for_owner[("capped",) + hit] = (
                "These replace calls stop after a fixed number of replacements. Can the text they work on hold more "
                "occurrences than that? If it can, the rest is left as it was.")
        for key in list(self.hits):
            self.hits[key] = sorted(set(self.hits[key]))

    def line_count(self, name=None):
        """Number of lines of one file, or of all files, as an editor counts them."""
        names = [name] if name else list(self.text)
        return sum(t.count("\n") + (0 if not t or t.endswith("\n") else 1) for t in (self.text[n] for n in names))

    def corrected(self, name):
        """The text of one file with every one-form correction applied. Line numbers do not move."""
        text = self.text[name]
        for f, pos, old, new, _, _ in sorted((x for x in set(self.fixes) if x[0] == name),
                                             key=lambda x: -x[1]):
            if text[pos:pos + len(old)] == old:
                text = text[:pos] + new + text[pos + len(old):]
        return text


CHECKS = [
    ("cond", "Assignment in a condition",
     "A single = inside the condition of if / while. It assigns; a comparison needs the comparison operator."),
    ("unset", "Name read, never assigned",
     "Nothing in the scanned code sets this name. It may be a misspelling, a missing prefix, or set by the platform. "
     "One entry per name; the code shown is its first line."),
    ("unread", "Name assigned, never read",
     "The value is set and nothing in the scanned code uses it."),
    ("once", "Name used once, close to another name",
     "Used a single time and one letter or letter case away from a name of the same sort that is used more often."),
    ("unlisted", "Name not in the list of names",
     "A document next to the code lists the names of this sort, and this name is not among them."),
    ("twice", "Assigned twice in a row",
     "Two statements in a row assign the same name; the first value is lost."),
    ("entity", "Entity without its closing ;", "Text in a string, outside logging."),
    ("tag", "Tag opened and closed a different number of times",
     "Counted over the strings of the scanned code, outside logging."),
    ("placeholder", "Placeholder text in strings", "Text in a string, outside logging."),
    ("brackets", "Brackets that do not balance",
     "A bracket is opened and never closed, or closed without being open."),
    ("mixed", "&& and || mixed without brackets",
     "One group of a condition uses both and and or. Which parts belong together is decided by the "
     "language, not by how the line reads."),
    ("orphan", "else or else-if with no if before it",
     "The block before it is not the block of an if. The code is read differently from how it is laid out, "
     "or is rejected."),
    ("twins", "Names that differ only by letter case",
     "Two spellings of one name, both given a value and both read. If they are meant to be one name, "
     "each holds only part of the values."),
    ("repeat", "Same condition twice in one chain",
     "A condition that an earlier branch of the same if / else-if chain already tested. The branch cannot run."),
    ("self", "Compared or assigned to itself",
     "The same value on both sides of a comparison, two fixed values compared, or a name assigned to itself."),
    ("empty", "Block with nothing in it", "The case is tested or handled, and nothing is done."),
    ("early", "Name read before the line that first sets it",
     "By the order of the lines, the read comes first. Functions and names set in another file are left out."),
    ("index", "Result indexed before its size is checked",
     "A name holds the result of a call and is indexed before anything looks at its size or presence."),
    ("loop", "Loop whose condition nothing in the loop changes",
     "Nothing inside the loop assigns what the condition tests, and nothing leaves the loop."),
    ("handler", "Error handler that only logs", "The failure is logged and nothing else is done about it."),
    ("query", "Query built by joining text with a value",
     "A string that starts a query is joined with a variable. Text in a string, outside logging."),
    ("secret", "Environment name, address or credential in a string", "Text in a string, outside logging."),
    ("nocall", "Function defined and never called", "Nothing in the scanned code calls it or names it."),
    ("contra", "Comparisons that contradict each other",
     "One name is compared with two different values in a way that can never be true, or is always true."),
    ("semi", "Condition followed by ;",
     "The ; ends the statement, so the condition controls nothing and what follows always runs."),
    ("noeffect", "Comparison whose result is not used",
     "A statement that only compares two values. An assignment may have been meant."),
    ("dupbranch", "Branches with the same statements",
     "Two branches of one if / else-if chain do the same thing. One may have been meant to differ; "
     "if not, their conditions can be merged."),
    ("dupcase", "Same label twice in one switch", "The second branch with the label can never run."),
    ("dupfunc", "Function defined more than once",
     "The same name is defined again: one definition replaces the other, or is never used."),
    ("unreach", "Code after a statement that leaves the block",
     "The line follows return, break, continue, exit or throw in the same block, so it never runs."),
    ("strclose", "String not closed on its line", "A quote is opened and the line ends before it is closed."),
    ("bound", "Loop bound that includes the size",
     "An index is compared with <= to a size. If indexes start at 0, the last pass reads past the end."),
    ("command", "Command or code run with text joined to a value",
     "A call that runs a command or evaluates code is given text joined with a variable."),
    ("writeback", "Data from outside the code is changed",
     "A name of the sort that holds the data given to the code is assigned. The change is kept for everything "
     "that reads that data afterwards."),
    ("capped", "Replace limited to a count",
     "The replace call stops after a number of replacements. Text with more occurrences is only partly replaced."),
    ("discard", "Value replaced before it is read",
     "A name is given a value, and a later line that always runs after it gives it another value before anything reads the first."),
    ("reapplied", "Replacement made twice on the same value",
     "The replacement puts back the text it looks for, so a second pass changes what the first pass produced."),
]


PAGE_TYPES = {".html", ".htm", ".xhtml"}


def script_of(text):
    """The code of a web page: what stands inside its <script> elements and its event attributes (onclick="..."),
    each statement of an attribute ended with a ;. The markup around it is blanked, keeping every line where it
    was, so that a finding still names the line of the page."""
    keep, ends = [False] * len(text), set()
    spans_ = [(m.start(1), m.end(1)) for m in re.finditer(r"<script\b[^>]*>(.*?)</script\s*>", text, flags=re.S | re.I)]
    for m in re.finditer(r"""\son[a-z]+\s*=\s*(?:"([^"]*)"|'([^']*)')""", text, flags=re.I):
        g = 1 if m.group(1) is not None else 2
        if not any(a <= m.start() < z for a, z in spans_):
            spans_.append((m.start(g), m.end(g)))
            ends.add(m.end(g))
    for a, z in spans_:
        for i in range(a, z):
            keep[i] = True
    return "".join(c if keep[i] or c in "\r\n" else (";" if i in ends else " ") for i, c in enumerate(text))
    return "".join(c if keep[i] or c in "\r\n" else " " for i, c in enumerate(text))


def collect(targets):
    out = []
    for target in targets:
        p = Path(target)
        if p.is_file():
            out.append(p)
        elif p.is_dir():
            out.extend(sorted(f for f in p.rglob("*") if f.is_file() and not f.name.startswith(".")
                              and f.suffix.lower() not in SKIP_TYPES
                              and not SKIP_DIRS & set(f.relative_to(p).parts)))
        else:
            raise SystemExit("not found: %s" % target)
    return out


def unused_names(scan):
    """Names whose value is never used: nothing reads them, or they are only read into names that are not used.

    A name that the code fills part by part and never reads is not counted: something outside may read it.
    """
    if getattr(scan, "_unused", None) is not None:
        return scan._unused
    names = {k for k in set(scan.reads) | set(scan.assigns) if (scan.reads.get(k) or scan.assigns.get(k))
             and k[0] not in scan.external}      # data from outside the code is used outside it
    unused = {k for k in names if scan.assigns.get(k) and not scan.reads.get(k) and k not in scan.filled}
    changed = True
    while changed:
        changed = False
        for k in names - unused:
            if not scan.assigns.get(k) or k in scan.filled:
                continue
            reads = set(scan.reads.get(k, []))
            # every place the name is read is an assignment to itself or to a name that is not used
            into = lambda f, line: [x for x in scan.flows.get(f, []) if x[0] <= line <= x[1] and k in x[3]]
            if reads and all(into(f, line) and all(x[2] == k or x[2] in unused for x in into(f, line)) for f, line in reads):
                unused.add(k)
                changed = True
    scan._unused = unused
    return unused


def goes_to(scan, f, line):
    """Where the value set on a line goes: (the name set, [(name it is read into, line)], names beyond, how it ends).

    It follows the assignments of the same file that read the name. It ends with "used" (the value is read),
    "handed on" (it reaches something the code fills and never reads, which something outside may read) or
    "nowhere" (nothing in this code uses it). None when the line sets nothing.
    """
    flows = scan.flows.get(f, [])
    here = next((x for x in flows if x[0] <= line <= x[1]), None)
    if here is None:
        return None
    name = here[2]
    readers = sorted({(x[2], x[0]) for x in flows if name in x[3] and x[2] != name},
                     key=lambda r: (r[1] < line, abs(r[1] - line)))
    direct, seen = [], {name}
    for target, at in readers:
        if target not in seen:
            direct.append((target, at))
            seen.add(target)
    beyond, frontier = [], [t for t, _ in direct]
    for _ in range(3):
        nxt = []
        for current in frontier:
            for x in flows:
                if current in x[3] and x[2] not in seen:
                    seen.add(x[2])
                    beyond.append(x[2])
                    nxt.append(x[2])
        frontier = nxt
    reached = seen
    if name in unused_names(scan):
        end = "nowhere"
    elif any(k in scan.filled and not scan.reads.get(k) for k in reached):
        end = "handed on"
    else:
        end = "used"
    return name, direct, beyond, end


def holds(text, style="slash"):
    """What a piece of code holds: (the text of its strings, logging left out; the names of the functions it calls)."""
    toks = lex(text, style)
    in_log = set()
    for i, t in enumerate(toks):
        if is_word(t, LOG_CALLS) and i + 1 < len(toks) and is_op(toks[i + 1], "("):
            in_log.update(range(i + 2, close_of(toks, i + 1)))
    strings = [t.val for i, t in enumerate(toks) if t.kind == "STR" and len(t.val.strip()) >= 2 and i not in in_log]
    calls = [t.val for i, t in enumerate(toks) if t.kind == "NAME" and not t.sigil and i + 1 < len(toks)
             and is_op(toks[i + 1], "(") and t.val.lower() not in CONTROL_WORDS]
    return strings, calls


def account_of(text, style="slash"):
    """A sentence that names what removed code held, so that the removal accounts for all of it."""
    strings, calls = holds(text, style)
    parts = []
    if strings:
        parts.append("the text %s" % ", ".join('"%s"' % s.replace("\n", "\\n") for s in dict.fromkeys(strings)))
    if calls:
        counted = {}
        for c in calls:
            counted[c] = counted.get(c, 0) + 1
        parts.append("the calls %s" % ", ".join("`%s` (%d)" % (c, n) for c, n in counted.items()))
    return "Removed with these lines: %s." % "; ".join(parts) if parts else ""


def text_changed(before, after, style="slash"):
    """A sentence that names the text in strings that one corrected line changed, with the counts."""
    old, new = holds(before, style)[0], holds(after, style)[0]
    changed = [(s, old.count(s), new.count(s)) for s in dict.fromkeys(old + new) if old.count(s) != new.count(s)]
    if not changed:
        return ""
    return "Text in strings on this line: %s." % ", ".join(
        '"%s" %d -> %d' % (s.replace("\n", "\\n"), a, b) for s, a, b in changed)


def run(targets, hash_comments=False, documents=None):
    """Scan code the way every script here does: (the scan, the files it read).

    The documents next to the code are read for lists of names. Pass `documents`
    to use the same ones for two versions of the code that are compared.
    """
    files = collect(targets)
    scan = Scan()
    left_out = []
    scan.add_documents(documents_for(targets, left_out) if documents is None else documents)
    if left_out:
        scan.notes.append("document not used, because it sits with other code in the workspace: %s"
                          % ", ".join(os.path.relpath(str(f)) for f in left_out))
    scan.learn(files, hash_comments)
    for f in files:
        scan.add_file(f, hash_comments)
    scan.finish()
    return scan, [f for f in files if str(f) in scan.lines]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("targets", nargs="+", help="files or folders of code")
    ap.add_argument("--hash-comments", action="store_true", help="# starts a comment")
    ap.add_argument("--table", action="store_true",
                    help="print the hits as rows of a Markdown table, to start a findings table from")
    args = ap.parse_args()
    scan, files = run(args.targets, args.hash_comments)

    if args.table:
        print("| Line | Code (quoted) | Kind | Scan note |\n|---|---|---|---|")
        for key, title, _ in CHECKS:
            for f, line, note in sorted(set(scan.hits[key])):
                code = scan.lines[f][line - 1].strip() if 0 < line <= len(scan.lines[f]) else ""
                where = "%d" % line if len(files) == 1 else "%s:%d" % (Path(f).name, line)
                print("| %s | `%s` | %s | %s |" % (where, code.replace("|", "\\|").replace("`", "'"),
                                                 title, note.replace("|", "\\|")))
        return

    print("Scan: %d file(s), %d lines. Every line below is a candidate to judge, not a finding.\n"
          % (len(files), scan.line_count()))
    for name, reason in scan.skipped:
        print("  left out: %s (%s)" % (name, reason))
    for note in scan.notes:
        print("  note: %s" % note)
    for key, title, _ in CHECKS:
        print("  %4d  %s" % (len(scan.hits[key]), title))
    for key, title, about in CHECKS:
        rows = sorted(set(scan.hits[key]))
        if not rows:
            continue
        print("\n%s (%d)\n  %s" % (title, len(scan.hits[key]), about))
        for f, line, note in rows:
            code = scan.lines[f][line - 1].strip() if 0 < line <= len(scan.lines[f]) else ""
            code = code if len(code) <= 150 else code[:147] + "..."
            where = "line %d" % line if len(files) == 1 else "%s:%d" % (Path(f).name, line)
            print("  %s  %s" % (where, note) if note else "  %s" % where)
            print("      %s" % code)


if __name__ == "__main__":
    main()
