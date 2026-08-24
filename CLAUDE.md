## Conda Python Environment

本仓库含多个子工程，依赖互斥（spade-bdi 锁定 `jinja2==3.0.3`，与 Flask 3.1.x 要求的 `jinja2>=3.1.2` 冲突），
因此**按目录映射 conda 环境**。每个目录下的 `.conda-env` 文件保存该目录应使用的环境名：

| 目录 | 环境 |
|------|------|
| 主仓库根目录（默认；pure_py、apitest 等数据脚本） | `llm` |
| `situationawareness latest/`（Flask 服务） | `study_flask` |
| `SituationAwareness Origin/`（Flask 服务） | `study_flask` |
| `uav_strategy/`（spade-bdi 智能体） | `llm` |

**ALL Python/pip commands MUST run inside the mapped conda environment:**

- Install packages:   `conda run -n <env> --no-capture-output pip install <pkg>`
- Run Python scripts: `conda run -n <env> --no-capture-output python script.py`
- 命令目标在哪个子模块，就使用该子模块对应的环境；安装子模块依赖时请让命令包含子模块路径（或先 `cd` 到该目录）。
- 跨环境流水线必须逐阶段显式选择环境：非 Flask 阶段使用 `llm`，Flask 服务/路由阶段使用 `study_flask`。
- 修复环境依赖时，不要向 `llm` 安装 Flask，也不要向 `study_flask` 安装 SPADE/spade-bdi。

**`conda run` does NOT support multi-line `-c` inline scripts.**
When you need to run Python code, first write it to a `.py` file, then execute the file.

A PreToolUse hook at `.claude/hooks/enforce-conda-env.ps1` blocks bare `python`/`pip` calls
and resolves the correct env from the command path / working directory (per-directory `.conda-env` files).
If you see a "BLOCKED" error, correct your command to the `conda run` form above.
