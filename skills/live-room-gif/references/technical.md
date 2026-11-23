# GIF 技术要点

## 检查与拆帧

```bash
python3 scripts/audit_gif.py input.gif --json-out report.json
python3 scripts/extract_gif.py input.gif --output-dir frames --overwrite
```

拆帧输出为 RGBA PNG，并附带 `帧信息.json`。先检查报告中的时长序列、循环标记、透明索引和相邻帧变化，再判断是否需要重建。

## 从图片序列合成

```bash
python3 scripts/build_gif.py \
  --frames-dir frames \
  --output out.gif \
  --duration-ms 800 \
  --transparent auto \
  --overwrite
```

所有输入帧必须同尺寸、同顺序。默认无限循环；速度按每帧固定毫秒数处理。

## 透明

- GIF 只支持一个透明色索引，不支持连续 alpha。
- 透明区域在深色应用中会呈现为黑色，这是预览底色，不一定是文件仍有黑底。
- 必须重新读取 alpha 通道或生成棋盘格预览，不能只凭深色预览判断。
- 透明 GIF 调色时保留原 RGB 调色板，再将未使用索引设为透明。禁止重建 P 图时丢弃原调色板。
- 外部黑底素材只抠与四边连通的深色区域，海报内部黑色商品应保持不透明。

## 时长与循环

- 同一动画默认使用固定单帧时长。
- 本地技术报告可以保留毫秒值，但最终播放器可能按 GIF 的最小单位取整。
- 循环次数 `0` 通常表示无限循环。
- 需要不同帧停留时间时，应在需求中明确，且回读每一帧的 `duration`。

## 优化

- 先减少尺寸、颜色复杂度和不必要的帧数，再考虑降低帧率。
- 文字和小图标较多的动画不适合激进减色；交付前必须查看缩略图和实际播放效果。
- 文件大小明显超出投放限制时，优先建议 WebP 动画或视频，并说明平台兼容性。
