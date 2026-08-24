# Project Instructions

## Conda Environments

This repository contains Python subprojects with incompatible dependency sets.
Use the nearest `.conda-env` file as the source of truth:

| Scope | Conda environment |
| --- | --- |
| Repository root and uncategorized Python tools | `llm` |
| `situationawareness latest/` | `study_flask` |
| `SituationAwareness Origin/` | `study_flask` |
| `uav_strategy/` | `llm` |
| `uav_strategy_pure_py/` | `llm` |

- Run Python as `conda run -n <env> --no-capture-output python ...`.
- Run pip as `conda run -n <env> --no-capture-output python -m pip ...`.
- Do not use bare `python` or `pip` commands.
- When one workflow spans subprojects with different environments, split it into
  separate commands or let the workflow launcher select an environment per stage.
- Do not install Flask into `llm` or SPADE/spade-bdi into `study_flask` when
  repairing the environments; their Jinja2 requirements conflict.

## Content And Encoding

- Render mathematical formulas and symbols with LaTeX. Use `\(...\)` for inline
  formulas mixed with prose.
- If a document is garbled, try multiple plausible encodings before concluding
  that the file is unreadable.
