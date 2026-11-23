---
name: live-room-gif
description: 制作和迭代直播间 GIF 动画，覆盖参考动图拆解、文字与数据轮播、商品或贴纸动效、透明背景、节奏控制和批量交付；以真实审核案例沉淀可复用配方。
metadata:
  version: "0.4.0"
---

# 直播间 GIF 动画

把直播间真实需求做成可审核的 GIF 成品，再把审核通过的做法沉淀成案例配方。当前能力不是预先写死所有场景，而是提供统一的拆解、制作、检查、反馈和晋级流程。

## 开始前

先读取 [references/workflow.md](references/workflow.md) 确认需求字段、审核门槛和案例晋级规则。涉及参考 GIF、透明背景、时长、循环或交付兼容性时，同时读取 [references/technical.md](references/technical.md)。

已有案例见 [references/case-registry.md](references/case-registry.md)。如果需求属于已登记案例，优先沿用其中已验证的实现；不要为了“通用”而重写已经通过的流程。

## 路由

- **参考动图复刻或二次创作**：先拆帧并读取每帧时长、循环、透明索引和变化区域，再决定重建方式。
- **跑马灯**：读取 [references/marquee.md](references/marquee.md)。无论文本还是图片，最终可见内容必须保持单行，并从左到右连续划过。
- **扫光动画**：读取 [references/sweep.md](references/sweep.md)。优先使用稳定脚本，不要在同类需求中重复手调。
- **缩放呼吸**：读取 [references/breathing.md](references/breathing.md)。默认 `90% → 100% → 90%`，允许按需求微调最小和最大比例。
- **固定底稿的文字、价格或状态轮播**：优先复用对应案例。天气海报轮播已登记为 `$weather-poster-gif` 案例。
- **新动画类型**：先做最小可行的关键帧和时长方案，得到用户对视觉、节奏和尺寸的确认后，再批量扩展。
- **只优化现有 GIF**：先审计，不要跳过问题诊断直接重新编码。

## 制作流程

1. 收集原图、参考 GIF、文案、尺寸、帧时长、循环次数、透明要求和投放平台限制。缺失项只有会影响成品正确性时才提问。
2. 拆解视觉层级和动画逻辑：哪些元素固定、哪些变化、变化顺序、每段停留多久、是否需要首尾无缝衔接。
3. 定义帧计划。每帧尺寸一致；同一轮播内默认匀速。不同画面确需不同停顿时，必须在方案中明确。
4. 使用专门脚本或已审核案例生成逐帧 PNG。透明素材保留 alpha，不要在中间步骤压到黑底或白底。
5. 用 `scripts/audit_gif.py` 检查帧数、时长、循环、透明、空白帧和相邻帧变化；为全部帧生成缩略审核图。
6. 向用户交付 GIF、逐帧素材、透明预览或关键帧预览，并说明帧数、单帧时长、总时长和循环方式。
7. 只有用户明确认可后，才把这次做法写入案例登记。未通过的部分只记录为待验证经验，不升级成通用规则。

## 通用工具

- 检查 GIF：`python3 scripts/audit_gif.py input.gif --json-out report.json`
- 生成稳定跑马灯：`python3 scripts/marquee_gif.py text ...` 或 `python3 scripts/marquee_gif.py images ...`
- 生成稳定扫光：`python3 scripts/sweep_gif.py --image input.png --output-dir outputs/sweep --color "#FFFFFF"`
- 生成缩放呼吸：`python3 scripts/breathing_gif.py --image input.png --output-dir outputs/breathing`
- 拆解参考 GIF：`python3 scripts/extract_gif.py input.gif --output-dir frames`
- 从 PNG 序列生成 GIF：`python3 scripts/build_gif.py --frames-dir frames --output out.gif --duration-ms 800`
- 生成审核拼图：`python3 scripts/contact_sheet.py --frames-dir frames --output preview.jpg --checker`

## 不能省略的约束

- GIF 时间通常以 10ms 为最小可感知单位；不要承诺低于播放器实际支持的精确时长。
- 透明 GIF 只有二值透明，不支持柔和半透明边缘。需要抗锯齿半透明时，应建议 APNG、WebP 动画或视频格式，并说明投放兼容性。
- 对外部黑底抠透明时，只处理与画布边缘连通的背景，不能把所有黑色像素设为透明。
- 透明 GIF 必须保留彩色调色板，并单独预留透明索引；重新创建 P 模式图像很容易导致整帧发黑。
- 深色预览器会把透明区域显示成黑色。必须用棋盘格预览和重新读取的 alpha 通道判断透明是否成功。
- 用户原文要逐字保留。不要擅自统一符号、单位、大小写或数字格式。
- 新方案默认写入新目录，不覆盖上一版；用户明确要求替换时才覆盖。
- 不能因为完成了一个案例就宣称已覆盖所有直播间场景。新能力只能由真实需求和审核结果支撑。

## 技能迭代

每次真实需求结束后，更新 [references/case-registry.md](references/case-registry.md)：

- 已审核：记录稳定做法、可复用点、关键参数和成品验证结果。
- 待修改：记录用户不接受的视觉或节奏问题，不把该版本标记为稳定。
- 新类型：先增加案例条目，验证至少一次后，再考虑抽取独立脚本。

优先做窄而可靠的修正，不把单个案例的偏好扩展成所有直播间的通用规则。
