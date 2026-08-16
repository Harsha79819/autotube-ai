from flask import Flask, jsonify, render_template
import subprocess
import threading
import os
import sys

app = Flask(__name__)

running = False
current_step = 0
status_message = "Ready to start."

steps = [
    "News Fetch",
    "Script Generation",
    "Voice Generation",
    "Images / Video Clips",
    "Video Creation",
    "Auto Subtitles",
    "Thumbnail",
    "YouTube Upload"
]


def run_autotube():

    global running
    global current_step
    global status_message

    running = True
    current_step = 1
    status_message = "Starting AutoTube AI..."

    project_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..")
    )

    try:

        process = subprocess.Popen(
            [sys.executable, "-u", "main.py"],
            cwd=project_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1
        )

        for line in process.stdout:

            line = line.strip()

            if not line:
                continue

            print(line, flush=True)

            if "Getting fresh news" in line:
                current_step = 1
                status_message = "Fetching fresh news..."

            elif "News Topic:" in line:
                current_step = 1
                status_message = "News fetched."

            elif "Generating Script" in line:
                current_step = 2
                status_message = "Generating script..."

            elif "Script Saved" in line:
                current_step = 2
                status_message = "Script generated."

            elif "Creating Voice" in line:
                current_step = 3
                status_message = "Creating voice..."

            elif "Voice Created" in line:
                current_step = 3
                status_message = "Voice generated."

            elif "Downloading Fresh Images" in line:
                current_step = 4
                status_message = "Downloading fresh images..."

            elif "Images Downloaded" in line:
                current_step = 4
                status_message = "Images downloaded."

            elif "Creating Video" in line:
                current_step = 5
                status_message = "Creating video..."

            elif "Video Created" in line:
                current_step = 5
                status_message = "Video created."

            elif "Creating Subtitles" in line:
                current_step = 6
                status_message = "Creating subtitles..."

            elif "Subtitles Created" in line:
                current_step = 6
                status_message = "Subtitles created."

            elif "Adding Subtitles" in line:
                current_step = 6
                status_message = "Adding subtitles to video..."

            elif "Final Video Created" in line:
                current_step = 6
                status_message = "Final video created."

            elif "Generating YouTube Metadata" in line:
                current_step = 7
                status_message = "Generating YouTube metadata..."

            elif "Uploading to YouTube" in line:
                current_step = 8
                status_message = "Uploading to YouTube..."

            elif "Upload Complete" in line:
                current_step = 8
                status_message = "YouTube upload completed."

            elif "AutoTube AI Finished" in line:
                current_step = 8
                status_message = "AutoTube AI finished successfully."

        process.wait()

        if process.returncode == 0:

            current_step = 8
            status_message = "AutoTube AI Finished Successfully!"

        else:

            status_message = "AutoTube AI failed."

    except Exception as e:

        print("ERROR:", e, flush=True)

        status_message = f"Error: {e}"

    finally:

        running = False


@app.route("/")
def home():

    return render_template(
        "index.html",
        running=running,
        status=status_message,
        current_step=current_step,
        steps=steps
    )


@app.route("/start", methods=["POST"])
def start():

    global running
    global current_step
    global status_message

    if running:

        return jsonify({
            "success": False,
            "message": "AutoTube AI is already running."
        })

    running = True
    current_step = 1
    status_message = "Starting AutoTube AI..."

    thread = threading.Thread(
        target=run_autotube,
        daemon=True
    )

    thread.start()

    return jsonify({
        "success": True,
        "message": "AutoTube AI started."
    })


@app.route("/status")
def status():

    return jsonify({
        "running": running,
        "step": current_step,
        "total_steps": len(steps),
        "steps": steps,
        "message": status_message
    })


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )