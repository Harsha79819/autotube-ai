from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os
import re
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT / "assets"
OUTPUT_DIR = ROOT / "output"


def _find_best_background():
    """
    Select the best landscape image from assets.

    Avoids:
    - contact sheets
    - very small images
    - portrait images when possible

    Prefers:
    - landscape orientation
    - larger resolution
    - good aspect ratio for YouTube thumbnails
    """

    candidates = []

    if not ASSETS_DIR.exists():
        return None

    for path in ASSETS_DIR.iterdir():

        if path.name.lower() in {
            "contact_sheet.jpg",
            "contact_sheet.jpeg",
            "contact_sheet.png",
        }:
            continue

        if path.suffix.lower() not in {
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
        }:
            continue

        try:
            with Image.open(path) as img:

                width, height = img.size

                if width < 500 or height < 300:
                    continue

                aspect = width / height

                # Strong preference for landscape images.
                if aspect >= 1.5:
                    orientation_score = 100
                elif aspect >= 1.2:
                    orientation_score = 70
                elif aspect >= 1.0:
                    orientation_score = 25
                else:
                    orientation_score = 0

                resolution_score = min(
                    (width * height) / 1_000_000,
                    10,
                )

                # Prefer images close to 16:9.
                ratio_difference = abs(aspect - (16 / 9))

                ratio_score = max(
                    0,
                    30 - (ratio_difference * 30),
                )

                score = (
                    orientation_score
                    + resolution_score
                    + ratio_score
                )

                candidates.append(
                    (score, path)
                )

        except Exception as exc:
            print(
                f"⚠️ Could not inspect {path.name}: {exc}"
            )

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    selected = candidates[0][1]

    print(
        f"🖼️ Thumbnail background selected: "
        f"{selected.name}"
    )

    return selected


def _load_font(size):
    """
    Find a usable bold font on macOS/Linux/Windows.
    """

    font_paths = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Helvetica Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ]

    for path in font_paths:

        if os.path.exists(path):

            try:
                return ImageFont.truetype(
                    path,
                    size,
                )
            except OSError:
                pass

    return ImageFont.load_default()


def _clean_title(title):
    """
    Convert a long video title into a short
    thumbnail-friendly phrase.
    """

    if not title:
        return "LATEST NEWS"

    title = str(title).strip()

    # Remove common punctuation noise.
    title = re.sub(
        r"\s+",
        " ",
        title,
    )

    title = title.strip(
        " .,!?:;-_"
    )

    # Keep the strongest first part.
    words = title.split()

    # Thumbnail text should stay short.
    if len(words) > 8:
        words = words[:8]

    result = " ".join(words)

    return result.upper()


def _crop_to_thumbnail(image):
    """
    Center-crop image to exactly 16:9.
    """

    target_ratio = 16 / 9

    width, height = image.size
    current_ratio = width / height

    if current_ratio > target_ratio:

        # Image is too wide.
        new_width = int(
            height * target_ratio
        )

        left = (width - new_width) // 2

        image = image.crop(
            (
                left,
                0,
                left + new_width,
                height,
            )
        )

    else:

        # Image is too tall.
        new_height = int(
            width / target_ratio
        )

        top = (height - new_height) // 2

        image = image.crop(
            (
                0,
                top,
                width,
                top + new_height,
            )
        )

    return image.resize(
        (1280, 720),
        Image.Resampling.LANCZOS,
    )


def create_thumbnail(title):

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print()
    print("=" * 60)
    print("THUMBNAIL GENERATION")
    print("=" * 60)

    background_path = _find_best_background()

    if background_path is None:

        print(
            "❌ No suitable background image found"
        )

        return None

    try:

        image = Image.open(
            background_path
        ).convert("RGB")

    except Exception as exc:

        print(
            f"❌ Failed to open background: {exc}"
        )

        return None

    # --------------------------------------------------------
    # CROP / RESIZE
    # --------------------------------------------------------

    image = _crop_to_thumbnail(
        image
    )

    # --------------------------------------------------------
    # SLIGHT CONTRAST / SHARPNESS
    # --------------------------------------------------------

    image = image.filter(
        ImageFilter.UnsharpMask(
            radius=1,
            percent=120,
            threshold=3,
        )
    )

    # --------------------------------------------------------
    # DARK GRADIENT OVERLAY
    # --------------------------------------------------------

    image = image.convert("RGBA")

    overlay = Image.new(
        "RGBA",
        image.size,
        (0, 0, 0, 0),
    )

    overlay_draw = ImageDraw.Draw(
        overlay
    )

    # Bottom dark area.
    overlay_draw.rectangle(
        (0, 390, 1280, 720),
        fill=(0, 0, 0, 165),
    )

    # Extra subtle top/bottom darkness.
    overlay_draw.rectangle(
        (0, 0, 1280, 90),
        fill=(0, 0, 0, 45),
    )

    image = Image.alpha_composite(
        image,
        overlay,
    )

    draw = ImageDraw.Draw(image)

    # --------------------------------------------------------
    # TITLE
    # --------------------------------------------------------

    thumbnail_title = _clean_title(
        title
    )

    font = _load_font(58)

    # Wrap based on pixel width rather than
    # blindly using a fixed word count.
    words = thumbnail_title.split()

    lines = []
    current = ""

    for word in words:

        test = (
            f"{current} {word}"
            if current
            else word
        )

        bbox = draw.textbbox(
            (0, 0),
            test,
            font=font,
            stroke_width=0,
        )

        text_width = (
            bbox[2] - bbox[0]
        )

        if (
            text_width <= 1120
            and len(lines) < 3
        ):
            current = test
        else:

            if current:
                lines.append(current)

            current = word

    if current:
        lines.append(current)

    lines = lines[:3]

    # --------------------------------------------------------
    # CENTER TITLE VERTICALLY
    # --------------------------------------------------------

    line_height = 68
    total_height = (
        len(lines) * line_height
    )

    y = 555 - (
        total_height // 2
    )

    for line in lines:

        bbox = draw.textbbox(
            (0, 0),
            line,
            font=font,
            stroke_width=2,
        )

        text_width = (
            bbox[2] - bbox[0]
        )

        x = (
            1280 - text_width
        ) // 2

        # Strong shadow.
        draw.text(
            (x + 5, y + 5),
            line,
            font=font,
            fill=(0, 0, 0, 220),
            stroke_width=3,
            stroke_fill=(0, 0, 0, 220),
        )

        # Main white text.
        draw.text(
            (x, y),
            line,
            font=font,
            fill="white",
            stroke_width=2,
            stroke_fill="black",
        )

        y += line_height

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    output = (
        OUTPUT_DIR /
        "thumbnail.jpg"
    )

    image.convert("RGB").save(
        output,
        "JPEG",
        quality=95,
        optimize=True,
    )

    print(
        f"✅ Thumbnail created: {output}"
    )

    print(
        f"📝 Thumbnail title: "
        f"{thumbnail_title}"
    )

    print(
        f"🖼️ Background: "
        f"{background_path.name}"
    )

    print("=" * 60)

    return output


if __name__ == "__main__":

    create_thumbnail(
        "Tata Motors Latest News"
    )

