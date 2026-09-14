import streamlit as st
from pathlib import Path
import json


# ============================================================
# LIQUID GLASS UI
# ============================================================

st.set_page_config(
    page_title="AutoTube AI",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ============================================================
# GLASS UI CSS
# ============================================================

st.markdown(
    """
<style>

.stApp {
    background:
        radial-gradient(circle at 15% 10%, rgba(88, 70, 180, 0.18), transparent 30%),
        radial-gradient(circle at 85% 15%, rgba(0, 180, 255, 0.12), transparent 28%),
        #0B0F17;
    color: #F5F7FA;
}

.block-container {
    max-width: 1450px;
    padding-top: 2rem;
    padding-bottom: 4rem;
}

header[data-testid="stHeader"] {
    background: transparent;
}

section[data-testid="stSidebar"] {
    display: none;
}

/* Glass cards */

.glass-card {
    background: rgba(255,255,255,0.055);
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 18px;
    padding: 24px;
    backdrop-filter: blur(18px);
    -webkit-backdrop-filter: blur(18px);
    box-shadow:
        0 20px 60px rgba(0,0,0,0.30),
        inset 0 1px 0 rgba(255,255,255,0.06);
    margin-bottom: 18px;
}

/* Header */

.brand {
    font-size: 30px;
    font-weight: 800;
    letter-spacing: -1px;
}

.brand span {
    background: linear-gradient(90deg,#8B5CF6,#22D3EE);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}

.status {
    display: inline-block;
    padding: 7px 12px;
    margin-left: 7px;
    border-radius: 999px;
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(255,255,255,0.10);
    font-size: 12px;
    color: #CBD5E1;
}

/* Hero */

.hero-title {
    font-size: 46px;
    line-height: 1.05;
    font-weight: 850;
    letter-spacing: -2px;
    margin-top: 20px;
}

.hero-gradient {
    background: linear-gradient(
        90deg,
        #FFFFFF 0%,
        #A78BFA 45%,
        #22D3EE 100%
    );
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}

.hero-subtitle {
    color: #94A3B8;
    font-size: 17px;
    margin-top: 12px;
    margin-bottom: 30px;
}

/* Section titles */

.section-title {
    font-size: 20px;
    font-weight: 750;
    margin-bottom: 5px;
}

.section-subtitle {
    color: #94A3B8;
    font-size: 13px;
    margin-bottom: 18px;
}

/* Streamlit inputs */

div[data-baseweb="input"] > div,
div[data-baseweb="select"] > div,
textarea {
    background: rgba(255,255,255,0.045) !important;
    border: 1px solid rgba(255,255,255,0.10) !important;
    border-radius: 12px !important;
    color: white !important;
}

label {
    color: #CBD5E1 !important;
}

/* Buttons */

.stButton > button {
    width: 100%;
    border-radius: 13px;
    border: 1px solid rgba(139,92,246,0.55);
    background: linear-gradient(
        135deg,
        rgba(139,92,246,0.90),
        rgba(34,211,238,0.78)
    );
    color: white;
    font-weight: 750;
    min-height: 48px;
    box-shadow: 0 10px 30px rgba(91,70,180,0.25);
    transition: all 0.2s ease;
}

.stButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 15px 40px rgba(34,211,238,0.22);
}

/* Pipeline */

.pipeline {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    margin-top: 15px;
    overflow-x: auto;
}

.pipeline-step {
    min-width: 105px;
    text-align: center;
    padding: 13px 10px;
    border-radius: 14px;
    background: rgba(255,255,255,0.045);
    border: 1px solid rgba(255,255,255,0.08);
}

.pipeline-icon {
    font-size: 21px;
}

.pipeline-name {
    font-size: 11px;
    color: #CBD5E1;
    margin-top: 5px;
}

.pipeline-arrow {
    color: #64748B;
    font-size: 18px;
}

/* Chips */

.chip {
    display: inline-block;
    padding: 7px 11px;
    margin-right: 6px;
    border-radius: 999px;
    background: rgba(255,255,255,0.055);
    border: 1px solid rgba(255,255,255,0.08);
    color: #CBD5E1;
    font-size: 12px;
}

/* Success */

.success-box {
    padding: 16px;
    border-radius: 14px;
    background: rgba(34,197,94,0.08);
    border: 1px solid rgba(34,197,94,0.25);
    color: #BBF7D0;
}

/* Responsive */

@media (max-width: 900px) {

    .hero-title {
        font-size: 34px;
    }

    .pipeline {
        justify-content: flex-start;
    }

}

</style>
""",
    unsafe_allow_html=True,
)


# ============================================================
# HEADER
# ============================================================

st.markdown(
    """
<div class="glass-card">

<div style="
display:flex;
justify-content:space-between;
align-items:center;
gap:20px;
flex-wrap:wrap;
">

<div class="brand">
🎬 <span>AutoTube AI</span>
</div>

<div>
<span class="status">● AI READY</span>
<span class="status">ENGLISH</span>
<span class="status">1080P</span>
</div>

</div>

</div>
""",
    unsafe_allow_html=True,
)


# ============================================================
# HERO
# ============================================================

st.markdown(
    """
<div class="hero-title">
Transform Ideas into<br>
<span class="hero-gradient">Instant Videos.</span>
</div>

<div class="hero-subtitle">
AI-powered video creation — from topic to script, voice, visuals,
subtitles, thumbnail and YouTube publishing.
</div>
""",
    unsafe_allow_html=True,
)


# ============================================================
# MAIN COLUMNS
# ============================================================

left, right = st.columns([1.55, 1], gap="large")


# ============================================================
# LEFT — CREATE VIDEO
# ============================================================

with left:

    st.markdown(
        """
<div class="glass-card">

<div class="section-title">Create Video</div>
<div class="section-subtitle">
Tell AutoTube AI what you want to create.
</div>
""",
        unsafe_allow_html=True,
    )

    content_type = st.selectbox(
        "Content Type",
        [
            "News",
            "Explainer",
            "Uploaded Flyer",
            "Custom Topic",
        ],
    )

    topic = st.text_area(
        "Topic",
        placeholder="Enter your video topic...",
        height=100,
    )

    language_style = st.selectbox(
        "Language / Style",
        [
            "English news style",
            "English creator style",
            "English documentary style",
            "English short-form style",
        ],
    )

    voice = st.selectbox(
        "Voice",
        [
            "Creator Voice",
        ],
    )

    captions = st.toggle(
        "Auto Subtitles",
        value=True,
    )

    thumbnail = st.toggle(
        "Create Thumbnail",
        value=True,
    )

    metadata = st.toggle(
        "Generate YouTube Metadata",
        value=True,
    )

    youtube_upload = st.toggle(
        "Upload to YouTube",
        value=False,
    )

    youtube_privacy = "private"

    if youtube_upload:
        youtube_privacy = st.selectbox(
            "YouTube Privacy",
            [
                "private",
                "unlisted",
                "public",
            ],
        )

    generate = st.button(
        "🚀 Generate Video",
        type="primary",
    )

    st.markdown("</div>", unsafe_allow_html=True)


# ============================================================
# RIGHT — MEDIA
# ============================================================

with right:

    st.markdown(
        """
<div class="glass-card">

<div class="section-title">Media & Assets</div>
<div class="section-subtitle">
Add images, videos or flyers for your generation.
</div>
""",
        unsafe_allow_html=True,
    )

    uploaded_files = st.file_uploader(
        "Upload media",
        type=[
            "png",
            "jpg",
            "jpeg",
            "webp",
            "mp4",
            "mov",
            "avi",
        ],
        accept_multiple_files=True,
    )

    if uploaded_files:
        st.success(
            f"{len(uploaded_files)} file(s) ready"
        )

        for file in uploaded_files:
            st.caption(f"📎 {file.name}")

    else:
        st.markdown(
            """
<div style="
padding:35px 15px;
text-align:center;
border:1px dashed rgba(255,255,255,0.14);
border-radius:15px;
color:#64748B;
">
📁<br>
Upload images, videos or flyers
</div>
""",
            unsafe_allow_html=True,
        )

    st.markdown("</div>", unsafe_allow_html=True)


# ============================================================
# PIPELINE
# ============================================================

st.markdown(
    """
<div class="glass-card">

<div class="section-title">AI Production Pipeline</div>
<div class="section-subtitle">
One workflow. From idea to published video.
</div>

<div class="pipeline">

<div class="pipeline-step">
<div class="pipeline-icon">📰</div>
<div class="pipeline-name">News</div>
</div>

<div class="pipeline-arrow">→</div>

<div class="pipeline-step">
<div class="pipeline-icon">✍️</div>
<div class="pipeline-name">Script</div>
</div>

<div class="pipeline-arrow">→</div>

<div class="pipeline-step">
<div class="pipeline-icon">🎙️</div>
<div class="pipeline-name">Voice</div>
</div>

<div class="pipeline-arrow">→</div>

<div class="pipeline-step">
<div class="pipeline-icon">🖼️</div>
<div class="pipeline-name">Visuals</div>
</div>

<div class="pipeline-arrow">→</div>

<div class="pipeline-step">
<div class="pipeline-icon">🎬</div>
<div class="pipeline-name">Video</div>
</div>

<div class="pipeline-arrow">→</div>

<div class="pipeline-step">
<div class="pipeline-icon">💬</div>
<div class="pipeline-name">Subtitles</div>
</div>

<div class="pipeline-arrow">→</div>

<div class="pipeline-step">
<div class="pipeline-icon">✨</div>
<div class="pipeline-name">Thumbnail</div>
</div>

<div class="pipeline-arrow">→</div>

<div class="pipeline-step">
<div class="pipeline-icon">▶️</div>
<div class="pipeline-name">YouTube</div>
</div>

</div>

</div>
""",
    unsafe_allow_html=True,
)


# ============================================================
# GENERATE
# ============================================================

if generate:

    media_paths = []

    if uploaded_files:

        upload_dir = Path("output/uploads")
        upload_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        for file in uploaded_files:

            file_path = upload_dir / file.name

            with open(file_path, "wb") as f:
                f.write(file.getbuffer())

            media_paths.append(
                str(file_path)
            )

    if (
        content_type != "Uploaded Flyer"
        and not topic.strip()
    ):
        st.warning(
            "Please enter a topic first."
        )

    elif (
        content_type == "Uploaded Flyer"
        and not media_paths
    ):
        st.warning(
            "Please upload a flyer or image."
        )

    else:

        try:

            with st.spinner(
                "AutoTube AI is creating your video..."
            ):

                result = generate_multi_media_video(
                    topic=topic.strip(),
                    media_files=media_paths,
                    content_type=content_type,
                    language_style=language_style,
                    voice=voice,
                    captions=captions,
                    thumbnail=thumbnail,
                    metadata=metadata,
                    youtube_upload=youtube_upload,
                    youtube_privacy=youtube_privacy,
                )

            st.session_state["pipeline_result"] = result

            st.success(
                "🎉 Video generation completed!"
            )

        except Exception as e:

            st.error(
                f"AutoTube AI failed: {e}"
            )


# ============================================================
# OUTPUT
# ============================================================

result = st.session_state.get(
    "pipeline_result"
)

final_video = Path(
    "output/final_video.mp4"
)

thumbnail_file = Path(
    "output/thumbnail.jpg"
)

if result or final_video.exists():

    st.markdown(
        """
<div class="glass-card">

<div class="section-title">
Your Output
</div>

<div class="section-subtitle">
Your latest AutoTube AI generation.
</div>
""",
        unsafe_allow_html=True,
    )

    if final_video.exists():

        st.video(
            str(final_video)
        )

        st.markdown(
            """
<span class="chip">🎬 MP4</span>
<span class="chip">📺 1080p</span>
<span class="chip">🔊 AI Voice</span>
<span class="chip">💬 Subtitles</span>
""",
            unsafe_allow_html=True,
        )

        with open(
            final_video,
            "rb",
        ) as video_file:

            st.download_button(
                "⬇️ Download Video",
                data=video_file,
                file_name="autotube_ai_video.mp4",
                mime="video/mp4",
            )

    if thumbnail_file.exists():

        st.markdown(
            "### Thumbnail"
        )

        st.image(
            str(thumbnail_file),
            use_container_width=True,
        )

    st.markdown("</div>", unsafe_allow_html=True)


# ============================================================
# FOOTER
# ============================================================

st.markdown(
    """
<div style="
text-align:center;
padding:25px;
color:#475569;
font-size:12px;
">
AutoTube AI • AI Video Automation
</div>
""",
    unsafe_allow_html=True,
)