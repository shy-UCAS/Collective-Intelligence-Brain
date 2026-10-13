# 无人机集群目标设施趋向与抵达时间推断：实现设计包 v1.0

这是供本地 Codex 接手的实现规范，不是已完成的预测服务。输入按用户现有轨迹 JSON、Airspace JSON 和上游分组适配；样例数值不用于业务分析。核心来自薛锡瑞等的桥接分布论文，工程扩展与独立推导分别标识。

## 使用顺序

先读 `docs/DESIGN.md`（主规范），再把本包交给 Codex，让其按 `CODEX_TASKS.md` 从M0执行。公式实现前必须读 `docs/MATH_AUDIT.md`。不要直接启用示例配置上线。

## 文件

| 路径 | 内容 |
|---|---|
| `docs/DESIGN.md` | 正式算法实现设计规范，含来源、接口、数学、执行模式、输出语义、验收 |
| `docs/算法实现设计规范_v1.0.pdf` | 主规范阅读版 |
| `docs/MATH_AUDIT.md` | 速度变量、矩阵积分、非线性近似、桥接、可达域、事件语义核对 |
| `CODEX_TASKS.md` | 分阶段执行要求及交接报告格式 |
| `config/config.example.yaml` | 开发配置模板；生产必需但尚未确认的项为null |
| `schemas/*.schema.json` | 轨迹、设施、内部集群、结果四份结构契约 |
| `examples/*.json` | 完全合成的接口样例；输出样例全部为结构演示，不是计算结果 |
| `checks/check_math.py` | 9项独立数学核验 |
| `checks/check_contracts.py` | 12项Schema与部分语义核验 |
| `checks/*_report.json` | 本次实际执行报告，仅限上述检查范围 |
| `CHECK_REPORT.md` | 检查结论与尚未实现范围 |

## 复查本包

在已有 Python 环境安装本地检查所需依赖，然后从包根目录执行：

```bash
python -m pip install -r requirements-checks.txt
python checks/check_math.py --report checks/math_report.json
python checks/check_contracts.py --report checks/contracts_report.json
```

依赖文件仅用于核验脚本，不是生产预测器的依赖锁文件。报告记录本次环境版本。未把用户原始数据、私人设施坐标或任何字体文件放入本包。

## 本版关键约束

外部数据格式不变；N=1与多机统一；仅位置作为评价量测；快照内重建以防重复证据；自由运动替代模型必须有真实似然；条件终端ETA与区域首次进入ETA分开；新概率不覆盖旧规则confidence和ETA；原论文歧义不能静默填补。

当前可以开始M0—M2。坐标参考、实际终端条件、误报预算、并发规模等部署配置仍需在实际工程中确认。配套检查通过不代表完整桥接预测、实时性能或真实轨迹有效性已验证。
