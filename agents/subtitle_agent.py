import whisper


def create_subtitles():

    model = whisper.load_model("base")

    result = model.transcribe(
        "output/voice.mp3"
    )

    output_file = "output/subtitles.srt"

    with open(
        output_file,
        "w",
        encoding="utf-8"
    ) as f:

        for i, seg in enumerate(
            result["segments"],
            start=1
        ):

            start = seg["start"]
            end = seg["end"]
            text = seg["text"].strip()

            def fmt(t):

                h = int(t // 3600)
                m = int((t % 3600) // 60)
                s = int(t % 60)
                ms = int(
                    (t - int(t)) * 1000
                )

                return (
                    f"{h:02}:{m:02}:"
                    f"{s:02},{ms:03}"
                )

            f.write(f"{i}\n")
            f.write(
                f"{fmt(start)} --> {fmt(end)}\n"
            )
            f.write(f"{text}\n\n")

    print(
        "Subtitles saved to "
        "output/subtitles.srt"
    )

    return output_file


if __name__ == "__main__":

    create_subtitles()