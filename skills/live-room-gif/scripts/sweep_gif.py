#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import shutil
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from audit_gif import 检查 as 检查GIF
from build_gif import 转透明调色帧


def 解析颜色(值: str) -> tuple[int, int, int]:
    """解析十六进制扫光颜色。"""
    文本 = 值.strip().lstrip("#")
    if len(文本) != 6:
        raise SystemExit(f"颜色必须为 #RRGGBB：{值}")
    return tuple(int(文本[i : i + 2], 16) for i in (0, 2, 4))


def 方向斜率(方向: str) -> float:
    """把方向名称转换为扫光坐标斜率。"""
    if 方向 == "top-left-to-bottom-right":
        return -1.8
    if 方向 == "bottom-left-to-top-right":
        return 1.8
    raise SystemExit(f"未知方向：{方向}")


def 准备输出目录(路径: Path, 覆盖: bool) -> None:
    """避免无意覆盖已有成品。"""
    if 路径.exists() and any(路径.iterdir()) and not 覆盖:
        raise SystemExit(f"输出目录非空：{路径}\n如需覆盖，请添加 --overwrite。")
    if 路径.exists() and 覆盖:
        shutil.rmtree(路径)
    路径.mkdir(parents=True)


def 裁切内容(图像: Image.Image, 留白: int) -> Image.Image:
    """按透明内容边界裁切，避免保留大面积空画布。"""
    alpha = np.asarray(图像.getchannel("A"))
    ys, xs = np.where(alpha > 8)
    if not len(xs):
        raise SystemExit("图片没有可见内容。")
    左 = max(0, int(xs.min()) - 留白)
    上 = max(0, int(ys.min()) - 留白)
    右 = min(图像.width, int(xs.max()) + 留白 + 1)
    下 = min(图像.height, int(ys.max()) + 留白 + 1)
    return 图像.crop((左, 上, 右, 下))


def 扫光蒙版(
    宽: int,
    高: int,
    进度: float,
    斜率: float,
    带宽系数: float,
    核心宽度系数: float,
    不透明度: float,
) -> np.ndarray:
    """生成宽光区、宽核心和受控峰值组成的扫光蒙版。"""
    x = np.arange(宽, dtype=np.float32)[None, :]
    y = np.arange(高, dtype=np.float32)[:, None]
    diagonal = x - 斜率 * y
    diagonal_min = float(diagonal.min())
    diagonal_max = float(diagonal.max())

    宽光标准宽 = max(105.0, 宽 * 带宽系数)
    核心标准宽 = max(52.0, 宽 * 核心宽度系数)
    中心 = diagonal_min + 进度 * (diagonal_max - diagonal_min)
    距离 = np.abs(diagonal - 中心)

    宽光 = np.exp(-0.5 * (距离 / 宽光标准宽) ** 2)
    核心 = np.exp(-0.5 * (距离 / 核心标准宽) ** 2)
    return np.clip(宽光 * 0.40 + 核心 * 0.58, 0.0, 不透明度).astype(np.float32)


def 应用扫光(
    原图: Image.Image,
    进度: float,
    颜色: tuple[int, int, int],
    强度: float,
    斜率: float,
    带宽系数: float,
    核心宽度系数: float,
    不透明度: float,
) -> Image.Image:
    """按原图 alpha 应用扫光，保留原始彩色层次。"""
    数据 = np.asarray(原图.convert("RGBA")).astype(np.float32)
    rgb = 数据[:, :, :3]
    alpha = 数据[:, :, 3]
    蒙版 = 扫光蒙版(
        原图.width,
        原图.height,
        进度,
        斜率,
        带宽系数,
        核心宽度系数,
        不透明度,
    )
    蒙版 *= (alpha / 255.0) * 强度
    强度蒙版 = 蒙版[:, :, None]
    高亮 = np.array(颜色, dtype=np.float32)[None, None, :]

    屏幕 = 255.0 - (255.0 - rgb) * (1.0 - 强度蒙版)
    着色 = rgb * (1.0 - 强度蒙版 * 0.16) + 高亮 * (强度蒙版 * 0.16)
    高光图 = np.clip(屏幕 * 0.84 + 着色 * 0.16, 0.0, 255.0)
    输出 = np.dstack([高光图, alpha]).astype(np.uint8)
    return Image.fromarray(输出, mode="RGBA")


def 棋盘背景(尺寸: tuple[int, int], 格子: int = 24) -> Image.Image:
    """生成透明预览棋盘格。"""
    背景 = Image.new("RGB", 尺寸, (255, 255, 255))
    绘制 = ImageDraw.Draw(背景)
    for y in range(0, 尺寸[1], 格子):
        for x in range(0, 尺寸[0], 格子):
            if (x // 格子 + y // 格子) % 2:
                绘制.rectangle((x, y, x + 格子 - 1, y + 格子 - 1), fill=(226, 226, 226))
    return 背景


def 保存棋盘预览(帧: Image.Image, 路径: Path) -> None:
    """保存透明区域检查图。"""
    画布 = 棋盘背景(帧.size)
    画布.paste(帧, (0, 0), 帧)
    画布.save(路径, format="PNG")


def 保存关键帧拼图(路径列表: list[Path], 输出路径: Path) -> None:
    """保存扫光过程关键帧。"""
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
    解析器 = argparse.ArgumentParser(description="生成透明斜向扫光 GIF。")
    解析器.add_argument("--image", required=True, help="输入图片")
    解析器.add_argument("--output-dir", required=True, help="成品输出目录")
    解析器.add_argument("--name", default="扫光动画", help="成品文件名前缀")
    解析器.add_argument("--color", default="#FFFFFF", help="扫光颜色 #RRGGBB")
    解析器.add_argument(
        "--direction",
        choices=["top-left-to-bottom-right", "bottom-left-to-top-right"],
        default="top-left-to-bottom-right",
        help="扫光推进方向",
    )
    解析器.add_argument("--frames", type=int, default=48, help="总帧数")
    解析器.add_argument("--duration-ms", type=int, default=80, help="每帧时长")
    解析器.add_argument("--strength", type=float, default=1.0, help="整体强度，0-1")
    解析器.add_argument("--opacity", type=float, default=0.98, help="核心最高不透明度，0-1")
    解析器.add_argument("--band-width", type=float, default=0.22, help="宽光宽度系数")
    解析器.add_argument("--core-width", type=float, default=0.105, help="核心宽度系数")
    解析器.add_argument("--crop-padding", type=int, default=28, help="透明内容外留白")
    解析器.add_argument("--preserve-canvas", action="store_true", help="不裁切透明空白")
    解析器.add_argument("--overwrite", action="store_true")
    return 解析器.parse_args()


def 主程序() -> None:
    """生成扫光 GIF、逐帧素材、审核预览和检查报告。"""
    参数 = 解析参数()
    if 参数.frames < 1:
        raise SystemExit("帧数必须大于 0。")
    if 参数.duration_ms < 20:
        raise SystemExit("每帧时长必须至少为 20ms。")
    if not 0 < 参数.strength <= 1:
        raise SystemExit("--strength 必须在 (0, 1] 范围内。")
    if not 0 < 参数.opacity <= 1:
        raise SystemExit("--opacity 必须在 (0, 1] 范围内。")

    源路径 = Path(参数.image).expanduser().resolve()
    if not 源路径.exists():
        raise SystemExit(f"输入图片不存在：{源路径}")

    输出目录 = Path(参数.output_dir).expanduser().resolve()
    准备输出目录(输出目录, 参数.overwrite)
    帧目录 = 输出目录 / "静态帧"
    帧目录.mkdir()

    原图 = Image.open(源路径).convert("RGBA")
    图像 = 原图 if 参数.preserve_canvas else 裁切内容(原图, 参数.crop_padding)
    斜率 = 方向斜率(参数.direction)
    颜色 = 解析颜色(参数.color)
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
        帧 = 应用扫光(
            图像,
            进度,
            颜色,
            参数.strength,
            斜率,
            参数.band_width,
            参数.core_width,
            参数.opacity,
        )
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
                "输出尺寸": list(图像.size),
                "帧数": 参数.frames,
                "帧时长毫秒": 参数.duration_ms,
                "总时长毫秒": 参数.frames * 参数.duration_ms,
                "方向": 参数.direction,
                "扫光颜色": list(颜色),
                "核心不透明度": 参数.opacity,
                "宽光宽度系数": 参数.band_width,
                "核心宽度系数": 参数.core_width,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"扫光 GIF：{gif路径}")
    print(f"帧数：{参数.frames}，每帧：{参数.duration_ms}ms")
    print(f"关键帧预览：{输出目录 / '关键帧预览.jpg'}")
    print(f"逐帧素材：{输出目录 / '逐帧素材.zip'}")


if __name__ == "__main__":
    主程序()
