#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import zipfile
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from audit_gif import 检查 as 检查GIF
from build_gif import 转透明调色帧


默认字体候选 = [
    Path("/Users/sunyao/Library/Fonts/MiSans-Semibold.ttf"),
    Path("/System/Library/Fonts/Hiragino Sans GB.ttc"),
    Path("/System/Library/Fonts/STHeiti Medium.ttc"),
]


def 解析颜色(值: str) -> tuple[int, int, int, int]:
    """解析 #RRGGBB 或 #RRGGBBAA。"""
    文本 = 值.strip().lstrip("#")
    if len(文本) == 6:
        文本 += "FF"
    if len(文本) != 8 or not re.fullmatch(r"[0-9a-fA-F]{8}", 文本):
        raise SystemExit(f"颜色格式错误：{值}")
    return tuple(int(文本[i : i + 2], 16) for i in range(0, 8, 2))


def 自然排序(路径: Path) -> list[object]:
    """按数字大小排序逐帧或商品文件。"""
    return [int(片段) if 片段.isdigit() else 片段.lower() for 片段 in re.split(r"(\d+)", 路径.name)]


def 解析字体(路径值: str | None) -> Path:
    """解析指定字体，未指定时使用本机候选字体。"""
    if 路径值:
        路径 = Path(路径值).expanduser().resolve()
        if not 路径.exists():
            raise SystemExit(f"字体不存在：{路径}")
        return 路径

    路径 = next((候选 for 候选 in 默认字体候选 if 候选.exists()), None)
    if 路径 is None:
        raise SystemExit("未找到可用中文字体，请使用 --font 指定。")
    return 路径


def 准备输出目录(路径: Path, 覆盖: bool) -> None:
    """避免无意覆盖已有逐帧和成品。"""
    if 路径.exists() and any(路径.iterdir()) and not 覆盖:
        raise SystemExit(f"输出目录非空：{路径}\n如需覆盖，请添加 --overwrite。")
    if 路径.exists() and 覆盖:
        shutil.rmtree(路径)
    路径.mkdir(parents=True)


def 圆角蒙版(尺寸: tuple[int, int], 半径: int) -> Image.Image:
    """生成圆角矩形蒙版。"""
    蒙版 = Image.new("L", 尺寸, 0)
    ImageDraw.Draw(蒙版).rounded_rectangle(
        (0, 0, 尺寸[0] - 1, 尺寸[1] - 1),
        radius=半径,
        fill=255,
    )
    return 蒙版


def 加阴影(
    画布: Image.Image,
    框: tuple[int, int, int, int],
    半径: int,
    模糊: float,
    颜色: tuple[int, int, int, int],
) -> None:
    """绘制柔和阴影。"""
    阴影 = Image.new("RGBA", 画布.size, (0, 0, 0, 0))
    ImageDraw.Draw(阴影).rounded_rectangle(框, radius=半径, fill=颜色)
    画布.alpha_composite(阴影.filter(ImageFilter.GaussianBlur(模糊)))


def 绘制重复条带(
    画布: Image.Image,
    条带: Image.Image,
    周期: int,
    偏移: int,
    顶部: int,
) -> None:
    """在透明画布上铺满周期条带。"""
    起始 = math.floor((-偏移 - 条带.width) / 周期) - 1
    结束 = math.ceil((画布.width - 偏移) / 周期) + 1
    for 序号 in range(起始, 结束 + 1):
        画布.alpha_composite(条带, (偏移 + 序号 * 周期, 顶部))


def 边缘渐隐(内容: Image.Image, 渐隐宽: int) -> Image.Image:
    """在左右边缘做透明渐隐，避免生硬截断。"""
    if 渐隐宽 <= 0:
        return 内容
    alpha = np.asarray(内容.getchannel("A")).astype(np.float32)
    x轴 = np.arange(内容.width, dtype=np.float32)
    左侧 = np.clip(x轴 / 渐隐宽, 0.0, 1.0)
    右侧 = np.clip((内容.width - 1 - x轴) / 渐隐宽, 0.0, 1.0)
    alpha *= np.minimum(左侧, 右侧)[None, :]
    结果 = 内容.copy()
    结果.putalpha(Image.fromarray(alpha.astype(np.uint8), "L"))
    return 结果


def 读取文本(参数: argparse.Namespace) -> str:
    """从命令行或 UTF-8 文件读取原始文本。"""
    if 参数.text_file:
        文本 = Path(参数.text_file).expanduser().read_text(encoding="utf-8").strip()
    else:
        文本 = 参数.text
    if not 文本:
        raise SystemExit("文本不能为空。")
    return 文本


def 创建文本条带(
    文本: str,
    字体路径: Path,
    字号: int,
    高度: int,
    间隔像素: int,
    位移像素: int,
    文字颜色: tuple[int, int, int, int],
    描边颜色: tuple[int, int, int, int],
    描边宽度: int,
    阴影模糊: float,
) -> tuple[Image.Image, int]:
    """生成只有文字、描边和阴影的透明周期条带。"""
    字体 = ImageFont.truetype(str(字体路径), 字号)
    测量图 = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    测量 = ImageDraw.Draw(测量图)
    边界 = 测量.textbbox((0, 0), 文本, font=字体, stroke_width=描边宽度)
    文字宽 = 边界[2] - 边界[0]
    原始周期 = 文字宽 + 间隔像素
    周期 = math.ceil(原始周期 / 位移像素) * 位移像素

    条带 = Image.new("RGBA", (周期, 高度), (0, 0, 0, 0))
    左 = 0
    上 = round((高度 - (边界[3] - 边界[1])) / 2 - 边界[1])

    阴影 = Image.new("RGBA", 条带.size, (0, 0, 0, 0))
    阴影绘制 = ImageDraw.Draw(阴影)
    阴影绘制.text(
        (左 + 2, 上 + 4),
        文本,
        font=字体,
        fill=(126, 67, 61, 90),
        stroke_width=描边宽度,
        stroke_fill=(126, 67, 61, 45),
    )
    条带.alpha_composite(阴影.filter(ImageFilter.GaussianBlur(阴影模糊)))

    绘制 = ImageDraw.Draw(条带)
    绘制.text(
        (左, 上),
        文本,
        font=字体,
        fill=文字颜色,
        stroke_width=描边宽度,
        stroke_fill=描边颜色,
    )
    return 条带, 周期


def 生成文本帧(
    参数: argparse.Namespace,
    帧目录: Path,
) -> tuple[int, list[Path]]:
    """生成无底座的纯文本跑马灯帧。"""
    文本 = 读取文本(参数)
    字体 = 解析字体(参数.font)
    条带, 周期 = 创建文本条带(
        文本,
        字体,
        参数.font_size,
        参数.height,
        参数.gap_px,
        参数.step_px,
        解析颜色(参数.text_color),
        解析颜色(参数.stroke_color),
        参数.stroke_width,
        参数.shadow_blur,
    )
    帧数 = 周期 // 参数.step_px
    关键序号 = {0, 帧数 // 5, 帧数 * 2 // 5, 帧数 * 3 // 5, 帧数 * 4 // 5, 帧数 - 1}
    关键帧: list[Path] = []

    for 序号 in range(帧数):
        画布 = Image.new("RGBA", (参数.width, 参数.height), (0, 0, 0, 0))
        条带层 = Image.new("RGBA", 画布.size, (0, 0, 0, 0))
        偏移 = -周期 + 序号 * 参数.step_px
        绘制重复条带(条带层, 条带, 周期, 偏移, 0)
        画布.alpha_composite(边缘渐隐(条带层, 参数.edge_fade_px))
        路径 = 帧目录 / f"{序号 + 1:04d}.png"
        画布.save(路径)
        if 序号 in 关键序号:
            关键帧.append(路径)
    return 帧数, 关键帧


def 解析裁切框(值: Iterable[str]) -> list[tuple[int, int, int, int]]:
    """解析 x0,y0,x1,y1 格式的裁切框。"""
    结果: list[tuple[int, int, int, int]] = []
    for 项 in 值:
        分量 = [int(部分.strip()) for 部分 in 项.split(",")]
        if len(分量) != 4:
            raise SystemExit(f"裁切框必须包含四个整数：{项}")
        结果.append(tuple(分量))
    return 结果


def 载入商品图(参数: argparse.Namespace) -> list[Image.Image]:
    """从拼图和裁切框或图片目录读取商品素材。"""
    if 参数.collage:
        if not 参数.crop_box:
            raise SystemExit("使用 --collage 时必须提供至少一个 --crop-box。")
        拼图 = Image.open(参数.collage).convert("RGB")
        裁切框 = 解析裁切框(参数.crop_box)
        return [拼图.crop(框) for 框 in 裁切框]

    if 参数.images_dir:
        目录 = Path(参数.images_dir).expanduser().resolve()
        路径列表 = sorted(
            [
                路径
                for 路径 in 目录.iterdir()
                if 路径.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
            ],
            key=自然排序,
        )
        if not 路径列表:
            raise SystemExit(f"图片目录为空：{目录}")
        return [Image.open(路径).convert("RGB") for 路径 in 路径列表]

    raise SystemExit("图片模式必须提供 --collage 与 --crop-box，或提供 --images-dir。")


def 创建商品卡(
    原图: Image.Image,
    宽: int,
    高: int,
    使用边框: bool,
    边框颜色: tuple[int, int, int, int],
    描边颜色: tuple[int, int, int, int],
) -> Image.Image:
    """生成单个商品卡；边框只属于商品本身，不创建整排底板。"""
    图片 = ImageOps.fit(原图, (宽, 高), method=Image.Resampling.LANCZOS).convert("RGBA")
    图片.putalpha(圆角蒙版((宽, 高), 9))
    if not 使用边框:
        return 图片

    内边距 = 8
    卡片 = Image.new("RGBA", (宽 + 内边距 * 2, 高 + 内边距 * 2), (0, 0, 0, 0))
    加阴影(卡片, (4, 8, 宽 + 11, 高 + 15), 18, 5, (124, 72, 84, 55))
    绘制 = ImageDraw.Draw(卡片)
    绘制.rounded_rectangle(
        (3, 3, 宽 + 12, 高 + 11),
        radius=17,
        fill=边框颜色,
        outline=描边颜色,
        width=2,
    )
    卡片.alpha_composite(图片, (内边距, 6))
    return 卡片


def 生成图片帧(
    参数: argparse.Namespace,
    帧目录: Path,
) -> tuple[int, list[Path]]:
    """生成无整排底板、保留可选单图边框的商品跑马灯帧。"""
    商品列表 = 载入商品图(参数)
    卡片列表 = [
        创建商品卡(
            商品,
            参数.item_width,
            参数.item_height,
            not 参数.no_border,
            解析颜色(参数.border_color),
            解析颜色(参数.outline_color),
        )
        for 商品 in 商品列表
    ]
    卡片宽 = 卡片列表[0].width
    卡片高 = 卡片列表[0].height
    原始周期 = len(卡片列表) * (卡片宽 + 参数.gap_px)
    周期 = math.ceil(原始周期 / 参数.step_px) * 参数.step_px
    条带 = Image.new("RGBA", (周期, 卡片高), (0, 0, 0, 0))

    for 序号, 卡片 in enumerate(卡片列表):
        条带.alpha_composite(卡片, (序号 * (卡片宽 + 参数.gap_px), 0))

    画布高 = max(参数.height, 卡片高 + 20)
    顶部 = (画布高 - 卡片高) // 2
    帧数 = 周期 // 参数.step_px
    关键序号 = {0, 帧数 // 5, 帧数 * 2 // 5, 帧数 * 3 // 5, 帧数 * 4 // 5, 帧数 - 1}
    关键帧: list[Path] = []

    for 序号 in range(帧数):
        画布 = Image.new("RGBA", (参数.width, 画布高), (0, 0, 0, 0))
        内容层 = Image.new("RGBA", 画布.size, (0, 0, 0, 0))
        偏移 = -周期 + 序号 * 参数.step_px
        绘制重复条带(内容层, 条带, 周期, 偏移, 顶部)
        画布.alpha_composite(边缘渐隐(内容层, 参数.edge_fade_px))
        路径 = 帧目录 / f"{序号 + 1:04d}.png"
        画布.save(路径)
        if 序号 in 关键序号:
            关键帧.append(路径)
    return 帧数, 关键帧


def 生成棋盘预览(帧路径: Path, 目标路径: Path) -> None:
    """把一帧叠加到棋盘格上检查透明背景。"""
    帧 = Image.open(帧路径).convert("RGBA")
    棋盘 = Image.new("RGB", 帧.size, (255, 255, 255))
    绘制 = ImageDraw.Draw(棋盘)
    for y in range(0, 帧.height, 24):
        for x in range(0, 帧.width, 24):
            if (x // 24 + y // 24) % 2:
                绘制.rectangle((x, y, x + 23, y + 23), fill=(226, 226, 226))
    棋盘.paste(帧, (0, 0), 帧)
    棋盘.save(目标路径, format="PNG")


def 生成关键帧预览(路径列表: list[Path], 目标路径: Path, 列数: int = 3) -> None:
    """生成关键帧审核拼图。"""
    缩略宽 = min(380, max(220, 1140 // 列数))
    间距 = 12
    首帧 = Image.open(路径列表[0]).convert("RGBA")
    缩略高 = round(首帧.height * 缩略宽 / 首帧.width)
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
        缩略 = Image.open(路径).convert("RGBA").resize(
            (缩略宽, 缩略高),
            Image.Resampling.LANCZOS,
        )
        x = 间距 + 列 * (缩略宽 + 间距)
        y = 间距 + 行 * (缩略高 + 间距)
        画布.paste(缩略, (x, y), 缩略)
    画布.save(目标路径, quality=93, subsampling=0)


def 保存透明GIF(帧目录: Path, 目标路径: Path, 时长毫秒: int) -> None:
    """把透明 PNG 帧合成为无限循环 GIF。"""
    路径列表 = sorted(帧目录.glob("*.png"), key=自然排序)
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


def 添加文本模式参数(解析器: argparse.ArgumentParser) -> None:
    """添加纯文本跑马灯参数。"""
    解析器.add_argument("--text", default="", help="单行原始文本")
    解析器.add_argument("--text-file", help="从 UTF-8 文件读取文本")
    解析器.add_argument("--font", help="中文字体路径")
    解析器.add_argument("--font-size", type=int, default=46)
    解析器.add_argument("--text-color", default="#7C3D3A")
    解析器.add_argument("--stroke-color", default="#FFFFFF")
    解析器.add_argument("--stroke-width", type=int, default=3)
    解析器.add_argument("--shadow-blur", type=float, default=2.2)
    解析器.add_argument("--gap-px", type=int, default=200, help="文案循环间隔")


def 添加图片模式参数(解析器: argparse.ArgumentParser) -> None:
    """添加图片跑马灯参数。"""
    解析器.add_argument("--collage", help="商品拼图路径")
    解析器.add_argument("--crop-box", action="append", help="裁切框 x0,y0,x1,y1，可重复")
    解析器.add_argument("--images-dir", help="已拆分商品图目录")
    解析器.add_argument("--item-width", type=int, default=190)
    解析器.add_argument("--item-height", type=int, default=240)
    解析器.add_argument("--gap-px", type=int, default=14, help="商品卡间距")
    解析器.add_argument("--no-border", action="store_true", help="关闭单图边框")
    解析器.add_argument("--border-color", default="#FFFFFF")
    解析器.add_argument("--outline-color", default="#F1D6DD")


def 添加公共参数(解析器: argparse.ArgumentParser) -> None:
    """添加两种模式共用的尺寸、节奏和输出参数。"""
    解析器.add_argument("--output-dir", required=True, help="成品与逐帧输出目录")
    解析器.add_argument("--name", default="跑马灯", help="成品文件名前缀")
    解析器.add_argument("--width", type=int, default=1080)
    解析器.add_argument("--height", type=int, default=100)
    解析器.add_argument("--duration-ms", type=int, default=80)
    解析器.add_argument("--step-px", type=int, default=10, help="每帧从左向右位移")
    解析器.add_argument("--edge-fade-px", type=int, default=28)
    解析器.add_argument("--overwrite", action="store_true")


def 解析参数() -> argparse.Namespace:
    """解析子命令参数。"""
    解析器 = argparse.ArgumentParser(description="生成单行、无缝、从左到右的透明跑马灯 GIF。")
    子命令 = 解析器.add_subparsers(dest="mode", required=True)

    文本 = 子命令.add_parser("text", help="纯文本跑马灯；默认无底座")
    添加公共参数(文本)
    添加文本模式参数(文本)

    图片 = 子命令.add_parser("images", help="图片跑马灯；默认单图边框，无整排底板")
    添加公共参数(图片)
    图片.set_defaults(height=276, edge_fade_px=24)
    添加图片模式参数(图片)

    return 解析器.parse_args()


def 主程序() -> None:
    """生成帧、透明 GIF、审核预览、压缩包和审计报告。"""
    参数 = 解析参数()
    if 参数.duration_ms < 20:
        raise SystemExit("每帧时长必须至少为 20ms。")
    if 参数.step_px < 1:
        raise SystemExit("每帧位移必须大于 0。")

    输出目录 = Path(参数.output_dir).expanduser().resolve()
    准备输出目录(输出目录, 参数.overwrite)
    帧目录 = 输出目录 / "静态帧"
    帧目录.mkdir()

    if 参数.mode == "text":
        帧数, 关键帧 = 生成文本帧(参数, 帧目录)
    else:
        帧数, 关键帧 = 生成图片帧(参数, 帧目录)

    gif路径 = 输出目录 / f"{参数.name}_透明.gif"
    保存透明GIF(帧目录, gif路径, 参数.duration_ms)
    生成棋盘预览(关键帧[2], 输出目录 / "透明效果棋盘预览.png")
    生成关键帧预览(关键帧, 输出目录 / "关键帧预览.jpg")
    打包帧目录(帧目录, 输出目录 / "逐帧素材.zip")

    报告 = 检查GIF(gif路径)
    (输出目录 / "审计报告.json").write_text(
        json.dumps(报告, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if 报告["警告"]:
        raise SystemExit(f"GIF 审计发现警告：{报告['警告']}")

    print(f"模式：{参数.mode}")
    print(f"帧数：{帧数}，每帧：{参数.duration_ms}ms")
    print(f"透明 GIF：{gif路径}")
    print(f"关键帧预览：{输出目录 / '关键帧预览.jpg'}")
    print(f"逐帧素材：{输出目录 / '逐帧素材.zip'}")


if __name__ == "__main__":
    主程序()
