#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

from PIL import Image, ImageDraw


def 解析参数() -> argparse.Namespace:
    """读取命令行参数。"""
    解析器 = argparse.ArgumentParser(description="把逐帧图片排成审核用缩略拼图。")
    解析器.add_argument("--frames-dir", required=True, help="逐帧图片目录")
    解析器.add_argument("--output", required=True, help="输出 JPG 或 PNG 路径")
    解析器.add_argument("--columns", type=int, default=5, help="列数，默认 5")
    解析器.add_argument("--thumb-width", type=int, default=204, help="缩略宽度，默认 204")
    解析器.add_argument("--checker", action="store_true", help="使用棋盘格显示透明区域")
    解析器.add_argument("--overwrite", action="store_true", help="允许覆盖已有文件")
    return 解析器.parse_args()


def 自然排序(路径: Path) -> list[object]:
    """按数字大小排序帧文件。"""
    return [int(片段) if 片段.isdigit() else 片段.lower() for 片段 in re.split(r"(\d+)", 路径.name)]


def 棋盘背景(尺寸: tuple[int, int], 格子: int = 24) -> Image.Image:
    """生成浅色棋盘格背景。"""
    背景 = Image.new("RGB", 尺寸, (255, 255, 255))
    绘制 = ImageDraw.Draw(背景)
    for y in range(0, 尺寸[1], 格子):
        for x in range(0, 尺寸[0], 格子):
            if (x // 格子 + y // 格子) % 2:
                绘制.rectangle(
                    (x, y, x + 格子 - 1, y + 格子 - 1),
                    fill=(226, 226, 226),
                )
    return 背景


def 主程序() -> None:
    """生成审核拼图。"""
    参数 = 解析参数()
    帧目录 = Path(参数.frames_dir).expanduser().resolve()
    输出路径 = Path(参数.output).expanduser().resolve()
    路径列表 = sorted(
        [路径 for 路径 in 帧目录.iterdir() if 路径.suffix.lower() in {".png", ".webp"}],
        key=自然排序,
    )
    if not 路径列表:
        raise SystemExit(f"目录中没有可用的逐帧图片：{帧目录}")
    if 输出路径.exists() and not 参数.overwrite:
        raise SystemExit(f"输出文件已存在：{输出路径}\n如需覆盖，请添加 --overwrite。")

    首帧 = Image.open(路径列表[0]).convert("RGBA")
    比例 = 参数.thumb_width / 首帧.width
    缩略高 = round(首帧.height * 比例)
    间距 = 14
    行数 = (len(路径列表) + 参数.columns - 1) // 参数.columns
    尺寸 = (
        参数.columns * 参数.thumb_width + (参数.columns + 1) * 间距,
        行数 * 缩略高 + (行数 + 1) * 间距,
    )
    拼图 = 棋盘背景(尺寸) if 参数.checker else Image.new("RGB", 尺寸, (232, 222, 209))

    for 序号, 路径 in enumerate(路径列表):
        列 = 序号 % 参数.columns
        行 = 序号 // 参数.columns
        缩略图 = (
            Image.open(路径)
            .convert("RGBA")
            .resize((参数.thumb_width, 缩略高), Image.Resampling.LANCZOS)
        )
        x = 间距 + 列 * (参数.thumb_width + 间距)
        y = 间距 + 行 * (缩略高 + 间距)
        拼图.paste(缩略图, (x, y), 缩略图)

    输出路径.parent.mkdir(parents=True, exist_ok=True)
    拼图.save(输出路径, quality=92, subsampling=0)
    print(f"审核拼图：{输出路径}")


if __name__ == "__main__":
    主程序()
