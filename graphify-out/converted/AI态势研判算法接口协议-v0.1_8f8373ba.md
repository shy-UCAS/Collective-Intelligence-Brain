<!-- converted from AI态势研判算法接口协议-v0.1.docx -->

AI态势研判算法输入输出协议
面向前端、后端、算法联调的接口契约草案 | v0.1

# 1. 接口定位与边界
算法服务负责把融合航迹、设施空域、白名单、计划、演练、载荷、机型等态势快照转换为可解释的意图、威胁、决策和处置建议。

# 2. 推荐总接口
建议后端只调用一个算法总接口，由算法服务内部串联聚类、编队、圈层、意图、威胁、决策和处置建议。
POST /analyze_situation
Content-Type: application/json

内部处理链路：轨迹预处理 -> 集群划分 -> 编队识别 -> 圈层/空域判断 -> 意图规则 -> 十维威胁评分 -> 硬规则抬底 -> 智能决策 -> 处置建议。
# 3. 请求协议
{
"requestId": "req-20260729-0001",
"timestamp": "2026-07-29T10:30:00+08:00",
"sceneId": "scene-001",
"tracks": [],
"facilities": {},
"airspaces": [],
"whitelist": [],
"flightPlans": [],
"drills": [],
"hoverExemptHotspots": [],
"regionSwitches": {"crossBorderSmugglingEnabled": false},
"options": {
"enableClustering": true,
"enableFormation": true,
"enableDecision": true,
"returnDebug": false
}
}

## 3.1 第一版必填字段

## 3.2 tracks 航迹字段
{
"targetId": "uav_001",
"lngs": [122.0881, 122.0882, 122.0883],
"lats": [37.5637, 37.5636, 37.5635],
"alts": [80, 95, 135],
"ts": [14, 15, 16],
"speedMps": 12.5,
"headingDeg": 92,
"confidence": 0.86,
"identity": {
"sn": "SN001",
"remoteId": "RID001",
"registrationStatus": "unregistered",
"pilotId": null
},
"model": {
"modelId": "dji-mavic-3",
"modelName": "DJI Mavic 3",
"class": "small"
},
"payload": {
"payloadClass": "unknown",
"payloadConfidence": 0.5,
"payloadDesc": "未识别载荷",
"releaseEvent": false,
"source": "optical"
}
}


## 3.3 facilities 设施字段
第一版兼容当前算法项目格式，便于复用已有接口。
{
"radar_1": [122.094416, 37.548881],
"hq_1": [122.0906111, 37.5426285],
"hq_2": [122.0867114, 37.5438984],
"ua_1": [122.0905609, 37.5488813],
"ua_2": [122.0885429, 37.5456034],
"RING1": [122.0862974, 37.54761, 122.0914643, 37.5450229],
"RING2": [122.0836284, 37.5481976, 122.0949838, 37.5527325],
"uav_counts": [20, 15]
}

建议后续升级为结构化 facilities，以避免 ua_1、hq_1、RING1 等字符串约定造成歧义。
## 3.4 空域 airspaces
[
{
"airspaceId": "zone_warn_001",
"name": "预警区",
"type": "warn",
"polygon": [[122.08, 37.54], [122.09, 37.54], [122.09, 37.55]],
"enabled": true
},
{
"airspaceId": "zone_hard_001",
"name": "法定禁飞区",
"type": "hard",
"polygon": [],
"enabled": true
}
]


## 3.5 白名单、计划、演练

# 4. 响应协议
{
"requestId": "req-20260729-0001",
"timestamp": "2026-07-29T10:30:00+08:00",
"sceneId": "scene-001",
"status": "success",
"summary": {
"targetCount": 3,
"clusterCount": 2,
"eventCount": 1,
"highestThreatGrade": "mid",
"needAlarm": false
},
"clusters": [],
"warnings": [],
"errors": []
}

## 4.1 clusters 输出结构
{
"clusterId": "eSwarm1",
"members": ["uav_001", "uav_002"],
"formation": "random",
"situation": {
"airspaceType": "alert",
"airspaceName": "警戒区",
"breachCircle": "C2",
"nearestFacilityId": "hq_1",
"nearestFacilityName": "指挥部1",
"distanceToNearestFacilityM": 420.5,
"currentCenter": [122.0883, 37.5635]
},
"intent": {
"intentCode": "I-12",
"intentCategory": "违规飞行（非恶意）",
"intentLabel": "超高飞行",
"intentConfidence": 0.82,
"intentBandHint": "130-300m"
},
"threat": {},
"decision": {},
"disposal": {},
"evidenceChain": []
}

## 4.2 威胁 threat
{
"threatScore": 58,
"threatGrade": "mid",
"dimScores": {
"intent": 55,
"airspace": 60,
"height": 65,
"behavior": 40,
"trend": 50,
"compliance": 80,
"cluster": 45,
"model": 50,
"payload": 50,
"pilot": 50
},
"weights": {
"intent": 0.18,
"airspace": 0.16,
"height": 0.16,
"behavior": 0.16,
"trend": 0.06,
"compliance": 0.12,
"cluster": 0.07,
"model": 0.04,
"payload": 0.03,
"pilot": 0.02
},
"hardRules": [
{
"ruleId": "R3",
"description": "真高高于130米，威胁至少中",
"floorScore": 36
}
]
}


## 4.3 决策 decision 与处置 disposal
{
"decision": {
"createEvent": true,
"eventType": "threat",
"eventLevel": "mid",
"needAlarm": false,
"needHumanReview": true,
"reason": "目标未登记且超高飞行，建议建威胁事件"
},
"disposal": {
"chainType": "tiered",
"suggestedTacticTier": "T1",
"authorizationRequired": false,
"planRequired": false,
"actions": [
{"actionCode": "WARN_BROADCAST", "actionName": "广播劝离", "priority": 1},
{"actionCode": "CONTACT_OWNER", "actionName": "联系飞手", "priority": 2}
]
}
}


## 4.4 依据链 evidenceChain
[
{
"rule": "高度规则",
"fields": ["alts"],
"values": {"currentAltM": 135},
"conclusion": "真高超过130米，判定为超高飞行"
},
{
"rule": "登记规则",
"fields": ["registrationStatus"],
"values": {"registrationStatus": "unregistered"},
"conclusion": "目标未登记，合规维风险较高"
}
]

# 5. 枚举约定

# 6. 错误与降级
接口应优先保证流程可跑通。字段缺失时尽量返回 warnings 并使用默认分；只有无法进行基本研判时才返回 failed。
{
"warnings": [
{"code": "MISSING_ALTITUDE", "message": "未提供高度，威胁高度维使用默认分"},
{"code": "MISSING_PAYLOAD", "message": "未提供载荷识别，载荷维使用 unknown"}
],
"errors": []
}


# 7. 前后端与算法分工

# 8. 会议必须确认的问题
- 后端是否能每次给算法传批量航迹，而不是单目标。
- 高度字段到底是什么：AGL 真高、海拔、雷达高度，还是暂时没有高度。
- 空域是否能提供预警区、警戒区、反制区、法定禁飞区四类几何。
- 白名单、飞行计划、演练清单由后端随请求传入，还是算法直接查库。
- 事件由谁创建。建议后端创建，算法只返回 createEvent 和 reason。
- 处置动作由谁执行。建议后端执行，算法只返回 suggestedTacticTier 和 actions。
- 前端是否展示十维分、硬规则、依据链和处置建议。
- 接口调用频率是多少：1 秒一次、5 秒一次，还是事件触发。
- 单次请求最多包含多少架无人机，最大轨迹长度是多少。
- 是否需要算法返回历史状态，例如首次高威胁、威胁升级、上次处置建议。
# 9. 第一版交付边界

# 10. 和当前算法项目的衔接
当前项目已有多个原子接口。建议新增 /analyze_situation 作为总接口，内部复用现有 main_apis.py 能力，并新增规则编排层。


| 文档定位  本协议用于会议对齐算法服务输入输出边界。当前两份产品资料提供的是算法规则和字段线索，不是完整 HTTP 接口文档；本稿在现有项目能力和产品规则基础上补齐联调协议。 |
| --- |
| 算法负责 | 算法不负责 |
| --- | --- |
| 态势研判、意图识别、十维威胁评分 | 不直接创建事件、不写业务数据库 |
| 硬规则抬底、是否建案建议 | 不直接执行反制、不发送短信/电话/广播 |
| 处置链类型、建议动作、授权需求 | 不做权限校验、不替代人工审批 |
| 依据链 evidenceChain，支持前端解释展示 | 不作为唯一执法或反制依据 |
| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| requestId | string | 是 | 本次请求 ID，由后端生成，算法原样返回 |
| timestamp | string | 是 | 当前态势时间，建议 ISO 8601，含时区 |
| tracks | array | 是 | 当前批量航迹。建议批量输入，支持聚类和蜂群判断 |
| tracks[].targetId | string | 是 | 目标唯一 ID |
| tracks[].lngs / lats / ts | number[] | 是 | 经度、纬度、时间序列，长度需一致 |
| facilities | object | 是 | 重点设施、防御圈、机场、雷达等 |
| 关键确认  高度字段建议统一为相对地面真高 AGL，单位米。产品规则中的高度维、超高飞行、硬规则 R3/R4 都依赖该字段。 |
| --- |
| type | 中文含义 | 算法语义 |
| --- | --- | --- |
| warn | 预警区 | 普通圈层劝导入口 |
| alert | 警戒区 | 中等空域风险 |
| core | 反制区 | 疑似恶意，威胁硬规则可抬高 |
| hard | 法定禁飞区 | 入侵禁飞区，走硬处置链 |
| test | 试验空域 | 一期只展示，不参与白名单豁免判定 |
| drill | 演练空域 | 展示演练几何，豁免以演练清单为准 |
| 对象 | 第一版用途 | 关键字段 |
| --- | --- | --- |
| whitelist | 命中有效白名单则一般不建威胁事件 | sn、remoteId、enabled、validFrom、validTo、purpose |
| flightPlans | 有效计划命中则输出合规目标 | planId、taskType、sn、validFrom、validTo、route、status |
| drills | 演练清单命中则一般不建威胁事件 | drillId、active、validFrom、validTo、allowedSns、allowedModels |
| hoverExemptHotspots | 悬停豁免热点 | name、type、polygon、enabled、validFrom、validTo |
| 维度 | 权重 | 第一版可用数据 |
| --- | --- | --- |
| 意图推断 | 18% | intentCategory、intentConfidence |
| 空域与圈层 | 16% | airspaceType、breachCircle、禁飞区命中 |
| 高度 | 16% | alts 当前真高 AGL |
| 行为态势 | 16% | 悬停、绕飞、俯冲、规避等轨迹派生特征 |
| 轨迹与动向 | 6% | ETA、是否逼近要地、预测风险 |
| 合规与登记 | 12% | registrationStatus、白名单、计划、演练 |
| 集群与编队 | 7% | 成员数量、formation、同步抵近 |
| 机型与属性 | 4% | model.class、modelName，缺失时中性默认 |
| 载荷 | 3% | payloadClass、payloadConfidence、releaseEvent |
| 飞手画像 | 2% | pilotId、信用/违规记录，缺失时中性默认 |
| 规则边界  高威胁不等于必须 T3。算法只给出建议处置层级和动作，授权与执行必须由后端业务流程和人工权限控制。 |
| --- |
| 枚举项 | 取值 |
| --- | --- |
| threatGrade | low：低，0-35；mid：中，36-65；high：高，66-100 |
| registrationStatus | whitelist、registered_rid、registered、unregistered、unknown |
| payloadClass | none、standard_camera、standard_cargo、spray、unknown、nonstandard、weapon_suspect、drop_capable |
| chainType | exempt：豁免/合规；tiered：普通圈层处置链；hard：禁飞区/核心区硬处置链 |
| actionCode | OBSERVE、WARN_BROADCAST、SEND_SMS、CONTACT_OWNER、DISPATCH_PATROL、TRACK_CONTINUOUSLY、COUNTER_PREPARE、COUNTER_AUTHORIZE、COUNTER_EXECUTE |
| 失败条件 | 处理方式 |
| --- | --- |
| tracks 为空 | status=failed，返回 INVALID_TRACKS |
| 轨迹缺少 lngs/lats/ts | status=failed，返回 INVALID_TRACK_FORMAT |
| facilities 完全缺失 | status=failed 或降级，仅保留轨迹行为类研判；会上需确认 |
| JSON 格式错误 | HTTP 400，返回 INVALID_JSON |
| 角色 | 职责 |
| --- | --- |
| 后端 | 汇聚态势快照，调用算法接口，保存结果，创建事件，控制处置流程，权限校验，推送前端 |
| 算法 | 接收快照，输出集群、意图、威胁分、决策建议、处置建议和依据链 |
| 前端 | 展示目标列表、意图标签、威胁等级、十维分解、依据链、建议处置动作、声光告警状态 |
| 产品 | 确认规则口径、字段优先级、处置流程边界和第一版演示样例 |
| 第一版支持 | 第一版 mock 或默认 |
| --- | --- |
| 批量航迹输入、集群划分、编队识别 | 飞行计划精确匹配 |
| 圈层/空域判断、规则意图判定 | 气象风偏、设备失控真实链路 |
| 十维威胁评分、硬规则抬底 | 真实载荷识别、飞手画像 |
| 是否建案建议、处置动作建议 | 大模型策略生成、自动反制执行 |
| 依据链解释，支持前端展示 | 复杂跨区域走私规则默认关闭 |
| 现有能力 | 建议在总接口中的位置 |
| --- | --- |
| /get_uavs_clusters | 集群划分 |
| /get_fleet_formtype | 编队识别 |
| /get_ring_breach_status | 圈层/突防判断 |
| /get_enemy_intentions | 作为意图候选或历史规则能力复用 |
| /get_enemy_threats、/get_facility_threats | 作为威胁候选或辅助信息 |
| /get_defend_status | 作为处置资源/防御能力参考 |
| /get_weak_ranges、/get_enemy_escape_locs、/get_enemy_crucial_nodes | 作为详情页或扩展研判能力 |
| 建议落地方式  不要把所有规则直接塞进 main_apis.py。建议新增 situation_pipeline.py、intent_rules_v2.py、threat_score_v2.py、decision_rules.py、disposal_rules.py，让总接口只负责组织流程。 |
| --- |