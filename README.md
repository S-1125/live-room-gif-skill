# 直播间 GIF 动画 Skill

一套用于制作、检查和迭代直播间 GIF 动画的 Codex 技能，覆盖文字与商品跑马灯、扫光动画、缩放呼吸动画，以及参考 GIF 拆解、透明 GIF 合成和自动审计。

## 功能

- 纯文本跑马灯：默认无底座、单行、从左到右无缝循环。
- 图片跑马灯：商品可保留各自的设计边框，不创建整排大底板。
- 扫光动画：可配置扫光颜色、宽度、核心不透明度、速度和倾斜方向。
- 缩放呼吸：默认 `90% → 100% → 90%`，使用余弦曲线围绕中心缩放。
- GIF 拆解：提取逐帧 RGBA 素材、帧时长、循环和透明索引。
- GIF 构建：从 PNG 序列生成透明或不透明动画。
- 自动审计：检查帧数、时长、循环、透明、空白帧和相邻帧变化。
- 自动生成关键帧预览、透明棋盘预览和逐帧素材压缩包。

## 仓库结构

```text
skills/
├── live-room-gif/
│   ├── SKILL.md
│   ├── scripts/
│   └── references/
└── weather-poster-gif/
    ├── SKILL.md
    ├── scripts/
    └── references/
```

`live-room-gif` 是主技能。`weather-poster-gif` 是天气海报城市轮播案例，主技能在对应需求中会引用它。

## 环境依赖

- Python 3.11 或更高版本
- Pillow
- NumPy
- SciPy

安装依赖：

```bash
python3 -m pip install -r requirements.txt
```

## 安装到 Codex

将两个技能目录复制到 Codex 技能目录：

```bash
cp -R skills/live-room-gif ~/.codex/skills/
cp -R skills/weather-poster-gif ~/.codex/skills/
```

重新打开任务后即可通过 `$live-room-gif` 使用。

## 快速使用

### 纯文本跑马灯

```bash
python3 skills/live-room-gif/scripts/marquee_gif.py text \
  --output-dir outputs/text-marquee \
  --text "直播专享｜48 小时发货｜温暖过冬" \
  --width 1080 \
  --height 100 \
  --duration-ms 80 \
  --step-px 10
```

### 商品图片跑马灯

```bash
python3 skills/live-room-gif/scripts/marquee_gif.py images \
  --output-dir outputs/image-marquee \
  --collage products.png \
  --crop-box 5,8,194,232 \
  --crop-box 201,7,390,234 \
  --duration-ms 80 \
  --step-px 10
```

### 扫光动画

```bash
python3 skills/live-room-gif/scripts/sweep_gif.py \
  --image input.png \
  --output-dir outputs/sweep \
  --name 商品扫光 \
  --color "#D6F8FF" \
  --direction top-left-to-bottom-right \
  --opacity 0.98
```

### 缩放呼吸

```bash
python3 skills/live-room-gif/scripts/breathing_gif.py \
  --image input.png \
  --output-dir outputs/breathing \
  --name 商品呼吸 \
  --min-scale 0.90 \
  --max-scale 1.00 \
  --frames 120 \
  --duration-ms 30
```

### 检查和拆解 GIF

```bash
python3 skills/live-room-gif/scripts/audit_gif.py input.gif --json-out report.json
python3 skills/live-room-gif/scripts/extract_gif.py input.gif --output-dir frames
```

### 从 PNG 序列构建 GIF

```bash
python3 skills/live-room-gif/scripts/build_gif.py \
  --frames-dir frames \
  --output output.gif \
  --duration-ms 80 \
  --transparent auto
```

## 设计原则

- 用户文案逐字保留，不擅自修改分隔符、单位或数字。
- 透明 GIF 只使用二值透明，不承诺连续半透明边缘。
- 深色预览器中的透明背景可能显示为黑色，以棋盘预览和 alpha 通道检查为准。
- 新动画类型先完成真实案例并经过审核，再沉淀为稳定脚本。
- 单个案例的视觉偏好不会被无依据地扩展成所有直播间规则。

## 验证

```bash
python3 -m py_compile skills/*/scripts/*.py
python3 skills/live-room-gif/scripts/audit_gif.py --help
python3 skills/live-room-gif/scripts/marquee_gif.py --help
python3 skills/live-room-gif/scripts/sweep_gif.py --help
python3 skills/live-room-gif/scripts/breathing_gif.py --help
```

## 许可证

本项目使用 [MIT License](LICENSE) 开源。
