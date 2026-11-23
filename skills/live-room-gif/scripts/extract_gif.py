#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image


def 解析参数() -> argparse.Namespace:
    """读取命令行参数。"""
    解析器 = argparse.ArgumentParser(description="把参考 GIF 拆成透明 PNG 帧并保存帧信息。")
    解析器.add_argument("gif", help="参考 GIF 文件")
    解析器.add_argument("--output-dir", required=True, help="逐帧素材输出目录")
    解析器.add_argument("--overwrite", action="store_true", help="允许覆盖非空输出目录")
    return 解析器.parse_args()


def 主程序() -> None:
    """执行拆帧并写入中文元数据。"""
    参数 = 解析参数()
    gif路径 = Path(参数.gif).expanduser().resolve()
    输出目录 = Path(参数.output_dir).expanduser().resolve()
    if not gif路径.exists():
        raise SystemExit(f"GIF 不存在：{gif路径}")
    if 输出目录.exists() and any(输出目录.iterdir()) and not 参数.overwrite:
        raise SystemExit(f"输出目录非空：{输出目录}\n如需覆盖，请添加 --overwrite。")
    输出目录.mkdir(parents=True, exist_ok=True)

    帧信息: list[dict[str, object]] = []
    with Image.open(gif路径) as 图像:
        尺寸 = list(图像.size)
        循环 = 图像.info.get("loop")
        透明索引 = 图像.info.get("transparency")
        for 序号 in range(图像.n_frames):
            图像.seek(序号)
            时长 = int(图像.info.get("duration", 0))
            帧路径 = 输出目录 / f"{序号 + 1:04d}.png"
            图像.convert("RGBA").save(帧路径, format="PNG")
            帧信息.append(
                {
                    "帧序号": 序号 + 1,
                    "文件": 帧路径.name,
                    "时长毫秒": 时长,
                }
            )

    元数据 = {
        "源文件": str(gif路径),
        "尺寸": 尺寸,
        "帧数": len(帧信息),
        "循环": 循环,
        "透明索引": 透明索引,
        "总时长毫秒": sum(int(项["时长毫秒"]) for 项 in 帧信息),
        "帧": 帧信息,
    }
    (输出目录 / "帧信息.json").write_text(
        json.dumps(元数据, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"已拆出 {len(帧信息)} 帧：{输出目录}")
    print(f"帧信息：{输出目录 / '帧信息.json'}")


if __name__ == "__main__":
    主程序()
