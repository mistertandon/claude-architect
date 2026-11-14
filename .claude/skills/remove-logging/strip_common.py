"""
strip_common.py - remove the logging patterns that repeat in every POC (built by /requirement-to-poc).

Usage:  python -I strip_common.py <file.py> ...

Handles only the mechanical patterns:
  * common.py: setup_logging(), log_model_io(), the `log` logger, and the imports only they used
  * setup_logging("...") + the "Setup failed" print in main()
  * `except X as exc:` whose body starts with a one-line log.error/log.warning
  * `log.info("MODEL INPUT ...")` and `log_model_io(...)` lines
  * `log`, `log_model_io`, `setup_logging` in `from common import ...`
  * an `except` left with no body gets `pass`

Everything else (summary lines, multi-line log calls, prints in offline demos) is left for the skill's manual pass.
Prints each file it changed. Never touches a file it can't parse afterwards: such files are reported, not written.
"""

import ast
import re
import sys


def strip_common_py(s: str) -> str:
    if "def setup_logging" not in s:
        return s
    s = s[:s.index("def setup_logging")].rstrip() + "\n"  # the logging helpers are the last functions
    s = s.replace("read .env, set up logging, and log the model's input and output.", "read .env.")
    s = s.replace('log = logging.getLogger("poc")\n', "")
    s = re.sub(r"from claude_agent_sdk import \(\n(?:    \w+,\n)+\)\n", "", s)
    for line in ("import logging\n", "import sys\n", "from datetime import datetime\n", "from typing import Any\n"):
        rest = s.replace(line, "")
        if not re.search(rf"\b{line.split()[-1]}\b", rest):  # drop the import only if nothing else uses it
            s = rest
    return s


def strip_script(s: str) -> str:
    s = re.sub(r'\n( +)setup_logging\("[^"]+"\)\n((?: +[^\n]*\n)*?)( +)except \(([^)]*)\) as exc:\n +print\(f"Setup failed: \{exc\}"\)\n',
               r'\n\2\3except (\4):\n', s)
    s = re.sub(r"except ([^\n:]+?) as exc:([^\n]*)\n( +)log\.(?:error|warning)\([^\n]*\)\n", r"except \1:\2\n", s)
    s = re.sub(r'\n +log\.info\("MODEL INPUT[^\n]*\)(?=\n)', "", s)
    s = re.sub(r"\n +log_model_io\([^\n]*\)(?=\n)", "", s)

    def fix_import(m: re.Match) -> str:
        names = [n.strip() for n in m.group(1).split(",")]
        names = [n for n in names if n not in ("log", "log_model_io", "setup_logging")]
        return f"from common import {', '.join(names)}\n" if names else ""

    s = re.sub(r"from common import ([^\n(]+)\n", fix_import, s)
    # an except whose only statement was the log call: give it `pass`
    return re.sub(r"(\n( +)except [^\n]*?:( +#[^\n]*)?\n)(?=\2\S|\n)", lambda m: m.group(1) + m.group(2) + "    pass\n", s)


for path in sys.argv[1:]:
    with open(path, encoding="utf-8") as f:
        original = f.read()
    new = strip_common_py(original) if path.endswith("common.py") else strip_script(original)
    if new == original:
        continue
    try:
        ast.parse(new)
    except SyntaxError as exc:
        print(f"SKIPPED {path}: the result would not parse ({exc.msg}, line {exc.lineno}); edit it by hand")
        continue
    with open(path, "w", encoding="utf-8") as f:
        f.write(new)
    print(f"changed {path}")
