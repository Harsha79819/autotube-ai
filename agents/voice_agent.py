import asyncio
import edge_tts
import os

VOICE = "en-US-AndrewNeural"

async def create_voice():

    if not os.path.exists("output/script.txt"):
        print("Script not found!")
        return

    with open("output/script.txt", "r", encoding="utf-8") as f:
        text = f.read()

    communicate = edge_tts.Communicate(text, VOICE)

    await communicate.save("output/voice.mp3")

    print("Voice created successfully!")

if __name__ == "__main__":
    asyncio.run(create_voice())