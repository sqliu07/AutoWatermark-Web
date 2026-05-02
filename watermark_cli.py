#!/usr/bin/env python3
"""AutoWatermark CLI — 本地批量水印处理工具。

用法:
    python watermark_cli.py [选项] <图片1> [图片2 ...]

示例:
    # 单张图片，默认样式 1，输出到当前目录
    python watermark_cli.py photo.jpg

    # 多张图片，指定样式
    python watermark_cli.py --style 1 3 photo1.jpg photo2.jpg

    # 所有样式都生成一份，输出到指定目录
    python watermark_cli.py --style all -o ./output *.jpg

    # 列出可用样式
    python watermark_cli.py --list
"""

import argparse
import glob
import os
import shutil
import sys
import time
from pathlib import Path

# 确保项目根目录在 sys.path 中
_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from constants import CommonConstants
from errors import WatermarkError
from process import process_image
from services.i18n import get_error_message
from services.watermark_styles import (
    get_style,
    list_enabled_styles,
    load_watermark_styles,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="watermark_cli",
        description="AutoWatermark 本地批量水印处理工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "images",
        nargs="*",
        metavar="IMAGE",
        help="输入图片路径（支持通配符，如 *.jpg）",
    )
    parser.add_argument(
        "-s", "--style",
        nargs="+",
        default=["1"],
        metavar="ID",
        help="水印样式 ID（可指定多个，如 -s 1 3 5；-s all 生成所有样式）。默认: 1",
    )
    parser.add_argument(
        "-o", "--output",
        default=".",
        metavar="DIR",
        help="输出目录。默认: 当前目录",
    )
    parser.add_argument(
        "-q", "--quality",
        choices=["high", "medium", "low"],
        default="high",
        help="输出质量。默认: high",
    )
    parser.add_argument(
        "--logo",
        choices=["xiaomi", "leica"],
        default="xiaomi",
        help="小米设备 Logo 偏好。默认: xiaomi",
    )
    parser.add_argument(
        "--lang",
        choices=["zh", "en"],
        default="zh",
        help="错误消息语言。默认: zh",
    )
    parser.add_argument(
        "-l", "--list",
        action="store_true",
        dest="list_styles",
        help="列出所有可用的水印样式",
    )
    return parser


def _resolve_images(patterns: list[str]) -> list[str]:
    """展开通配符并验证文件存在。"""
    result = []
    for pattern in patterns:
        expanded = glob.glob(pattern)
        if not expanded:
            # 可能是精确路径而非通配符
            if os.path.isfile(pattern):
                result.append(os.path.abspath(pattern))
            else:
                print(f"  警告: 未找到 '{pattern}'，跳过", file=sys.stderr)
        else:
            for p in expanded:
                if os.path.isfile(p):
                    result.append(os.path.abspath(p))
    return result


def _parse_style_ids(raw: list[str], config: dict) -> list[int]:
    """解析样式参数，支持 'all' 和多个 ID。"""
    if len(raw) == 1 and raw[0].lower() == "all":
        return [s["style_id"] for s in list_enabled_styles(config)]

    ids = []
    for item in raw:
        try:
            sid = int(item)
        except ValueError:
            print(f"  错误: 无效的样式 ID '{item}'", file=sys.stderr)
            sys.exit(1)
        if not get_style(config, sid):
            print(f"  错误: 样式 {sid} 不存在", file=sys.stderr)
            sys.exit(1)
        ids.append(sid)
    return ids


def _print_styles(config: dict) -> None:
    """打印所有可用样式。"""
    styles = list_enabled_styles(config)
    print(f"\n{'ID':<5} {'代码':<6} {'名称':<12} {'布局':<15}")
    print("-" * 40)
    for s in styles:
        sid = s["style_id"]
        code = s["display_code"]
        label = s["label_zh"]
        layout = s["layout"]
        print(f"{sid:<5} {code:<6} {label:<12} {layout:<15}")
    print()


def _process_single(
    image_path: str,
    style_id: int,
    output_dir: str,
    quality: str,
    logo: str,
    lang: str,
    style_config: dict,
) -> tuple[bool, str]:
    """处理单张图片的单个样式，返回 (成功, 输出路径)。"""
    quality_map = CommonConstants.IMAGE_QUALITY_MAP
    image_quality = quality_map.get(quality, quality_map["high"])

    try:
        result = process_image(
            image_path,
            lang=lang,
            watermark_type=style_id,
            image_quality=image_quality,
            logo_preference=logo,
            style_config=style_config,
        )
    except WatermarkError as err:
        msg = get_error_message(err.get_message_key(), lang) or str(err)
        return False, msg
    except Exception as exc:
        return False, str(exc)

    if not result.success:
        return False, "处理失败"

    # process_image 在输入文件同目录生成 {name}_watermark.{ext}
    src_dir = os.path.dirname(image_path)
    name, ext = os.path.splitext(os.path.basename(image_path))
    generated = os.path.join(src_dir, f"{name}_watermark{ext}")

    if not os.path.exists(generated):
        return False, "输出文件未生成"

    # 确定最终文件名
    if len(style_config.get("_requested_style_ids", [])) > 1:
        out_name = f"{name}_watermark_s{style_id}{ext}"
    else:
        out_name = f"{name}_watermark{ext}"

    dest = os.path.join(output_dir, out_name)

    # 如果源和目标在同一目录且同名，不需要移动
    if os.path.abspath(generated) == os.path.abspath(dest):
        return True, dest

    shutil.move(generated, dest)
    return True, dest


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    # 加载样式配置
    try:
        style_config = load_watermark_styles(CommonConstants.WATERMARK_STYLE_CONFIG_PATH)
    except Exception as exc:
        print(f"错误: 无法加载样式配置 — {exc}", file=sys.stderr)
        sys.exit(1)

    if args.list_styles:
        _print_styles(style_config)
        return

    if not args.images:
        parser.error("至少需要一个输入图片文件")

    # 解析样式 ID
    style_ids = _parse_style_ids(args.style, style_config)
    style_config["_requested_style_ids"] = style_ids

    # 解析图片
    images = _resolve_images(args.images)
    if not images:
        print("错误: 没有找到有效的输入图片", file=sys.stderr)
        sys.exit(1)

    # 准备输出目录
    output_dir = os.path.abspath(args.output)
    os.makedirs(output_dir, exist_ok=True)

    total_tasks = len(images) * len(style_ids)
    print(f"\n处理 {len(images)} 张图片 × {len(style_ids)} 种样式，共 {total_tasks} 个任务")
    print(f"输出目录: {output_dir}\n")

    succeeded = 0
    failed = 0
    start_all = time.time()

    for img_idx, image_path in enumerate(images, 1):
        img_name = os.path.basename(image_path)
        for sid in style_ids:
            style = get_style(style_config, sid)
            style_label = style["label_zh"] if style else str(sid)
            task_no = (img_idx - 1) * len(style_ids) + style_ids.index(sid) + 1
            print(f"  [{task_no}/{total_tasks}] {img_name} → 样式 {sid} ({style_label}) ... ", end="", flush=True)

            start = time.time()
            ok, info = _process_single(
                image_path, sid, output_dir, args.quality, args.logo, args.lang, style_config,
            )
            elapsed = time.time() - start

            if ok:
                succeeded += 1
                out_name = os.path.basename(info)
                print(f"完成 ({elapsed:.1f}s) → {out_name}")
            else:
                failed += 1
                print(f"失败 — {info}")

    elapsed_all = time.time() - start_all
    print(f"\n完成: {succeeded} 成功, {failed} 失败, 耗时 {elapsed_all:.1f}s")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
