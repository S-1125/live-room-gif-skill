#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


def 解析参数() -> argparse.Namespace:
    """读取命令行参数。"""
    解析器 = argparse.ArgumentParser(description="检查直播间 GIF 的尺寸、帧节奏、透明和变化情况。")
    解析器.add_argument("gif", help="待检查的 GIF 文件")
    解析器.add_argument("--json-out", help="可选：保存中文检查摘要的 JSON 路径")
    return 解析器.parse_args()


def 读取帧序列(路径: Path) -> tuple[list[np.ndarray], list[int], dict[str, Any]]:
    """逐帧转换为 RGBA，并收集时长与容器信息。"""
    帧列表: list[np.ndarray] = []
    时长列表: list[int] = []
    with Image.open(路径) as 图像:
        容器信息 = {
            "尺寸": list(图像.size),
            "帧数": int(图像.n_frames),
            "循环": 图像.info.get("loop"),
            "透明索引": 图像.info.get("transparency"),
        }
        for 序号 in range(图像.n_frames):
            图像.seek(序号)
            时长列表.append(int(图像.info.get("duration", 0)))
            帧列表.append(np.asarray(图像.convert("RGBA")))
    return 帧列表, 时长列表, 容器信息


def 计算变化(current: np.ndarray, previous: np.ndarray) -> dict[str, Any]:
    """计算当前帧相对前一帧的平均差和显著变化区域。"""
    差值 = np.abs(current.astype(np.int16) - previous.astype(np.int16))
    显著变化 = 差值.max(axis=2) > 12
    区域 = None
    if 显著变化.any():
        ys, xs = np.where(显著变化)
        区域 = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]
    return {
        "平均像素差": round(float(差值.mean()), 4),
        "显著变化像素占比": round(float(显著变化.mean()), 6),
        "变化区域": 区域,
    }


def 检查(路径: Path) -> dict[str, Any]:
    """生成可复核的 GIF 技术检查报告。"""
    帧列表, 时长列表, 容器信息 = 读取帧序列(路径)
    逐帧: list[dict[str, Any]] = []
    warnings: list[str] = []

    for 序号, 帧 in enumerate(帧列表):
        alpha = 帧[:, :, 3]
        可见 = alpha > 16
        可见像素 = 帧[可见][:, :3]
        亮度均值 = float(可见像素.mean()) if len(可见像素) else 0.0
        变化信息 = None if 序号 == 0 else 计算变化(帧, 帧列表[序号 - 1])
        逐帧.append(
            {
                "帧序号": 序号 + 1,
                "时长毫秒": 时长列表[序号],
                "透明像素占比": round(float((alpha == 0).mean()), 6),
                "可见亮度均值": round(亮度均值, 4),
                "相对前帧变化": 变化信息,
            }
        )

    if len(set(时长列表)) > 1:
        warnings.append("各帧时长不一致，动画节奏可能不稳定。")
    if 容器信息["循环"] is None:
        warnings.append("未检测到循环标记，播放器可能只播放一次。")
    if len(帧列表) == 1:
        warnings.append("文件只有一帧，不是动态图。")
    if any(项["透明像素占比"] == 1 for 项 in 逐帧):
        warnings.append("存在全透明帧。")
    if any(项["可见亮度均值"] < 2 for 项 in 逐帧):
        warnings.append("存在接近全黑的可见帧，可能是调色板或透明索引错误。")

    变化值 = [
        项["相对前帧变化"]["显著变化像素占比"]
        for 项 in 逐帧[1:]
        if 项["相对前帧变化"] is not None
    ]
    if len(帧列表) > 1 and 变化值 and max(变化值) <= 1e-8:
        warnings.append("相邻帧没有可见变化，动画可能静止。")

    报告 = {
        "文件": str(路径),
        "文件大小字节": 路径.stat().st_size,
        **容器信息,
        "时长序列毫秒": 时长列表,
        "总时长毫秒": sum(时长列表),
        "逐帧": 逐帧,
        "警告": warnings,
    }
    return 报告


def 主程序() -> None:
    """执行检查并输出中文摘要。"""
    参数 = 解析参数()
    路径 = Path(参数.gif).expanduser().resolve()
    if not 路径.exists():
        raise SystemExit(f"GIF 不存在：{路径}")

    报告 = 检查(路径)
    if 参数.json_out:
        输出路径 = Path(参数.json_out).expanduser().resolve()
        输出路径.parent.mkdir(parents=True, exist_ok=True)
        输出路径.write_text(
            json.dumps(报告, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    print(f"尺寸：{报告['尺寸'][0]}x{报告['尺寸'][1]}")
    print(f"帧数：{报告['帧数']}")
    print(f"总时长：{报告['总时长毫秒']}ms")
    print(f"循环：{报告['循环']}")
    print(f"透明索引：{报告['透明索引']}")
    if 报告["警告"]:
        print("警告：")
        for 警告 in 报告["警告"]:
            print(f"- {警告}")
    else:
        print("未发现基础结构问题。")


if __name__ == "__main__":
    主程序()
