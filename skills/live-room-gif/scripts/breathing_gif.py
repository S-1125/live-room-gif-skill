#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import shutil
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw

from audit_gif import 检查 as 检查GIF
from build_gif import 转透明调色帧


def 准备输出目录(路径: Path, 覆盖: bool) -> None:
    """避免无意覆盖已有成品。"""
    if 路径.exists() and any(路径.iterdir()) and not 覆盖:
        raise SystemExit(f"输出目录非空：{路径}\n如需覆盖，请添加 --overwrite。")
    if 路径.exists() and 覆盖:
        shutil.rmtree(路径)
    路径.mkdir(parents=True)


def 棋盘背景(尺寸: tuple[int, int], 格子: int = 24) -> Image.Image:
    """生成透明预览棋盘格。"""
    背景 = Image.new("RGB", 尺寸, (255, 255, 255))
    绘制 = ImageDraw.Draw(背景)
    for y in range(0, 尺寸[1], 格子):
        for x in range(0, 尺寸[0], 格子):
            if (x // 格子 + y // 格子) % 2:
                绘制.rectangle((x, y, x + 格子 - 1, y + 格子 - 1), fill=(226, 226, 226))
    return 背景


def 呼吸缩放(进度: float, 最小缩放: float, 最大缩放: float) -> float:
    """使用余弦曲线在最小值、最大值和最小值之间呼吸。"""
    比例 = 0.5 - 0.5 * math.cos(math.tau * 进度)
    return 最小缩放 + (最大缩放 - 最小缩放) * 比例


def 缩放到画布(原图: Image.Image, 缩放: float) -> Image.Image:
    """围绕中心使用浮点仿射缩放，避免整数尺寸造成重复帧。"""
    宽, 高 = 原图.size
    逆缩放 = 1.0 / 缩放
    中心X = 宽 / 2
    中心Y = 高 / 2
    return 原图.transform(
        原图.size,
        Image.Transform.AFFINE,
        (
            逆缩放,
            0,
            中心X - 中心X * 逆缩放,
            0,
            逆缩放,
            中心Y - 中心Y * 逆缩放,
        ),
        resample=Image.Resampling.BICUBIC,
        fillcolor=(0, 0, 0, 0),
    )


def 保存棋盘预览(帧: Image.Image, 路径: Path) -> None:
    """保存透明区域检查图。"""
    画布 = 棋盘背景(帧.size)
    画布.paste(帧, (0, 0), 帧)
    画布.save(路径, format="PNG")


def 保存关键帧拼图(路径列表: list[Path], 输出路径: Path) -> None:
    """生成缩放过程关键帧拼图。"""
    列数 = 3
    间距 = 12
    缩略宽 = 360
    首帧 = Image.open(路径列表[0]).convert("RGBA")
    缩略高 = max(1, round(首帧.height * 缩略宽 / 首帧.width))
    行数 = math.ceil(len(路径列表) / 列数)
    画布 = Image.new(
        "RGB",
        (
            列数 * 缩略宽 + (列数 + 1) * 间距,
            行数 * 缩略高 + (行数 + 1) * 间距,
        ),
        (245, 237, 239),
    )
    for 序号, 路径 in enumerate(路径列表):
        列 = 序号 % 列数
        行 = 序号 // 列数
        图像 = Image.open(路径).convert("RGBA").resize(
            (缩略宽, 缩略高),
            Image.Resampling.LANCZOS,
        )
        x = 间距 + 列 * (缩略宽 + 间距)
        y = 间距 + 行 * (缩略高 + 间距)
        画布.paste(图像, (x, y), 图像)
    画布.save(输出路径, quality=93, subsampling=0)


def 保存透明GIF(帧目录: Path, 目标路径: Path, 时长毫秒: int) -> None:
    """把透明 PNG 序列合成为无限循环 GIF。"""
    路径列表 = sorted(帧目录.glob("*.png"))
    调色帧 = [
        转透明调色帧(Image.open(路径).convert("RGBA"))
        for 路径 in 路径列表
    ]
    调色帧[0].save(
        目标路径,
        save_all=True,
        append_images=调色帧[1:],
        duration=时长毫秒,
        loop=0,
        disposal=2,
        optimize=True,
        transparency=255,
        background=255,
    )


def 打包帧目录(帧目录: Path, 目标路径: Path) -> None:
    """打包全部透明帧。"""
    with zipfile.ZipFile(目标路径, "w", compression=zipfile.ZIP_DEFLATED) as 压缩包:
        for 路径 in sorted(帧目录.glob("*.png")):
            压缩包.write(路径, 路径.name)


def 解析参数() -> argparse.Namespace:
    """读取命令行参数。"""
    解析器 = argparse.ArgumentParser(description="生成以中心缩放的呼吸循环 GIF。")
    解析器.add_argument("--image", required=True, help="输入透明图片")
    解析器.add_argument("--output-dir", required=True, help="成品输出目录")
    解析器.add_argument("--name", default="缩放呼吸", help="成品文件名前缀")
    解析器.add_argument("--min-scale", type=float, default=0.90, help="最小缩放比例")
    解析器.add_argument("--max-scale", type=float, default=1.00, help="最大缩放比例")
    解析器.add_argument("--frames", type=int, default=120, help="总帧数")
    解析器.add_argument("--duration-ms", type=int, default=30, help="每帧时长")
    解析器.add_argument("--overwrite", action="store_true")
    return 解析器.parse_args()


def 主程序() -> None:
    """生成呼吸帧、透明 GIF、审核预览与检查报告。"""
    参数 = 解析参数()
    if not 0 < 参数.min_scale < 参数.max_scale <= 1:
        raise SystemExit("缩放比例必须满足 0 < min-scale < max-scale <= 1。")
    if 参数.frames < 2:
        raise SystemExit("帧数必须至少为 2。")
    if 参数.duration_ms < 20:
        raise SystemExit("每帧时长必须至少为 20ms。")

    源路径 = Path(参数.image).expanduser().resolve()
    if not 源路径.exists():
        raise SystemExit(f"输入图片不存在：{源路径}")

    输出目录 = Path(参数.output_dir).expanduser().resolve()
    准备输出目录(输出目录, 参数.overwrite)
    帧目录 = 输出目录 / "静态帧"
    帧目录.mkdir()

    原图 = Image.open(源路径).convert("RGBA")
    关键序号 = {
        0,
        参数.frames // 5,
        参数.frames * 2 // 5,
        参数.frames * 3 // 5,
        参数.frames * 4 // 5,
        参数.frames - 1,
    }
    关键帧: list[Path] = []

    for 序号 in range(参数.frames):
        进度 = 序号 / 参数.frames
        缩放 = 呼吸缩放(进度, 参数.min_scale, 参数.max_scale)
        帧 = 缩放到画布(原图, 缩放)
        路径 = 帧目录 / f"{序号 + 1:04d}.png"
        帧.save(路径)
        if 序号 in 关键序号:
            关键帧.append(路径)

    gif路径 = 输出目录 / f"{参数.name}_透明.gif"
    保存透明GIF(帧目录, gif路径, 参数.duration_ms)
    保存棋盘预览(Image.open(关键帧[2]).convert("RGBA"), 输出目录 / "透明效果棋盘预览.png")
    保存关键帧拼图(关键帧, 输出目录 / "关键帧预览.jpg")
    打包帧目录(帧目录, 输出目录 / "逐帧素材.zip")

    报告 = 检查GIF(gif路径)
    (输出目录 / "审计报告.json").write_text(
        json.dumps(报告, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if 报告["警告"]:
        raise SystemExit(f"GIF 审计发现警告：{报告['警告']}")

    (输出目录 / "动画参数.json").write_text(
        json.dumps(
            {
                "源图片": str(源路径),
                "画布尺寸": list(原图.size),
                "帧数": 参数.frames,
                "帧时长毫秒": 参数.duration_ms,
                "总时长毫秒": 参数.frames * 参数.duration_ms,
                "最小缩放": 参数.min_scale,
                "最大缩放": 参数.max_scale,
                "曲线": "余弦呼吸",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"呼吸 GIF：{gif路径}")
    print(f"缩放：{参数.min_scale:.0%} → {参数.max_scale:.0%} → {参数.min_scale:.0%}")
    print(f"帧数：{参数.frames}，每帧：{参数.duration_ms}ms")
    print(f"关键帧预览：{输出目录 / '关键帧预览.jpg'}")


if __name__ == "__main__":
    主程序()
