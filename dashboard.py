import streamlit as st
import os
import asyncio
import json

from agents.news_agent import get_news
from agents.script_agent import generate_script
from agents.voice_agent import create_voice
from agents.image_agent import download_images
from agents.video_agent import create_video
from agents.subtitle_agent import create_subtitles
from agents.final_video_agent import create_final_video
from agents.thumbnail_agent import create_thumbnail
from agents.youtube_agent import upload_video


# --------------------------------------------------
# PAGE CONFIG
# --------------------------------------------------

st.set_page_config(
    page_title="AutoTube AI",
    layout="wide"
)


# --------------------------------------------------
# HEADER
# --------------------------------------------------

st.title("AutoTube AI")
st.subheader(
    "Automated YouTube Video Generator"
)

st.divider()


# --------------------------------------------------
# PIPELINE
# --------------------------------------------------

steps = [
    "News Fetch",
    "Script Generate",
    "Voice Generate",
    "Collect Visuals",
    "Create Video",
    "Auto Subtitles",
    "Final Video",
    "Create Thumbnail",
    "YouTube Upload"
]


# --------------------------------------------------
# SESSION STATE
# --------------------------------------------------

if "running" not in st.session_state:
    st.session_state.running = False

if "current_step" not in st.session_state:
    st.session_state.current_step = 0

if "completed" not in st.session_state:
    st.session_state.completed = []

if "news_topic" not in st.session_state:
    st.session_state.news_topic = ""

if "youtube_id" not in st.session_state:
    st.session_state.youtube_id = ""

if "error" not in st.session_state:
    st.session_state.error = ""


# --------------------------------------------------
# STATUS
# --------------------------------------------------

def get_status(step_number):

    if step_number in st.session_state.completed:
        return "COMPLETED"

    if (
        st.session_state.running
        and step_number
        == st.session_state.current_step
    ):
        return "RUNNING"

    return "WAITING"


# --------------------------------------------------
# PROGRESS
# --------------------------------------------------

completed_count = len(
    st.session_state.completed
)

progress = (
    completed_count / len(steps)
)

st.markdown(
    "### Generation Progress"
)

st.progress(progress)

st.write(
    f"{completed_count} / "
    f"{len(steps)} steps completed"
)

st.divider()


# --------------------------------------------------
# PIPELINE DISPLAY
# --------------------------------------------------

st.markdown("### Pipeline")

for i, step in enumerate(
    steps,
    start=1
):

    status = get_status(i)

    col1, col2, col3 = st.columns(
        [1, 5, 2]
    )

    with col1:
        st.write(f"**{i}**")

    with col2:
        st.write(step)

    with col3:

        if status == "COMPLETED":
            st.success("COMPLETED")

        elif status == "RUNNING":
            st.warning("RUNNING")

        else:
            st.info("WAITING")


st.divider()


# --------------------------------------------------
# START GENERATION
# --------------------------------------------------

if not st.session_state.running:

    if st.button(
        "START GENERATION",
        type="primary",
        use_container_width=True
    ):

        st.session_state.running = True
        st.session_state.current_step = 1
        st.session_state.completed = []
        st.session_state.error = ""
        st.session_state.youtube_id = ""

        st.rerun()


# --------------------------------------------------
# REAL PIPELINE
# --------------------------------------------------

if st.session_state.running:

    current = (
        st.session_state.current_step
    )

    try:

        # ------------------------------------------
        # STEP 1 - NEWS
        # ------------------------------------------

        if current == 1:

            st.warning(
                "Running Step 1: News Fetch"
            )

            topic = get_news()

            st.session_state.news_topic = topic

            st.session_state.completed.append(
                1
            )

            st.session_state.current_step = 2

            st.rerun()


        # ------------------------------------------
        # STEP 2 - SCRIPT
        # ------------------------------------------

        elif current == 2:

            st.warning(
                "Running Step 2: Script Generate"
            )

            generate_script(
                st.session_state.news_topic
            )

            st.session_state.completed.append(
                2
            )

            st.session_state.current_step = 3

            st.rerun()


        # ------------------------------------------
        # STEP 3 - VOICE
        # ------------------------------------------

        elif current == 3:

            st.warning(
                "Running Step 3: Voice Generate"
            )

            asyncio.run(
                create_voice()
            )

            st.session_state.completed.append(
                3
            )

            st.session_state.current_step = 4

            st.rerun()


        # ------------------------------------------
        # STEP 4 - VISUALS
        # ------------------------------------------

        elif current == 4:

            st.warning(
                "Running Step 4: Collect Visuals"
            )

            download_images(
                st.session_state.news_topic
            )

            st.session_state.completed.append(
                4
            )

            st.session_state.current_step = 5

            st.rerun()


        # ------------------------------------------
        # STEP 5 - VIDEO
        # ------------------------------------------

        elif current == 5:

            st.warning(
                "Running Step 5: Create Video"
            )

            create_video()

            st.session_state.completed.append(
                5
            )

            st.session_state.current_step = 6

            st.rerun()


        # ------------------------------------------
        # STEP 6 - SUBTITLES
        # ------------------------------------------

        elif current == 6:

            st.warning(
                "Running Step 6: Auto Subtitles"
            )

            create_subtitles()

            st.session_state.completed.append(
                6
            )

            st.session_state.current_step = 7

            st.rerun()


        # ------------------------------------------
        # STEP 7 - FINAL VIDEO
        # ------------------------------------------

        elif current == 7:

            st.warning(
                "Running Step 7: Final Video"
            )

            create_final_video()

            st.session_state.completed.append(
                7
            )

            st.session_state.current_step = 8

            st.rerun()


        # ------------------------------------------
        # STEP 8 - THUMBNAIL
        # ------------------------------------------

        elif current == 8:

            st.warning(
                "Running Step 8: Create Thumbnail"
            )

            create_thumbnail(
                st.session_state.news_topic
            )

            st.session_state.completed.append(
                8
            )

            st.session_state.current_step = 9

            st.rerun()


        # ------------------------------------------
        # STEP 9
        # ------------------------------------------

        elif current == 9:

            st.session_state.running = False

            st.success(
                "Generation completed!"
            )

            st.info(
                "Final video and thumbnail "
                "are ready. YouTube upload "
                "is waiting for your approval."
            )


    except Exception as e:

        st.session_state.running = False

        st.session_state.error = str(e)

        st.error(
            "Pipeline failed."
        )

        st.exception(e)


# --------------------------------------------------
# NEWS TOPIC
# --------------------------------------------------

if st.session_state.news_topic:

    st.divider()

    st.markdown(
        "### Current News Topic"
    )

    st.info(
        st.session_state.news_topic
    )


# --------------------------------------------------
# FINAL VIDEO
# --------------------------------------------------

st.divider()

st.markdown(
    "### Completed Video"
)

final_video = (
    "output/final_video.mp4"
)

if os.path.exists(final_video):

    st.video(final_video)

else:

    st.info(
        "Final video not available yet."
    )


# --------------------------------------------------
# THUMBNAIL
# --------------------------------------------------

thumbnail = (
    "output/thumbnail.jpg"
)

if os.path.exists(thumbnail):

    st.markdown(
        "### Thumbnail"
    )

    st.image(
        thumbnail,
        width=500
    )


# --------------------------------------------------
# YOUTUBE UPLOAD
# --------------------------------------------------

st.divider()

st.markdown(
    "### YouTube Upload"
)

if (
    os.path.exists(final_video)
    and os.path.exists(thumbnail)
):

    if not st.session_state.youtube_id:

        if st.button(
            "UPLOAD TO YOUTUBE",
            type="primary",
            use_container_width=True
        ):

            try:

                title = (
                    st.session_state.news_topic
                )

                description = (
                    "Auto-generated by "
                    "AutoTube AI."
                )

                tags = [
                    "news",
                    "AI",
                    "technology",
                    "AutoTube AI"
                ]

                with st.spinner(
                    "Uploading to YouTube..."
                ):

                    video_id = upload_video(
                        final_video,
                        title,
                        description,
                        tags,
                        privacy="private"
                    )

                st.session_state.youtube_id = (
                    video_id
                )

                st.success(
                    "YouTube upload completed!"
                )

                st.rerun()

            except Exception as e:

                st.error(
                    "YouTube upload failed."
                )

                st.exception(e)

    else:

        st.success(
            "YouTube upload completed!"
        )

        st.code(
            st.session_state.youtube_id
        )

else:

    st.info(
        "Complete video generation first."
    )


# --------------------------------------------------
# FOOTER
# --------------------------------------------------

st.divider()

st.caption(
    "AutoTube AI - Dashboard"
)