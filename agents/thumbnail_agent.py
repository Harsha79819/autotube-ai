from PIL import Image, ImageDraw, ImageFont
import os
import textwrap


def create_thumbnail(title):

    os.makedirs("output", exist_ok=True)

    # Use first downloaded image as background
    background = "assets/1.jpg"

    if not os.path.exists(background):
        print("❌ Background image not found")
        return None

    image = Image.open(background).convert("RGB")

    # YouTube thumbnail size
    image = image.resize((1280, 720))

    draw = ImageDraw.Draw(image)

    # Dark overlay for better text visibility
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)

    overlay_draw.rectangle(
        (0, 430, 1280, 720),
        fill=(0, 0, 0, 170)
    )

    image = Image.alpha_composite(
        image.convert("RGBA"),
        overlay
    )

    draw = ImageDraw.Draw(image)

    # Font
    font_path = "C:/Windows/Fonts/arialbd.ttf"

    try:
        font = ImageFont.truetype(font_path, 58)
    except:
        font = ImageFont.load_default()

    # Short thumbnail title
    words = title.split()
    short_title = " ".join(words[:10])

    lines = textwrap.wrap(
        short_title,
        width=28
    )

    y = 455

    for line in lines[:3]:

        # Shadow
        draw.text(
            (42, y + 4),
            line,
            font=font,
            fill="black"
        )

        # Main text
        draw.text(
            (38, y),
            line,
            font=font,
            fill="white"
        )

        y += 70

    output = "output/thumbnail.jpg"

    image.convert("RGB").save(
        output,
        quality=95
    )

    print("✅ Thumbnail created:", output)

    return output


if __name__ == "__main__":
    create_thumbnail("Tata Motors Latest News")