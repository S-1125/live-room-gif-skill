#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

import numpy as np
from PIL import Image


def 解析参数() -> argparse.Namespace:
    """读取命令行参数。"""
    解析器 = argparse.ArgumentParser(description="把同尺寸 PNG 序列合成为匀速直播间 GIF。")
    解析器.add_argument("--frames-dir", required=True, help="逐帧图片目录")
    解析器.add_argument("--output", required=True, help="输出 GIF 路径")
    解析器.add_argument("--duration-ms", type=int, default=800, help="每帧时长，默认 800ms")
    解析器.add_argument("--loop", type=int, default=0, help="循环次数，0 表示无限循环")
    解析器.add_argument(
        "--transparent",
        choices=["auto", "yes", "no"],
        default="auto",
        help="透明处理方式，默认自动判断",
    )
    解析器.add_argument("--overwrite", action="store_true", help="允许覆盖已有 GIF")
    return 解析器.parse_args()


def 自然排序(路径: Path) -> list[object]:
    """按数字大小排序 1.png、2.png、10.png。"""
    return [int(片段) if 片段.isdigit() else 片段.lower() for 片段 in re.split(r"(\d+)", 路径.name)]


def 载入帧(目录: Path) -> list[Image.Image]:
    """载入目录内全部 PNG 帧，并确保尺寸一致。"""
    路径列表 = sorted(目录.glob("*.png"), key=自然排序)
    if not 路径列表:
        raise SystemExit(f"目录中没有 PNG 帧：{目录}")

    帧列表 = [Image.open(路径).convert("RGBA") for 路径 in 路径列表]
    尺寸 = 帧列表[0].size
    if any(帧.size != 尺寸 for 帧 in 帧列表):
        raise SystemExit("所有帧必须尺寸一致。")
    return 帧列表


def 转透明调色帧(帧: Image.Image) -> Image.Image:
    """保留彩色调色板，并单独预留透明索引 255。"""
    alpha = np.asarray(帧.getchannel("A"))
    调色图 = 帧.convert("RGB").quantize(
        colors=255,
        method=Image.Quantize.MEDIANCUT,
        dither=Image.Dither.NONE,
    )
    调色数据 = np.asarray(调色图).copy()
    调色数据[alpha < 128] = 255
    调色图.putdata(调色数据.ravel().tolist())

    调色板 = 调色图.getpalette() or []
    if len(调色板) < 768:
        调色板 = 调色板 + [0] * (768 - len(调色板))
    调色板[255 * 3 : 255 * 3 + 3] = [0, 0, 0]
    调色图.putpalette(调色板)
    return 调色图


def 主程序() -> None:
    """根据帧目录生成 GIF 并进行基础回读校验。"""
    参数 = 解析参数()
    帧目录 = Path(参数.frames_dir).expanduser().resolve()
    输出路径 = Path(参数.output).expanduser().resolve()
    if not 帧目录.is_dir():
        raise SystemExit(f"帧目录不存在：{帧目录}")
    if 输出路径.exists() and not 参数.overwrite:
        raise SystemExit(f"输出文件已存在：{输出路径}\n如需覆盖，请添加 --overwrite。")
    if 参数.duration_ms < 20:
        raise SystemExit("每帧时长必须至少为 20ms。")
    输出路径.parent.mkdir(parents=True, exist_ok=True)

    帧列表 = 载入帧(帧目录)
    有透明 = any(
        (np.asarray(帧.getchannel("A")) < 255).any()
        for 帧 in 帧列表
    )
    if 参数.transparent == "yes" and not 有透明:
        raise SystemExit("要求透明 GIF，但输入帧没有透明像素。")
    使用透明 = 参数.transparent == "yes" or (参数.transparent == "auto" and 有透明)

    if 使用透明:
        调色帧 = [转透明调色帧(帧) for 帧 in 帧列表]
        保存参数 = {
            "transparency": 255,
            "background": 255,
        }
    else:
        调色帧 = [
            帧.convert("RGB").quantize(
                colors=256,
                method=Image.Quantize.MEDIANCUT,
                dither=Image.Dither.NONE,
            )
            for 帧 in 帧列表
        ]
        保存参数 = {}

    调色帧[0].save(
        输出路径,
        save_all=True,
        append_images=调色帧[1:],
        duration=参数.duration_ms,
        loop=参数.loop,
        disposal=2,
        optimize=True,
        **保存参数,
    )

    with Image.open(输出路径) as 校验图:
        if 校验图.n_frames != len(帧列表):
            raise SystemExit(f"输出帧数异常：{校验图.n_frames}，预期 {len(帧列表)}。")
        for 序号 in range(校验图.n_frames):
            校验图.seek(序号)
            if int(校验图.info.get("duration", 0)) != 参数.duration_ms:
                raise SystemExit(f"第 {序号 + 1} 帧时长异常。")

    print(f"已生成 GIF：{输出路径}")
    print(f"帧数：{len(帧列表)}，每帧：{参数.duration_ms}ms，透明：{'是' if 使用透明 else '否'}")


if __name__ == "__main__":
    主程序()
