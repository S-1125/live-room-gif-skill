# 配置说明

## 数据文件

推荐使用对象格式：

```json
{
  "items": [
    {
      "name": "北京",
      "city": "北京",
      "temperature": "8～-1°C"
    },
    {
      "name": "天津",
      "city": "天津",
      "temperature": "7～-1°C"
    }
  ]
}
```

也可以直接使用数组。`name` 仅用于输出文件名；文字槽位通过 `field` 读取 `city`、`temperature` 等字段。

## 排版配置

以下配置对应一张 `856×1837` 的海报样例：

```json
{
  "font": "/Users/sunyao/Library/Fonts/MiSans-Semibold.ttf",
  "prefix": "天气降温预警",
  "duration_ms": 800,
  "black_threshold": 55,
  "preview_columns": 5,
  "thumbnail_width": 204,
  "erase_regions": [
    {
      "box": [112, 1228, 744, 1684],
      "brightness_threshold": 190,
      "dilation": 8,
      "iterations": 360,
      "texture_std": 1.8,
      "feather": 1.6,
      "seed": 20261119
    }
  ],
  "slots": [
    {
      "field": "city",
      "center": [428, 1373],
      "max_size": 246,
      "max_width": 610,
      "min_size": 72,
      "fill": [255, 255, 255]
    },
    {
      "field": "temperature",
      "center": [428, 1590],
      "max_size": 132,
      "max_width": 610,
      "min_size": 78,
      "fill": [255, 255, 255]
    }
  ]
}
```

## 字段

- `box`：待擦除变量文字区域，格式为 `[左, 上, 右, 下]`，右、下边界不包含在区域内。
- `brightness_threshold`：识别亮色文字的最低 RGB 通道值。底图越亮，该值应越高。
- `dilation`：文字蒙版向外扩张的像素数，用来覆盖抗锯齿亮边。
- `iterations`：邻域底色扩散次数。文字越粗、区域越大，需要越多，但速度会更慢。
- `texture_std`：修复区补入的颗粒强度。设为 `0` 可完全关闭。
- `feather`：蒙版羽化半径。出现硬边时可增大。
- `center`：新文字的可见像素中心点。
- `max_size`、`min_size`：字号搜索范围。
- `max_width`：文字允许占用的最大像素宽度。
- `fill`：文字 RGB 颜色。
- `black_threshold`：识别海报外侧黑底时允许的最大 RGB 通道值。

## 校准方法

1. 先使用较宽松的擦除区域覆盖旧文字及其亮边，但不要覆盖固定标题。
2. 只输出首帧检查。底色出现色带时，增大 `iterations`；出现方块接缝时，不要整块替换，应继续使用字形蒙版。
3. 长文字越界时减小 `max_width` 或降低 `max_size`；短文字过小时提高 `max_size`。
4. 透明 PNG 四角应为透明，但牛仔裤等内部黑色区域必须保持不透明。
5. 深色界面中透明边缘可能显示为黑色，应以棋盘格预览和重新读取的 alpha 通道为准。
