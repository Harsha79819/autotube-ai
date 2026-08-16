import torchaudio as ta
from huggingface_hub import snapshot_download

from chatterbox.mtl_tts import ChatterboxMultilingualTTS
from chatterbox.models.t3.modules.t3_config import T3Config


REFERENCE = "voice_reference.wav"


print("Using CPU...")
print("Preparing Telugu Chatterbox configuration...")


# Telugu model uses a 2521-token vocabulary.
# The standard multilingual config uses 2454.
_original_multilingual = T3Config.multilingual


@classmethod
def telugu_multilingual(cls):
    return cls(text_tokens_dict_size=2521)


T3Config.multilingual = telugu_multilingual


print("Loading Telugu Chatterbox model...")

ckpt = snapshot_download(
    "shankarpandala/chatterbox-telugu"
)

model = ChatterboxMultilingualTTS.from_local(
    ckpt,
    device="cpu",
    t3_model="t3_mtl_te.safetensors"
)


text = """
Namaskaram friends, welcome to our channel.
Eeroju India lo jarugutunna important news updates ni simple ga telusukundam.
"""


print("Generating cloned voice...")

wav = model.generate(
    text,
    language_id="te",
    audio_prompt_path=REFERENCE
)

ta.save(
    "voice_test_output.wav",
    wav,
    model.sr
)

print("Voice generated successfully!")
print("Saved: voice_test_output.wav")

