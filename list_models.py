import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise RuntimeError("GEMINI_API_KEY is not configured in .env")

client = genai.Client(api_key=api_key)

models = client.models.list()

for model in models:
    print(model.name)