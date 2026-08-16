import os
import re
from google import genai
from dotenv import load_dotenv


# ============================================================
# CONFIG
# ============================================================

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY not found in .env file"
    )

client = genai.Client(api_key=API_KEY)


# ============================================================
# GEMINI MODEL
# ============================================================

MODELS = [
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-flash-latest",
]


# ============================================================
# GENERATE SCRIPT
# ============================================================

def generate_script(topic):
    """
    Generate a YouTube news video script.
    """

    print()
    print("=" * 60)
    print("AI SCRIPT GENERATION STARTED")
    print("=" * 60)
    print()
    print("Topic:")
    print(topic)
    print()

    prompt = f"""
You are a professional Indian YouTube news script writer.

Create a clear, engaging and factual YouTube video script
about the following topic:

{topic}

Requirements:

- Write in simple English.
- Suitable for a 2 to 4 minute YouTube news video.
- Start with a strong attention-grabbing introduction.
- Explain what happened.
- Mention the important people involved.
- Explain the important background.
- Explain why this news matters.
- Keep the tone professional and neutral.
- Do not invent facts.
- Do not create fake quotes.
- Do not use markdown.
- Do not use headings.
- Do not include camera directions.
- Do not include image instructions.
- Write only the narration that can be converted directly to voice.

End with a short professional conclusion.

Return ONLY the final narration script.
"""

    for model in MODELS:

        try:

            print(f"Trying model: {model}")

            response = client.models.generate_content(
                model=model,
                contents=prompt
            )

            text = getattr(
                response,
                "text",
                ""
            )

            if not text:
                print("Model returned empty response.")
                continue

            text = text.strip()

            # Remove accidental markdown
            text = re.sub(
                r"^```[a-zA-Z]*",
                "",
                text
            )

            text = re.sub(
                r"```$",
                "",
                text
            )

            text = text.strip()

            if len(text) < 100:
                print("Generated script is too short.")
                continue

            # Create output folder
            os.makedirs(
                "output",
                exist_ok=True
            )

            # Save script
            script_file = "output/script.txt"

            with open(
                script_file,
                "w",
                encoding="utf-8"
            ) as file:

                file.write(text)

            print()
            print("=" * 60)
            print("SCRIPT GENERATED SUCCESSFULLY")
            print("=" * 60)
            print()
            print(f"Saved to: {script_file}")
            print()
            print(f"Characters: {len(text)}")
            print()
            print("=" * 60)

            return text

        except Exception as error:

            print()
            print(f"Model failed: {model}")
            print(error)
            print()

    raise RuntimeError(
        "All Gemini models failed to generate the script."
    )


# ============================================================
# DIRECT TEST
# ============================================================

if __name__ == "__main__":

    topic = (
        "CJI Surya Kant Highlights "
        "Lawyers Role In Freedom Struggle"
    )

    script = generate_script(topic)

    print()
    print(script)