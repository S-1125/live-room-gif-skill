#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from scipy import ndimage


默认字体候选 = [
    Path("/Users/sunyao/Library/Fonts/MiSans-Semibold.ttf"),
    Path("/System/Library/Fonts/Hiragino Sans GB.ttc"),
    Path("/System/Library/Fonts/STHeiti Medium.ttc"),
]


def 读取JSON(路径: Path) -> Any:
    """读取 UTF-8 JSON 文件。"""
    try:
        return json.loads(路径.read_text(encoding="utf-8"))
    except FileNotFoundError as 错误:
        raise SystemExit(f"找不到文件：{路径}") from 错误
    except json.JSONDecodeError as 错误:
        raise SystemExit(f"JSON 格式错误：{路径}\n{错误}") from 错误


def 解析路径(值: str, 基准目录: Path) -> Path:
    """相对路径按配置文件所在目录解析。"""
    路径 = Path(值).expanduser()
    if not 路径.is_absolute():
        路径 = 基准目录 / 路径
    return 路径.resolve()


def 读取条目(路径: Path) -> list[dict[str, Any]]:
    """兼容顶层数组和 items 数组两种数据格式。"""
    数据 = 读取JSON(路径)
    if isinstance(数据, dict):
        数据 = 数据.get("items")
    if not isinstance(数据, list) or not 数据:
        raise SystemExit("文字数据必须是非空数组，或包含 items 数组的对象。")
    if not all(isinstance(条目, dict) for 条目 in 数据):
        raise SystemExit("文字数据中的每个条目都必须是对象。")
    return 数据


def 安全文件名(值: str) -> str:
    """清除非文件名安全字符，并限制长度。"""
    清理后 = re.sub(r'[\\/:*?"<>|\s]+', "_", 值.strip())
    清理后 = 清理后.strip("._") or "frame"
    return 清理后[:48]


def 查找字体(配置: dict[str, Any], 配置目录: Path, 命令行字体: str | None) -> Path:
    """按命令行、配置和默认候选顺序确定字体。"""
    if 命令行字体:
        字体 = Path(命令行字体).expanduser().resolve()
    elif 配置.get("font"):
        字体 = 解析路径(配置["font"], 配置目录)
    else:
        字体 = next((候选 for 候选 in 默认字体候选 if 候选.exists()), None)
        if 字体 is None:
            raise SystemExit("未找到可用中文字体，请通过 --font 指定。")

    if not 字体.exists():
        raise SystemExit(f"字体文件不存在：{字体}")
    return 字体


def 擦除亮色文字(原图: Image.Image, 区域配置: dict[str, Any]) -> Image.Image:
    """在指定区域内识别亮色文字，并用周围底色向笔画内部扩散修复。"""
    图像 = np.asarray(原图.convert("RGB")).astype(np.float32)
    高, 宽 = 图像.shape[:2]
    框 = 区域配置.get("box")
    if not isinstance(框, list) or len(框) != 4:
        raise SystemExit("擦除区域必须提供 [x0, y0, x1, y1]。")

    x0, y0, x1, y1 = map(int, 框)
    if not (0 <= x0 < x1 <= 宽 and 0 <= y0 < y1 <= 高):
        raise SystemExit(f"擦除区域越界：{框}，原图尺寸为 {宽}x{高}。")

    阈值 = int(区域配置.get("brightness_threshold", 190))
    膨胀次数 = int(区域配置.get("dilation", 8))
    迭代次数 = int(区域配置.get("iterations", 360))
    纹理强度 = float(区域配置.get("texture_std", 1.8))
    羽化半径 = float(区域配置.get("feather", 1.6))
    随机种子 = int(区域配置.get("seed", 20261119))

    局部图 = 图像[y0:y1, x0:x1]
    文字蒙版 = 局部图.min(axis=2) > 阈值
    文字蒙版 = ndimage.binary_dilation(文字蒙版, iterations=膨胀次数)

    if not 文字蒙版.any():
        return 原图.copy()

    距离索引 = ndimage.distance_transform_edt(
        文字蒙版,
        return_distances=False,
        return_indices=True,
    )
    填充图 = 局部图[tuple(距离索引)].astype(np.float32)

    for _ in range(迭代次数):
        邻域均值 = (
            np.roll(填充图, 1, axis=0)
            + np.roll(填充图, -1, axis=0)
            + np.roll(填充图, 1, axis=1)
            + np.roll(填充图, -1, axis=1)
        ) / 4.0
        填充图[文字蒙版] = 邻域均值[文字蒙版]

    if 纹理强度 > 0:
        随机数 = np.random.default_rng(随机种子)
        纹理 = 随机数.normal(0.0, 纹理强度, 填充图.shape).astype(np.float32)
        填充图[文字蒙版] = np.clip(填充图[文字蒙版] + 纹理[文字蒙版], 0.0, 255.0)

    羽化蒙版 = Image.fromarray((文字蒙版 * 255).astype(np.uint8))
    if 羽化半径 > 0:
        羽化蒙版 = 羽化蒙版.filter(ImageFilter.GaussianBlur(羽化半径))

    结果 = 原图.copy()
    结果.paste(Image.fromarray(填充图.astype(np.uint8)), (x0, y0), 羽化蒙版)
    return 结果


def 生成清空底图(原图: Image.Image, 配置: dict[str, Any]) -> Image.Image:
    """依次擦除全部配置区域，固定标题是否保留取决于区域配置。"""
    区域列表 = 配置.get("erase_regions")
    if not isinstance(区域列表, list) or not 区域列表:
        raise SystemExit("配置必须提供非空 erase_regions 数组。")

    结果 = 原图.convert("RGB").copy()
    for 区域 in 区域列表:
        if not isinstance(区域, dict):
            raise SystemExit("erase_regions 中的每一项都必须是对象。")
        结果 = 擦除亮色文字(结果, 区域)
    return 结果


def 自适应字体(
    绘制: ImageDraw.ImageDraw,
    文字: str,
    字体路径: Path,
    最大字号: int,
    最大宽度: int,
    最小字号: int,
) -> ImageFont.FreeTypeFont:
    """在不超出最大宽度时选择尽可能大的字号。"""
    if 最小字号 > 最大字号:
        raise SystemExit("文字槽位的 min_size 不能大于 max_size。")

    for 字号 in range(最大字号, 最小字号 - 1, -1):
        字体 = ImageFont.truetype(str(字体路径), 字号)
        边界 = 绘制.textbbox((0, 0), 文字, font=字体)
        if 边界[2] - 边界[0] <= 最大宽度:
            return 字体
    return ImageFont.truetype(str(字体路径), 最小字号)


def 绘制居中文字(
    绘制: ImageDraw.ImageDraw,
    中心点: tuple[int, int],
    文字: str,
    字体: ImageFont.FreeTypeFont,
    颜色: tuple[int, int, int],
) -> None:
    """按可见像素边界把文字精确放在指定中心。"""
    边界 = 绘制.textbbox((0, 0), 文字, font=字体)
    文字宽 = 边界[2] - 边界[0]
    文字高 = 边界[3] - 边界[1]
    左上 = (
        round(中心点[0] - 文字宽 / 2 - 边界[0]),
        round(中心点[1] - 文字高 / 2 - 边界[1]),
    )
    绘制.text(左上, 文字, font=字体, fill=颜色)


def 生成静态帧(
    清空底图: Image.Image,
    条目列表: list[dict[str, Any]],
    槽位列表: list[dict[str, Any]],
    字体路径: Path,
    输出目录: Path,
) -> list[Path]:
    """为每个条目生成一张保留原文写法的静态帧。"""
    输出目录.mkdir(parents=True, exist_ok=True)
    帧路径列表: list[Path] = []

    for 序号, 条目 in enumerate(条目列表, start=1):
        图像 = 清空底图.copy()
        绘制 = ImageDraw.Draw(图像)
        文件名片段: list[str] = []

        for 槽位 in 槽位列表:
            字段 = 槽位.get("field")
            if not isinstance(字段, str):
                raise SystemExit("每个文字槽位都必须提供 field。")
            文字 = str(条目.get(字段, ""))
            if not 文字:
                continue

            中心 = 槽位.get("center")
            if not isinstance(中心, list) or len(中心) != 2:
                raise SystemExit(f"槽位 {字段} 必须提供 [x, y] 中心点。")

            字体 = 自适应字体(
                绘制,
                文字,
                字体路径,
                int(槽位.get("max_size", 180)),
                int(槽位.get("max_width", 600)),
                int(槽位.get("min_size", 72)),
            )
            颜色值 = 槽位.get("fill", [255, 255, 255])
            颜色 = tuple(int(分量) for 分量 in 颜色值)
            绘制居中文字(绘制, (int(中心[0]), int(中心[1])), 文字, 字体, 颜色)
            文件名片段.append(文字)

        名称 = str(条目.get("name") or "_".join(文件名片段) or 序号)
        路径 = 输出目录 / f"{序号:02d}_{安全文件名(名称)}.png"
        图像.save(路径, format="PNG")
        帧路径列表.append(路径)

    return 帧路径列表


def 生成透明图(图像: Image.Image, 黑色阈值: int = 55) -> Image.Image:
    """把与画布边缘连通的近黑区域转为透明，保留内部深色物体。"""
    rgb = np.asarray(图像.convert("RGB"))
    深色区域 = rgb.max(axis=2) < 黑色阈值
    连通区域, _ = ndimage.label(深色区域)

    边缘标签 = np.concatenate(
        [
            连通区域[0, :],
            连通区域[-1, :],
            连通区域[:, 0],
            连通区域[:, -1],
        ]
    )
    背景标签 = np.unique(边缘标签[边缘标签 > 0])
    if not len(背景标签):
        raise SystemExit("未从画布边缘识别到黑色背景，请确认原图是黑色外底。")

    背景蒙版 = np.isin(连通区域, 背景标签)
    rgba = np.dstack([rgb, np.where(背景蒙版, 0, 255).astype(np.uint8)])
    return Image.fromarray(rgba, mode="RGBA")


def 生成透明静态帧(
    帧路径列表: list[Path],
    输出目录: Path,
    黑色阈值: int = 55,
) -> list[Path]:
    """为全部静态帧生成透明 PNG。"""
    输出目录.mkdir(parents=True, exist_ok=True)
    透明帧路径列表: list[Path] = []
    for 路径 in 帧路径列表:
        透明图 = 生成透明图(Image.open(路径).convert("RGB"), 黑色阈值)
        目标路径 = 输出目录 / 路径.name
        透明图.save(目标路径, format="PNG")
        透明帧路径列表.append(目标路径)
    return 透明帧路径列表


def 转成透明GIF调色帧(图像: Image.Image) -> Image.Image:
    """保留彩色调色板，并为透明像素单独预留索引 255。"""
    rgba = 图像.convert("RGBA")
    alpha = np.asarray(rgba.getchannel("A"))
    rgb = rgba.convert("RGB")
    调色图 = rgb.quantize(
        colors=255,
        method=Image.Quantize.MEDIANCUT,
        dither=Image.Dither.NONE,
    )

    # 必须修改原 P 模式图像的像素，不能重新创建 P 图，否则彩色调色板会丢失。
    调色数据 = np.asarray(调色图).copy()
    调色数据[alpha < 128] = 255
    调色图.putdata(调色数据.ravel().tolist())

    调色板 = 调色图.getpalette() or []
    if len(调色板) < 768:
        调色板 = 调色板 + [0] * (768 - len(调色板))
    调色板[255 * 3 : 255 * 3 + 3] = [0, 0, 0]
    调色图.putpalette(调色板)
    return 调色图


def 保存不透明GIF(帧路径列表: list[Path], 目标路径: Path, 帧时长毫秒: int) -> Path:
    """保存常规 RGB GIF。"""
    调色帧 = [
        Image.open(路径)
        .convert("RGB")
        .quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
        for 路径 in 帧路径列表
    ]
    调色帧[0].save(
        目标路径,
        save_all=True,
        append_images=调色帧[1:],
        duration=帧时长毫秒,
        loop=0,
        disposal=2,
        optimize=True,
    )
    return 目标路径


def 保存透明GIF(透明帧路径列表: list[Path], 目标路径: Path, 帧时长毫秒: int) -> Path:
    """保存带二进制透明通道的 GIF。"""
    调色帧 = [
        转成透明GIF调色帧(Image.open(路径).convert("RGBA"))
        for 路径 in 透明帧路径列表
    ]
    调色帧[0].save(
        目标路径,
        save_all=True,
        append_images=调色帧[1:],
        duration=帧时长毫秒,
        loop=0,
        disposal=2,
        optimize=True,
        transparency=255,
        background=255,
    )
    return 目标路径


def 生成棋盘预览(透明图: Image.Image, 目标路径: Path, 格子大小: int = 24) -> Path:
    """用棋盘格展示透明区域。"""
    宽, 高 = 透明图.size
    棋盘 = Image.new("RGB", (宽, 高), (255, 255, 255))
    绘制 = ImageDraw.Draw(棋盘)
    for y in range(0, 高, 格子大小):
        for x in range(0, 宽, 格子大小):
            if (x // 格子大小 + y // 格子大小) % 2:
                绘制.rectangle(
                    (x, y, x + 格子大小 - 1, y + 格子大小 - 1),
                    fill=(226, 226, 226),
                )
    棋盘.paste(透明图, (0, 0), 透明图)
    棋盘.save(目标路径, format="PNG")
    return 目标路径


def 生成帧预览(
    帧路径列表: list[Path],
    目标路径: Path,
    列数: int,
    缩略宽度: int,
    间距: int = 14,
) -> Path:
    """生成全部透明帧的缩略拼图，避免深色外底干扰透明判断。"""
    首帧 = Image.open(帧路径列表[0]).convert("RGBA")
    缩放比例 = 缩略宽度 / 首帧.width
    缩略高度 = round(首帧.height * 缩放比例)
    行数 = (len(帧路径列表) + 列数 - 1) // 列数

    拼图 = Image.new(
        "RGB",
        (
            列数 * 缩略宽度 + (列数 + 1) * 间距,
            行数 * 缩略高度 + (行数 + 1) * 间距,
        ),
        (232, 222, 209),
    )
    for 序号, 路径 in enumerate(帧路径列表):
        列 = 序号 % 列数
        行 = 序号 // 列数
        缩略图 = Image.open(路径).convert("RGBA").resize(
            (缩略宽度, 缩略高度),
            Image.Resampling.LANCZOS,
        )
        x = 间距 + 列 * (缩略宽度 + 间距)
        y = 间距 + 行 * (缩略高度 + 间距)
        拼图.paste(缩略图, (x, y), 缩略图)

    拼图.save(目标路径, quality=92, subsampling=0)
    return 目标路径


def 打包目录(目录: Path, 目标压缩包: Path) -> Path:
    """把目录压缩为 UTF-8 文件名的 ZIP。"""
    with zipfile.ZipFile(目标压缩包, "w", compression=zipfile.ZIP_DEFLATED) as 压缩包:
        for 路径 in sorted(目录.rglob("*")):
            if 路径.is_file():
                压缩包.write(路径, 目录.name / 路径.relative_to(目录))
    return 目标压缩包


def 校验静态透明帧(路径列表: list[Path]) -> dict[str, Any]:
    """确认四角透明，并确认海报中心仍为不透明内容。"""
    报告: list[dict[str, Any]] = []
    for 路径 in 路径列表:
        图像 = Image.open(路径).convert("RGBA")
        alpha = np.asarray(图像.getchannel("A"))
        if np.any(alpha[[0, 0, -1, -1], [0, -1, 0, -1]] != 0):
            raise SystemExit(f"透明帧四角未完全透明：{路径}")
        报告.append(
            {
                "文件": 路径.name,
                "尺寸": list(图像.size),
                "透明像素占比": round(float((alpha == 0).mean()), 6),
            }
        )
    return {"帧数": len(路径列表), "逐帧": 报告}


def 校验GIF(路径: Path, 预期帧数: int, 预期时长: int, 要求透明: bool) -> dict[str, Any]:
    """重新打开 GIF，检查帧数、时长、透明索引和首帧内容。"""
    with Image.open(路径) as 图像:
        时长列表: list[int] = []
        for 序号 in range(图像.n_frames):
            图像.seek(序号)
            时长列表.append(int(图像.info.get("duration", 0)))

        if 图像.n_frames != 预期帧数:
            raise SystemExit(f"GIF 帧数异常：{图像.n_frames}，预期 {预期帧数}。")
        if set(时长列表) != {预期时长}:
            raise SystemExit(f"GIF 帧时长异常：{sorted(set(时长列表))}，预期 {预期时长} 毫秒。")

        图像.seek(0)
        rgba = 图像.convert("RGBA")
        像素 = np.asarray(rgba)
        alpha = 像素[:, :, 3]
        不透明像素 = 像素[alpha > 0][:, :3]
        if not len(不透明像素) or float(不透明像素.mean()) < 2:
            raise SystemExit(f"GIF 首帧内容异常，可能被错误填成黑色：{路径}")

        if 要求透明:
            if 图像.info.get("transparency") is None:
                raise SystemExit(f"GIF 未写透明索引：{路径}")
            if np.any(alpha[[0, 0, -1, -1], [0, -1, 0, -1]] != 0):
                raise SystemExit(f"GIF 四角未透明：{路径}")

        return {
            "帧数": 图像.n_frames,
            "时长毫秒": 预期时长,
            "循环": 图像.info.get("loop"),
            "透明索引": 图像.info.get("transparency"),
            "首帧透明像素占比": round(float((alpha == 0).mean()), 6),
        }


def 准备输出目录(目录: Path, 覆盖: bool) -> None:
    """避免无意覆盖已有成品。"""
    if 目录.exists() and any(目录.iterdir()) and not 覆盖:
        raise SystemExit(f"输出目录非空：{目录}\n如需覆盖，请显式添加 --overwrite。")
    目录.mkdir(parents=True, exist_ok=True)


def 解析参数() -> argparse.Namespace:
    """读取命令行参数。"""
    解析器 = argparse.ArgumentParser(
        description="擦除海报旧文字，批量生成透明静态帧与匀速 GIF。"
    )
    解析器.add_argument("--source", required=True, help="原始海报图片路径")
    解析器.add_argument("--items", required=True, help="城市与温度数据 JSON 路径")
    解析器.add_argument("--config", required=True, help="排版与擦除配置 JSON 路径")
    解析器.add_argument("--output-dir", help="成品输出目录")
    解析器.add_argument("--font", help="覆盖配置文件中的字体路径")
    解析器.add_argument("--duration-ms", type=int, help="覆盖每帧时长")
    解析器.add_argument("--prefix", help="覆盖成品文件名前缀")
    解析器.add_argument("--overwrite", action="store_true", help="允许覆盖非空输出目录")
    return 解析器.parse_args()


def 主程序() -> None:
    """执行完整工作流并输出验证摘要。"""
    参数 = 解析参数()
    源路径 = Path(参数.source).expanduser().resolve()
    条目路径 = Path(参数.items).expanduser().resolve()
    配置路径 = Path(参数.config).expanduser().resolve()

    if not 源路径.exists():
        raise SystemExit(f"原图不存在：{源路径}")
    if not 条目路径.exists():
        raise SystemExit(f"数据文件不存在：{条目路径}")
    if not 配置路径.exists():
        raise SystemExit(f"配置文件不存在：{配置路径}")

    配置 = 读取JSON(配置路径)
    if not isinstance(配置, dict):
        raise SystemExit("配置文件顶层必须是对象。")
    条目列表 = 读取条目(条目路径)

    槽位列表 = 配置.get("slots")
    if not isinstance(槽位列表, list) or not 槽位列表:
        raise SystemExit("配置必须提供非空 slots 数组。")

    字体路径 = 查找字体(配置, 配置路径.parent, 参数.font)
    帧时长 = int(参数.duration_ms or 配置.get("duration_ms", 800))
    if 帧时长 < 20:
        raise SystemExit("帧时长必须至少为 20ms；常用值为 500、650 或 800ms。")
    前缀 = 参数.prefix or str(配置.get("prefix", 源路径.stem))
    输出目录 = (
        Path(参数.output_dir).expanduser().resolve()
        if 参数.output_dir
        else 源路径.parent / "outputs" / 安全文件名(前缀)
    )
    准备输出目录(输出目录, 参数.overwrite)

    原图 = Image.open(源路径).convert("RGB")
    清空底图 = 生成清空底图(原图, 配置)
    清空底图路径 = 输出目录 / f"{前缀}_清空文字底图.png"
    清空底图.save(清空底图路径, format="PNG")

    不透明帧目录 = 输出目录 / f"{前缀}_静态帧"
    帧路径列表 = 生成静态帧(
        清空底图,
        条目列表,
        槽位列表,
        字体路径,
        不透明帧目录,
    )

    透明帧目录 = 输出目录 / f"{前缀}_透明静态帧"
    黑色阈值 = int(配置.get("black_threshold", 55))
    透明帧路径列表 = 生成透明静态帧(帧路径列表, 透明帧目录, 黑色阈值)

    不透明GIF路径 = 保存不透明GIF(
        帧路径列表,
        输出目录 / f"{前缀}_不透明.gif",
        帧时长,
    )
    透明GIF路径 = 保存透明GIF(
        透明帧路径列表,
        输出目录 / f"{前缀}_透明.gif",
        帧时长,
    )
    棋盘预览路径 = 生成棋盘预览(
        Image.open(透明帧路径列表[0]),
        输出目录 / f"{前缀}_透明棋盘预览.png",
    )
    帧预览路径 = 生成帧预览(
        透明帧路径列表,
        输出目录 / f"{前缀}_全帧预览.jpg",
        int(配置.get("preview_columns", 5)),
        int(配置.get("thumbnail_width", 204)),
    )
    透明压缩包路径 = 打包目录(
        透明帧目录,
        输出目录 / f"{前缀}_透明静态帧.zip",
    )

    透明帧报告 = 校验静态透明帧(透明帧路径列表)
    透明GIF报告 = 校验GIF(透明GIF路径, len(条目列表), 帧时长, 要求透明=True)
    不透明GIF报告 = 校验GIF(不透明GIF路径, len(条目列表), 帧时长, 要求透明=False)

    摘要 = {
        "源图片": str(源路径),
        "条目数量": len(条目列表),
        "每帧时长毫秒": 帧时长,
        "字体": str(字体路径),
        "清空文字底图": str(清空底图路径),
        "透明帧目录": str(透明帧目录),
        "透明GIF": str(透明GIF路径),
        "不透明GIF": str(不透明GIF路径),
        "透明棋盘预览": str(棋盘预览路径),
        "全帧预览": str(帧预览路径),
        "透明静态帧压缩包": str(透明压缩包路径),
        "透明帧校验": 透明帧报告,
        "透明GIF校验": 透明GIF报告,
        "不透明GIF校验": 不透明GIF报告,
    }
    摘要路径 = 输出目录 / "生成摘要.json"
    摘要路径.write_text(
        json.dumps(摘要, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"已生成 {len(条目列表)} 帧，每帧 {帧时长}ms。")
    print(f"透明 GIF：{透明GIF路径}")
    print(f"棋盘预览：{棋盘预览路径}")
    print(f"摘要文件：{摘要路径}")


if __name__ == "__main__":
    主程序()
