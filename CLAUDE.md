## Conda Python Environment

**ALL Python/pip commands MUST run inside the conda environment `study`:**

- Install packages:   `conda run -n study --no-capture-output pip install <pkg>`
- Run Python scripts: `conda run -n study --no-capture-output python script.py`

**`conda run` does NOT support multi-line `-c` inline scripts.**
When you need to run Python code, first write it to a `.py` file, then execute the file.

A PreToolUse hook at `.claude/hooks/enforce-conda-env.ps1` blocks bare `python`/`pip` calls.
If you see a "BLOCKED" error, correct your command to the `conda run` form above.
