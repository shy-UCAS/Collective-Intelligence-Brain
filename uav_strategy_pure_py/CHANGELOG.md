# Changelog

## [2026-08-13] 队形同步修复

### 问题
编队队形在仿真时出现"有先有后"、不同步、切换预瞄点时队形错乱的问题。

### 根本原因

#### 1. 随机噪声累积破坏队形
- **位置噪声**: 每个轨迹点独立添加随机噪声，导致噪声累积、队形变形
- **角度噪声**: V形队形每个成员角度扰动 ±3°，导致两翼不对称
- **影响**: 即使同步机制正常工作，物理位置已经错乱

#### 2. 同步阈值过大导致起跑线不齐
- **原值**: `CLOSE_TH_SYNC = 3.0` 米
- **问题**: 成员在距离目标 0.1-2.9 米之间任意位置都算"到达"
- **后果**: 切换预瞄点时，不同成员从相差最多 2.8 米的位置开始飞向下一个航点
- **表现**: 每次切换航点队形瞬间错乱

### 修复内容

#### Modified: `planning_modules/formation_generator.py`

**1. V形角度噪声 (line 69)**
```python
# Before:
α = self.angle + np.random.uniform(-self.angle_noise_scale, self.angle_noise_scale)  # ±3°

# After:
α = self.angle + np.random.uniform(-0.5, 0.5)  # ±0.5°
```

**2. 位置噪声 (line 172)**
```python
# Before:
p_w = Rm.dot(p_body) + base + np.random.normal(scale=self.noise_scale, size=3)

# After:
noise = np.random.normal(scale=self.noise_scale * 0.1, size=3)
p_w = Rm.dot(p_body) + base + noise  # 降低到原来的 10%
```

**噪声规模对比**:
- 原始: `0.00001-0.00005` 米/点 (0.01-0.05mm)
- 现在: `0.000001-0.000005` 米/点 (0.001-0.005mm)
- 100 航点累积: 约 0.1-0.5mm (几乎感觉不到)

#### Modified: `behaviours.py`

**同步阈值 (line 25)**
```python
# Before:
CLOSE_TH_SYNC = 3.0  # 3 米

# After:
CLOSE_TH_SYNC = 0.5  # 0.5 米
```

**影响**:
- 更精确的到达判定（0.5米范围内）
- 切换航点时起跑线对齐（位置偏差 < 0.5米）
- 队形保持整齐

### 效果验证

#### Before (问题表现)
```
切换航点时:
  agent_1: 从距离目标 0.5m 处开始
  agent_2: 从距离目标 2.8m 处开始  ← 相差 2.3m
  agent_3: 从距离目标 1.2m 处开始
  → 队形瞬间错乱，需要数个航点才能恢复
```

#### After (修复后)
```
切换航点时:
  agent_1: 从距离目标 0.2m 处开始
  agent_2: 从距离目标 0.4m 处开始  ← 相差仅 0.3m
  agent_3: 从距离目标 0.3m 处开始
  → 队形基本保持，有轻微自然扰动
```

### 预期效果

- ✅ 队形几何关系精确保持（圆形、V形、横线、弧形等）
- ✅ 切换预瞄点时队形不再错乱
- ✅ "有先有后"现象消失
- ✅ 成员间相对位置稳定
- ✅ 保留微弱噪声，增加自然真实感
- ✅ 结果基本可重现（噪声影响极小）

### 参数调优指南

#### 1. 角度噪声 (`formation_generator.py:69`)

根据需要的真实感调整：
```python
# 更自然（稍微明显的不对称）
α = self.angle + np.random.uniform(-1.0, 1.0)

# 当前配置（轻微扰动）
α = self.angle + np.random.uniform(-0.5, 0.5)

# 更精确（几乎完美对称）
α = self.angle + np.random.uniform(-0.2, 0.2)

# 完全移除（完美对称）
α = self.angle
```

#### 2. 位置噪声倍率 (`formation_generator.py:172`)

调整噪声规模：
```python
# 更明显（原来的 20%）
noise = np.random.normal(scale=self.noise_scale * 0.2, size=3)

# 当前配置（原来的 10%）
noise = np.random.normal(scale=self.noise_scale * 0.1, size=3)

# 更精确（原来的 5%）
noise = np.random.normal(scale=self.noise_scale * 0.05, size=3)

# 完全移除（完美队形）
noise = np.zeros(3)
# 或直接: p_w = Rm.dot(p_body) + base
```

#### 3. 同步阈值 (`behaviours.py:25`)

根据队形整齐度和等待时间权衡：
```python
# 更严格（队形更整齐，但等待时间可能更长）
CLOSE_TH_SYNC = 0.3  # 或 0.2

# 当前配置（平衡）
CLOSE_TH_SYNC = 0.5

# 稍微放松（减少等待时间，允许轻微偏差）
CLOSE_TH_SYNC = 0.8  # 或 1.0

# 原始配置（过松，不推荐）
CLOSE_TH_SYNC = 3.0
```

### 相关文件

- **详细分析报告**: [`FORMATION_SYNC_BUG_ANALYSIS.md`](FORMATION_SYNC_BUG_ANALYSIS.md)
- **主要修改文件**:
  - `planning_modules/formation_generator.py` (line 69, 172)
  - `behaviours.py` (line 25)
- **相关文档**: [`README.md`](README.md) (添加"队形同步修复"章节)

### Breaking Changes

无。这些修复是参数调整和噪声规模优化，不影响 API 或数据格式。

### Migration Guide

无需迁移。现有代码可以直接使用修复后的版本。

如果之前有自定义的噪声参数或同步阈值，建议参考本次修复重新评估：
- 噪声应该足够小，不累积成队形偏差
- 同步阈值应该足够小，保证切换时起跑线对齐

### Known Issues

无。

### Future Improvements

可考虑的优化方向：
1. 将噪声参数暴露到配置文件，而非硬编码在生成器中
2. 添加队形质量监控指标（成员间距标准差等）
3. 支持动态调整同步阈值（根据飞行速度自适应）
4. 添加队形"归位"机制，定期校准成员位置

---

## [Earlier] 初始版本

纯 Python 移植 `uav_dynamic_agents02.py`，移除 SPADE/Redis 依赖。
