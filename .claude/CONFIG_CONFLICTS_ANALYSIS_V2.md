# 配置冲突与不一致性分析报告（更新版）

**生成时间**: 2026-08-24（Hook 系统验证后）  
**分析范围**: 全局配置 + 项目配置 + 22 个 skills

---

## 执行摘要

经过完整验证，**hooks 系统正常工作**（exit 2 可阻断工具调用）。发现 **3 个实际冲突** + **2 个潜在风险**。

---

## 🔴 关键冲突（需修复）

### 1. activate-conda-env skill 教生成过时配置 ❌

**位置**: `C:\Users\shy\.claude\skills\activate-conda-env\SKILL.md`

**问题**:
- **第 130 行**: 教生成 `.claude/hooks.json`（项目级）
- **第 155/275 行**: 明确写着"hook 注册配置"是 `.claude/hooks.json`

**实际情况**（已验证）:
- 项目级 `.claude/hooks.json` **完全不被 CLI 读取**（二进制扫描 + 实测证实）
- Hook 配置必须写入 `~/.claude/settings.json`（全局）才生效

**影响**:
- 按 skill 指示生成的配置**完全失效**
- 误导用户以为 hook 已生效

**修复方案**: 更新 SKILL.md 第 3.2 节：

```markdown
### 3.2 注册 hooks（写入全局 settings.json）

读取 `~/.claude/settings.json`，在 `hooks.PreToolUse` 数组中合并添加（不覆盖已有 hooks）：

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash|PowerShell",
        "hooks": [
          {
            "type": "command",
            "command": "powershell -ExecutionPolicy Bypass -File \"<PROJECT_ROOT>\\.claude\\hooks\\enforce-conda-env.ps1\""
          }
        ]
      }
    ]
  }
}
```

**注意**: 必须使用**绝对路径**。`<PROJECT_ROOT>` 需替换为项目实际路径（如 `F:\CASIA\...`）。

相对路径（`.claude/hooks/...`）在全局配置里无法正确解析，会导致 hook 静默失败。
```

---

### 2. activate-conda-env 的 exit code 错误 ❌

**位置**: SKILL.md 第 123 行生成的脚本

**问题**:
```powershell
exit 1  # ← 错误：exit 1 不会阻断工具调用
```

**CLI 的 exit code 行为**（已实测验证）:
| Exit Code | 行为 |
|---|---|
| 0 | 放行，不显示输出 |
| **2** | **阻断工具调用**，显示 stderr 给 AI |
| 其他（1, 3-255） | 显示 stderr 给用户，但**继续执行** |

**影响**:
- Hook 触发了、提示也显示了，但命令仍然执行
- AI 看到提示后自动修正，用户误以为 hook 生效（实际是 AI 自觉修正）

**修复方案**: SKILL.md 第 123 行改为：
```powershell
exit 2  # 阻断工具调用
```

---

### 3. pdf-enhance hook 与 conda hook 可能冲突 ⚠️

**位置**: 
- pdf-enhance: `C:\Users\shy\.claude\skills\pdf-enhance\hooks\intercept-pdf-read.ps1`
- conda: `settings.json` 的 PreToolUse hook

**冲突场景**:
- **pdf-enhance hook** 也返回 `exit 1`（第 72 行），同样不会真正阻断
- 如果用户按 pdf-enhance SKILL.md 第 101-118 行的指示，手动在 settings.json 添加 Read matcher：

```json
{
  "matcher": "Read",
  "hooks": [...]
}
```

就会与当前已有的 `"matcher": "Bash|PowerShell"` 共存，形成：

```json
"PreToolUse": [
  {"matcher": "Bash|PowerShell", "hooks": [...]},  // conda hook
  {"matcher": "Read", "hooks": [...]}                // pdf hook
]
```

**潜在问题**:
- settings.json 里有多个 PreToolUse matcher
- 如果两个 hook 都用**绝对路径指向不同项目**，在其他项目打开会话时路径失效

**当前状态**:
- ✅ pdf-enhance hook **未配置**（settings.json 只有 conda hook）
- ✅ 暂无实际冲突

**预防措施**:
1. pdf-enhance hook 的 exit 1 也应改成 exit 2
2. 如果要配置 pdf-enhance hook，需要改用相对路径或环境变量（如 `${CLAUDE_USER_ROOT}/.claude/skills/pdf-enhance/hooks/...`）

---

## 🟡 潜在风险（未触发，需注意）

### 4. 全局 settings.json 使用硬编码绝对路径 ⚠️

**当前配置**:
```json
"command": "powershell -ExecutionPolicy Bypass -File \"F:\\CASIA\\Drone Swarm Situational Awareness Algorithm\\Collective Intelligence Brain\\.claude\\hooks\\enforce-conda-env.ps1\""
```

**问题**:
- 路径硬编码为 `F:\CASIA\...\Collective Intelligence Brain\...`
- **在其他项目**打开会话时，这个路径无效 → hook 静默失败（但不报错）
- **换其他机器**时，路径不存在 → hook 静默失败

**影响范围**:
- 全局配置影响所有项目
- 其他项目的裸 python 不会被拦截（除非它们也有自己的 .conda-env + 脚本）

**改进方案**（CLI 可能不支持，需测试）:
1. 使用环境变量（如果 CLI 支持）:
   ```json
   "command": "powershell -ExecutionPolicy Bypass -File \"${CLAUDE_CWD}\\.claude\\hooks\\enforce-conda-env.ps1\""
   ```
2. 或改为项目级插件（创建 `.claude-plugin/plugin.json` + `hooks/hooks.json`）

**当前缓解措施**:
- CLAUDE.md 作为兜底（AI 自觉遵守）
- 只在 "Collective Intelligence Brain" 项目里需要 conda hook
- 其他项目如果裸 python 被放行也无妨

---

### 5. activate-conda-env 与 pdf-enhance 都写 settings.json，可能覆盖 ⚠️

**问题**:
- 两个 skill 都教在 `settings.json` 添加 PreToolUse hooks
- 如果实现用**整体替换而非数组追加**，后执行的会丢失先前的 hooks

**当前状态**:
- activate-conda-env 已按正确方式配置（本次会话手动合并）
- pdf-enhance 未配置

**预防措施**:
- 两个 skill 都需在文档里明确：**必须合并追加到 PreToolUse 数组，不要覆盖整个 hooks 对象**
- 提供合并示例代码（PowerShell / Python）

---

## 🟢 已确认无冲突

### 6. 全局 CLAUDE.md vs 项目 CLAUDE.md ✅

| 文件 | 内容 | 作用域 |
|---|---|---|
| `C:\Users\shy\.claude\CLAUDE.md` | graphify + 质量复盘规则 | 所有项目 |
| `f:\...\Collective Intelligence Brain\CLAUDE.md` | Conda 映射表 | 本项目 |

**结论**: 两者主题不重叠，规则叠加生效 ✅

---

### 7. settings.json 结构完整性 ✅

**当前全局配置**:
```json
{
  "effortLevel": "xhigh",
  "model": "fable",
  "env": {
    "ANTHROPIC_AUTH_TOKEN": "...",
    "ANTHROPIC_BASE_URL": "https://uuapi.shop",
    ...
  },
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash|PowerShell",
        "hooks": [{"type": "command", "command": "..."}]
      }
    ]
  }
}
```

**验证**: JSON 合法，各字段互不冲突 ✅

---

### 8. 项目 .claude 目录清理 ✅

**当前文件**:
- `CONFIG_CONFLICTS_ANALYSIS.md` - 本报告的旧版（可删除或保留作记录）
- `hooks.json` - ❌ **应删除**（CLI 不读取，容易误导）
- `settings.local.json` - 只保留 permissions，hooks 已删除 ✅
- `hooks/enforce-conda-env.ps1` - ✅ 保留（被全局 settings.json 引用）

**建议清理**:
```powershell
Remove-Item ".claude\hooks.json" -Force
```

---

## 📋 修复优先级与行动清单

| 优先级 | 问题 | 修复方案 | 责任方 |
|---|---|---|---|
| **P0** | activate-conda-env 教生成失效配置 | 更新 SKILL.md 第 3.2 节：`.claude/hooks.json` → `settings.json` + 绝对路径 | 用户（skill 维护者） |
| **P0** | activate-conda-env exit code 错误 | SKILL.md 第 123 行：`exit 1` → `exit 2` | 用户（skill 维护者） |
| **P1** | 项目内废弃的 `.claude/hooks.json` | 删除文件，避免混淆 | 用户 |
| **P2** | pdf-enhance exit code 错误 | intercept-pdf-read.ps1 第 72 行：`exit 1` → `exit 2` | 用户（skill 维护者） |
| **P2** | pdf-enhance hook 配置指南 | SKILL.md 第 101-118 行：改为合并追加示例 | 用户（skill 维护者） |
| **P3** | 全局 hook 绝对路径问题 | 文档化限制，或研究环境变量方案 | 观察中 |

---

## 🧪 验证检查表（已通过）

✅ **Hook 系统可用性**
- `/hooks` 显示注册的 hooks ✓
- 裸 `python --version` 被阻断（exit 2 生效）✓
- `conda run` 放行 ✓
- 非 Python 命令（git status）放行 ✓

✅ **目录感知**
- 根目录 → llm ✓
- latest 路径提示 → study_flask ✓

✅ **配置文件完整性**
- settings.json JSON 合法 ✓
- 4 个 .conda-env 存在 ✓
- CLAUDE.md 映射表正确 ✓

---

## 附录：完整文件清单

### 全局配置（影响所有项目）
- `C:\Users\shy\.claude\settings.json` - Hook 注册（1 个 conda hook）✅
- `C:\Users\shy\.claude\CLAUDE.md` - 全局规则（graphify + 质量复盘）✅
- `C:\Users\shy\.claude\skills\activate-conda-env\SKILL.md` - ⚠️ 需更新
- `C:\Users\shy\.claude\skills\pdf-enhance\SKILL.md` - ⚠️ 需更新
- `C:\Users\shy\.claude\skills\pdf-enhance\hooks\intercept-pdf-read.ps1` - ⚠️ exit 1 → exit 2

### 项目配置（本项目专用）
- `f:\...\Collective Intelligence Brain\CLAUDE.md` - Conda 映射表 ✅
- `.claude\hooks\enforce-conda-env.ps1` - Hook 脚本（exit 2 版本）✅
- `.claude\settings.local.json` - 只保留 permissions ✅
- `.claude\hooks.json` - ❌ **待删除**（失效文件）
- `.conda-env` 等 4 个文件 - 环境声明 ✅

### 插件配置（只读，不修改）
- 22+ 个官方插件的 hooks.json（ARS / security-guidance / 等）
- 全部正常工作，无冲突 ✅

---

## 关键经验教训

### ✅ 已验证的事实
1. **Hooks 系统正常工作**（CLI 2.1.241）
2. **只有 exit 2 才能阻断工具调用**（exit 0 放行，exit 1/其他 显示但不阻断）
3. **项目级 `.claude/hooks.json` 不被读取**（只有插件的 `hooks/hooks.json` 和全局 `settings.json` 生效）
4. **绝对路径在全局配置里有效**（但只对那一个项目有效）

### ❌ 常见误区
1. ~~"exit 1 会阻断命令"~~ → **错误**，只有 exit 2 阻断
2. ~~"项目级 `.claude/hooks.json` 会被加载"~~ → **错误**，CLI 不读取
3. ~~"settings.json 的 hooks 不生效"~~ → **错误**，生效但需要正确的 exit code
4. ~~"相对路径在全局配置里可用"~~ → **部分错误**，当前工作目录匹配时可用，但跨项目失效

---

**报告结束** — 生成时间: 2026-08-24 08:15
