import argparse
from pathlib import Path
from typing import Optional

from PIL import Image, ImageColor, ImageDraw, ImageFilter, ImageFont, ImageOps


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FONT_PATH = PROJECT_ROOT / "fonts" / "RobotoMono-Regular.ttf"
DEFAULT_BACKGROUND = "#ececec"
DEFAULT_TEXT_COLOR = "#5f5f5f"
DEFAULT_STAMP_COLOR = "#b88949"


def _fit_image(image: Image.Image, max_width: int, max_height: int) -> Image.Image:
    width_ratio = max_width / image.width
    height_ratio = max_height / image.height
    scale = min(width_ratio, height_ratio)

    if scale >= 1:
        return image.copy()

    new_size = (
        max(1, int(round(image.width * scale))),
        max(1, int(round(image.height * scale))),
    )
    return image.resize(new_size, Image.Resampling.LANCZOS)


def _load_font(font_path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(font_path), size)


def _draw_shadow(canvas: Image.Image, framed_photo: Image.Image, photo_x: int, photo_y: int, blur_radius: int) -> None:
    shadow_padding = blur_radius * 3
    shadow = Image.new(
        "RGBA",
        (
            framed_photo.width + shadow_padding * 2,
            framed_photo.height + shadow_padding * 2,
        ),
        (0, 0, 0, 0),
    )
    shadow_draw = ImageDraw.Draw(shadow)
    rect = (
        shadow_padding,
        shadow_padding,
        shadow_padding + framed_photo.width,
        shadow_padding + framed_photo.height,
    )
    shadow_draw.rectangle(rect, fill=(0, 0, 0, 85))
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur_radius))

    shadow_x = photo_x - shadow_padding + max(1, blur_radius // 2)
    shadow_y = photo_y - shadow_padding + blur_radius
    canvas.paste(shadow, (shadow_x, shadow_y), shadow)


def create_film_frame(
    input_path: str,
    output_path: str,
    caption: str,
    stamp_text: Optional[str] = None,
    font_path: Optional[str] = None,
) -> Path:
    source_path = Path(input_path)
    target_path = Path(output_path)
    resolved_font_path = Path(font_path) if font_path else DEFAULT_FONT_PATH

    if not source_path.exists():
        raise FileNotFoundError(f"Input image not found: {source_path}")
    if not resolved_font_path.exists():
        raise FileNotFoundError(f"Font not found: {resolved_font_path}")

    with Image.open(source_path) as opened_image:
        photo = opened_image.convert("RGB")

    max_photo_width = min(photo.width, 1600)
    max_photo_height = min(photo.height, 1200)
    photo = _fit_image(photo, max_photo_width, max_photo_height)

    short_side = min(photo.size)
    border_size = max(2, int(round(short_side * 0.006)))
    framed_photo = ImageOps.expand(photo, border=border_size, fill="black")

    side_margin = max(36, int(round(framed_photo.width * 0.05)))
    top_margin = max(56, int(round(framed_photo.height * 0.16)))
    text_gap = max(56, int(round(framed_photo.height * 0.14)))
    bottom_margin = max(72, int(round(framed_photo.height * 0.16)))

    caption_font_size = max(18, int(round(framed_photo.width * 0.038)))
    caption_font = _load_font(resolved_font_path, caption_font_size)
    caption_bbox = caption_font.getbbox(caption)
    caption_width = caption_bbox[2] - caption_bbox[0]
    caption_height = caption_bbox[3] - caption_bbox[1]

    canvas_width = framed_photo.width + side_margin * 2
    canvas_height = (
        top_margin
        + framed_photo.height
        + text_gap
        + caption_height
        + bottom_margin
    )
    canvas = Image.new("RGB", (canvas_width, canvas_height), ImageColor.getrgb(DEFAULT_BACKGROUND))

    photo_x = (canvas_width - framed_photo.width) // 2
    photo_y = top_margin

    shadow_blur = max(4, int(round(border_size * 2.5)))
    _draw_shadow(canvas, framed_photo, photo_x, photo_y, shadow_blur)
    canvas.paste(framed_photo, (photo_x, photo_y))

    if stamp_text:
        stamp_font_size = max(14, int(round(photo.width * 0.03)))
        stamp_font = _load_font(resolved_font_path, stamp_font_size)
        draw_on_photo = ImageDraw.Draw(canvas)
        stamp_bbox = stamp_font.getbbox(stamp_text)
        stamp_width = stamp_bbox[2] - stamp_bbox[0]
        stamp_height = stamp_bbox[3] - stamp_bbox[1]
        stamp_x = photo_x + border_size + photo.width - stamp_width - max(18, int(round(photo.width * 0.04)))
        stamp_y = photo_y + border_size + photo.height - stamp_height - max(12, int(round(photo.height * 0.04)))
        draw_on_photo.text((stamp_x, stamp_y), stamp_text, font=stamp_font, fill=DEFAULT_STAMP_COLOR)

    draw = ImageDraw.Draw(canvas)
    caption_x = (canvas_width - caption_width) // 2
    caption_y = photo_y + framed_photo.height + text_gap
    draw.text((caption_x, caption_y), caption, font=caption_font, fill=DEFAULT_TEXT_COLOR)

    target_path.parent.mkdir(parents=True, exist_ok=True)
    save_kwargs = {"quality": 95}
    if target_path.suffix.lower() in {".png"}:
        save_kwargs = {}
    canvas.save(target_path, **save_kwargs)
    return target_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a simple framed image similar to the provided film-photo reference."
    )
    parser.add_argument("input_image", help="Path to the source image.")
    parser.add_argument("output_image", help="Path to the rendered output image.")
    parser.add_argument("--caption", required=True, help="Centered caption shown below the photo.")
    parser.add_argument(
        "--stamp",
        default=None,
        help="Optional in-photo stamp text rendered near the bottom-right corner.",
    )
    parser.add_argument(
        "--font-path",
        default=str(DEFAULT_FONT_PATH),
        help="Font path for the caption and optional stamp.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    create_film_frame(
        input_path=args.input_image,
        output_path=args.output_image,
        caption=args.caption,
        stamp_text=args.stamp,
        font_path=args.font_path,
    )


if __name__ == "__main__":
    main()
