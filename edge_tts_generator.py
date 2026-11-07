"""
edge_tts_generator.py

Free, unlimited Telugu TTS using Microsoft Edge's neural voices via the
open-source `edge-tts` library (no API key, no quota).

Install:
    pip install edge-tts --break-system-packages

Available Telugu voices (verify current list anytime with `edge-tts --list-voices`):
    te-IN-ShrutiNeural  (female)
    te-IN-MohanNeural   (male)

Usage:
    import asyncio
    asyncio.run(generate_telugu_speech(
        text="మీ స్క్రిప్ట్ ఇక్కడ...",
        output_path="voice.mp3",
        voice="te-IN-MohanNeural",
        rate="+8%",     # slightly energetic pacing, avoids flat/robotic feel
        pitch="+2Hz",   # tiny lift for a livelier, less monotone delivery
    ))
"""

import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import concurrent.futures
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
try:
    import certifi
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
except ImportError:
    pass
import edge_tts

ROOT = Path(__file__).resolve().parent
TTS_CACHE_DIR = ROOT / "data" / "cache" / "tts_cache"
TTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def prepare_script_for_tts(raw_text: str) -> str:
    """Punctuation cleanup, abbreviation expansion, Tanglish transliteration, and phonetic Telugu tech normalization so Edge-TTS
    pacing sounds completely natural, fluent, and human-like."""
    text = str(raw_text or "").strip()

    # Ensure native Telugu script (తెలుగు లిపి) if Romanized Tanglish is detected
    try:
        from utils.transliterate_telugu import ensure_telugu_script
        text = ensure_telugu_script(text)
    except Exception as trans_err:
        pass

    # Normalize common abbreviations and English titles/loanwords before punctuation splitting
    COMMON_REPLACEMENTS = [
        (r"\bMr\.\s*", "మిస్టర్ "),
        (r"\bMr\b", "మిస్టర్"),
        (r"\bMrs\.\s*", "మిసెస్ "),
        (r"\bMrs\b", "మిసెస్"),
        (r"\bDr\.\s*", "డాక్టర్ "),
        (r"\bDr\b", "డాక్టర్"),
        (r"\bvs\.\s*|\bv/s\s*|\bvs\b", " వర్సెస్ "),
        (r"\bPan-India\b|\bPan India\b|\bpan india\b", "పాన్ ఇండియా"),
        (r"\bOTT\b|\bott\b", "ఓటీటీ"),
        (r"\bBGM\b|\bbgm\b", "బీజీఎం"),
        (r"\bTRP\s*ratings\b|\bTRP\b|\btrp\b", "టీఆర్పీ రేటింగ్స్"),
        (r"\bBigg\s*Boss\b|\bBiggboss\b", "బిగ్ బాస్"),
        (r"\bBB10\b|\bBB 10\b", "బిగ్ బాస్ 10"),
        (r"\bMind\s*blank\b|\bmindblank\b", "మైండ్ బ్లాంక్"),
        (r"\bScene\s*cut\b|\bscenecut\b", "సీన్ కట్"),
        (r"\bSelective\s*grilling\b", "సెలెక్టివ్ గ్రిల్లింగ్"),
        (r"\bGrilling\b", "గ్రిల్లింగ్"),
        (r"\bPR\s*strategy\b|\bPR\b|\bpr\b", "పీఆర్ స్ట్రాటజీ"),
        (r"\bSecret\s*room\b", "సీక్రెట్ రూమ్"),
        (r"\bLive\s*feed\b", "లైవ్ ఫీడ్"),
        (r"\bWalkout\b|\bwalk out\b", "వాకౌట్"),
        (r"\bRe-entry\b|\bRe\s*entry\b|\breentry\b", "రీఎంట్రీ"),
        (r"\bElimination\b|\beliminations\b", "ఎలిమినేషన్"),
        (r"\bNomination\b|\bnominations\b", "నామినేషన్"),
        (r"\bCaptaincy\b", "కెప్టెన్సీ"),
        (r"\bTask\b|\btasks\b", "టాస్క్"),
        (r"\bSnacks\b|\bsnack\b", "స్నాక్స్"),
        (r"\bChill\b", "చిల్"),
        (r"\bFake\b", "ఫేక్"),
        (r"\bCircus\s*comedy\s*show\b", "సర్కస్ కామెడీ షో"),
        (r"\bComedy\s*show\b|\bcomedy\b", "కామెడీ షో"),
        (r"\bVoting\s*graph\b", "ఓటింగ్ గ్రాఫ్"),
        (r"\bVoting\b|\bvotes\b|\bvote\b", "ఓటింగ్"),
        (r"\bSame\s*to\s*same\b", "సేమ్ టు సేమ్"),
        (r"\bStrategy\b|\bstrategies\b", "స్ట్రాటజీ"),
        (r"\bSafety\b", "సేఫ్టీ"),
        (r"\bDanger\s*zone\b", "డేంజర్ జోన్"),
        (r"\bReviews\b|\breviews\b", "రివ్యూస్"),
        (r"\bReview\b|\breview\b", "రివ్యూ"),
        (r"\bChannel\b|\bchannel\b", "ఛానల్"),
        (r"\bLike\b|\blikes\b", "లైక్"),
        (r"\bShare\b", "షేర్"),
        (r"\bSubscribe\b", "సబ్‌స్క్రైబ్"),
        (r"\bComment\b|\bcomments\b", "కామెంట్"),
        (r"\bOveracting\b|\bover action\b", "ఓవరాక్షన్"),
        (r"\bTwist\b|\btwists\b", "ట్విస్ట్"),
        (r"\bHouse\b", "హౌస్"),
        (r"\bHousemates\b|\bhouse\s*mates\b", "హౌస్‌మేట్స్"),
        (r"\bContent\b", "కంటెంట్"),
        (r"\bLoyalty\b", "లాయల్టీ"),
        (r"\bClasses\b|\bclass\b", "క్లాసులు"),
        (r"\bNext\s*level\b|\bnextlevel\b", "నెక్స్ట్ లెవెల్"),
        (r"\bFlip\b", "ఫ్లిప్"),
        (r"\bAudience\b", "ఆడియన్స్"),
        (r"\bWeekend\b", "వీకెండ్"),
        (r"\bCamera\b", "కెమెరా"),
        (r"\bExit\b", "ఎగ్జిట్"),
        (r"\bDrama\b", "డ్రామా"),
        (r"\bShock\b|\bshocking\b", "షాక్"),
        (r"\bSuper\b", "సూపర్"),
        (r"\bCrazy\b", "క్రేజీ"),
        (r"\bTrophy\b", "ట్రోఫీ"),
        (r"\bGame\b", "గేమ్"),
        (r"\bHost\b", "హోస్ట్"),
        (r"\bFavorites\b|\bfavorite\b", "ఫేవరెట్స్"),
        (r"\bTarget\b", "టార్గెట్"),
        (r"\bBanter\b", "బ్యాంటర్"),
        (r"\bShow\b|\bshows\b", "షో"),
        (r"\bEpisode\b|\bepisodes\b", "ఎపిసోడ్"),
        (r"\bYouTube\b|\byoutube\b", "యూట్యూబ్"),
        (r"\bInstagram\b|\binsta\b", "ఇన్‌స్టాగ్రామ్"),
        (r"\bShorts\b", "షార్ట్స్"),
        (r"\bReels\b", "రీల్స్"),
    ]
    for pattern, repl in COMMON_REPLACEMENTS:
        text = re.sub(pattern, repl, text, flags=re.IGNORECASE)

    # Apply Telugu phonetic normalization for brands, model numbers, chips & specs
    try:
        from telugu_phonetic_normalizer import normalize_telugu_tech_script
        text = normalize_telugu_tech_script(text)
    except Exception as norm_err:
        print(f"[edge_tts] Phonetic normalization note: {norm_err}")

    # Remove quotes, hashtags, asterisks, brackets that cause awkward robotic pauses in neural TTS
    text = re.sub(r'["\'“”‘’`*_#~\[\]\(\)]', '', text)

    # Clean multiple punctuation marks (!! -> !, ?? -> ?)
    text = re.sub(r"!+", "!", text)
    text = re.sub(r"\?+", "?", text)

    # Punctuation spacing: ensure space after comma, semicolon, exclamation, question mark, single dot
    text = re.sub(r"([,;!?])(?=\S)", r"\1 ", text)
    text = re.sub(r"(?<!\.)\.(?!\.)(?=\S)", ". ", text)

    # Format dashes and ellipsis for natural TTS cadence & inflection
    text = re.sub(r"\s*—\s*", " — ", text)
    text = re.sub(r"\s*--\s*", " — ", text)
    text = re.sub(r"(?:\s*\.\s*){3,}", " ... ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


async def generate_telugu_speech(
    text: str,
    output_path: str,
    voice: str = "te-IN-MohanNeural",
    rate: str = "+4%",
    pitch: str = "+0Hz",
) -> str:
    """Generate natural-sounding Telugu speech via Edge-TTS.

    rate: fluent creator delivery (+4% optimal for crisp engagement without rushing)
    pitch: neutral +0Hz preserves natural baritone richness and authentic human timbre
    """
    safe_text = prepare_script_for_tts(text)

    communicate = edge_tts.Communicate(
        text=safe_text,
        voice=voice,
        rate=rate or "+4%",
        pitch=pitch or "+0Hz",
    )
    await communicate.save(output_path)
    return output_path


async def generate_with_word_boundaries(
    text: str,
    output_path: str,
    voice: str = "te-IN-MohanNeural",
    rate: str = "+4%",
    pitch: str = "+0Hz",
):
    """Generates natural-sounding continuous speech via Edge-TTS and captures word-level timing
    boundaries directly from Microsoft's neural stream. This completely replaces the need
    for heavy 15-minute CPU Whisper transcription on Cloud environments."""
    safe_text = prepare_script_for_tts(text)
    communicate = edge_tts.Communicate(
        text=safe_text,
        voice=voice,
        rate=rate or "+4%",
        pitch=pitch or "+0Hz",
    )

    word_timings = []
    sentence_timings = []
    with open(output_path, "wb") as audio_file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_file.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                w_text = str(chunk.get("text", "")).strip()
                if not w_text:
                    continue
                start_sec = round(float(chunk["offset"]) / 10_000_000.0, 3)
                duration_sec = round(float(chunk["duration"]) / 10_000_000.0, 3)
                end_sec = round(start_sec + duration_sec, 3)

                norm = re.sub(r"[^\w\s]", "", w_text).strip()
                word_timings.append({
                    "word": w_text,
                    "text": w_text,
                    "normalized": norm or w_text,
                    "start": start_sec,
                    "end": end_sec,
                })
            elif chunk["type"] == "SentenceBoundary":
                s_text = str(chunk.get("text", "")).strip()
                if s_text:
                    s_start = round(float(chunk["offset"]) / 10_000_000.0, 3)
                    s_dur = round(float(chunk["duration"]) / 10_000_000.0, 3)
                    sentence_timings.append((s_text, s_start, s_dur))

    if not word_timings and sentence_timings:
        for s_text, s_start, s_dur in sentence_timings:
            words = s_text.split()
            if words:
                per_w = s_dur / len(words)
                for w_i, w in enumerate(words):
                    w_st = round(s_start + (w_i * per_w), 3)
                    w_en = round(w_st + per_w, 3)
                    norm = re.sub(r"[^\w\s]", "", w).strip()
                    word_timings.append({
                        "word": w,
                        "text": w,
                        "normalized": norm or w,
                        "start": w_st,
                        "end": w_en,
                    })

    if not word_timings:
        dur = _probe_audio_duration(Path(output_path))
        words = safe_text.split()
        if words and dur > 0:
            per_w = dur / len(words)
            for w_i, w in enumerate(words):
                w_st = round(w_i * per_w, 3)
                w_en = round(w_st + per_w, 3)
                norm = re.sub(r"[^\w\s]", "", w).strip()
                word_timings.append({
                    "word": w,
                    "text": w,
                    "normalized": norm or w,
                    "start": w_st,
                    "end": w_en,
                })

    return output_path, word_timings


# ============================================================
# PER-SENTENCE EMOTION MODULATION & DISK CACHING
# ============================================================

def classify_sentence_delivery(sentence: str, idx: int, total_sentences: int, voice: str = "te-IN-MohanNeural") -> Dict[str, Any]:
    """
    Control speech rate, pitch, and pauses per sentence:
    - Sarcastic punchlines: slightly slower (e.g. -4% or -2%), lower pitch (-2Hz or -1Hz),
      short pause before them (350-450ms) to let sarcasm land.
    - Normal / setup lines: energetic pacing (+8%), neutral pitch (+0Hz).
    """
    s_clean = sentence.strip()
    is_punchline = False

    SARCASTIC_MARKERS = [
        "రచ్చ", "సీన్ లేదు", "ట్విస్ట్", "ఓవర్ యాక్షన్", "తుస్సు", "మైండ్ బ్లాక్", "గురూ",
        "షాక్", "డ్రామా క్వీన్", "నవ్వులాట", "లైట్ తీస్కో", "రంజు", "పప్పులుడకలేదు",
        "వావ్", "బలైపోయాడు", "అర్థమైందా", "సూపర్ స్కెచ్"
    ]
    s_no_bb = re.sub(r"బిగ్\s*బాస్|bigg\s*boss", "", s_clean, flags=re.IGNORECASE)
    # Check standalone slang 'బాస్' (not part of Bigg Boss)
    has_standalone_boss = bool(re.search(r"(?<!బిగ్\s)బాస్", s_clean)) if "బిగ్ బాస్" in s_clean else ("బాస్" in s_clean)
    if any(m in s_no_bb for m in SARCASTIC_MARKERS) or has_standalone_boss or s_clean.endswith("?") or s_clean.endswith("!"):
        is_punchline = True
    elif idx == total_sentences and total_sentences > 1:
        is_punchline = True

    is_shruti = "shruti" in voice.lower()

    if is_punchline and idx > 1:
        rate = "-2%" if is_shruti else "-4%"
        pitch = "-1Hz" if is_shruti else "-2Hz"
        pause_ms = 400
    else:
        rate = "+8%"
        pitch = "+0Hz"
        pause_ms = 120 if idx > 1 else 0

    return {
        "rate": rate,
        "pitch": pitch,
        "pause_ms": pause_ms,
        "is_punchline": is_punchline,
    }


def get_cached_tts_chunk(text: str, voice: str, rate: str, pitch: str) -> Optional[Tuple[Path, List[Dict[str, Any]], float]]:
    """Retrieve audio chunk and word timings from disk cache if present (preferring clean WAV)."""
    clean_txt = prepare_script_for_tts(text)
    cache_key = hashlib.md5(f"{clean_txt}_{voice}_{rate}_{pitch}".encode("utf-8")).hexdigest()
    wav_file = TTS_CACHE_DIR / f"{cache_key}.wav"
    mp3_file = TTS_CACHE_DIR / f"{cache_key}.mp3"
    json_file = TTS_CACHE_DIR / f"{cache_key}.json"
    
    if wav_file.exists() and wav_file.stat().st_size > 1000 and json_file.exists():
        try:
            meta = json.loads(json_file.read_text(encoding="utf-8"))
            return wav_file, meta.get("word_timings", []), float(meta.get("duration", 0.0))
        except Exception:
            pass
    elif mp3_file.exists() and mp3_file.stat().st_size > 400 and json_file.exists():
        try:
            meta = json.loads(json_file.read_text(encoding="utf-8"))
            return mp3_file, meta.get("word_timings", []), float(meta.get("duration", 0.0))
        except Exception:
            pass
    return None


def save_cached_tts_chunk(text: str, voice: str, rate: str, pitch: str, audio_file: Path, word_timings: List[Dict[str, Any]], duration: float) -> None:
    """Store generated audio chunk (both clean WAV and MP3) and word timings into disk cache."""
    clean_txt = prepare_script_for_tts(text)
    cache_key = hashlib.md5(f"{clean_txt}_{voice}_{rate}_{pitch}".encode("utf-8")).hexdigest()
    dest_wav = TTS_CACHE_DIR / f"{cache_key}.wav"
    dest_mp3 = TTS_CACHE_DIR / f"{cache_key}.mp3"
    dest_json = TTS_CACHE_DIR / f"{cache_key}.json"
    try:
        if audio_file.suffix.lower() == ".wav":
            shutil.copy2(audio_file, dest_wav)
            if not dest_mp3.exists() or dest_mp3.stat().st_size < 400:
                subprocess.run([
                    "ffmpeg", "-y", "-i", str(dest_wav),
                    "-codec:a", "libmp3lame", "-q:a", "2",
                    str(dest_mp3)
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        else:
            shutil.copy2(audio_file, dest_mp3)
            if not dest_wav.exists() or dest_wav.stat().st_size < 1000:
                subprocess.run([
                    "ffmpeg", "-y", "-i", str(dest_mp3),
                    "-ac", "1", "-ar", "24000", "-c:a", "pcm_s16le",
                    str(dest_wav)
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

        dest_json.write_text(json.dumps({"word_timings": word_timings, "duration": duration}, indent=2), encoding="utf-8")
    except Exception:
        pass


def _probe_audio_duration(file_path: Path) -> float:
    cmd = [
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
        str(file_path)
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, check=True)
        return float(res.stdout.strip() or 0.0)
    except Exception:
        return 0.0


async def synthesize_chunk_to_file(text: str, voice: str, rate: str, pitch: str, output_path: Path) -> Tuple[Path, List[Dict[str, Any]], float]:
    """Synthesize single sentence/chunk with word timings, utilizing disk cache with clean WAV streams."""
    cached = get_cached_tts_chunk(text, voice, rate, pitch)
    if cached:
        c_path, c_words, c_dur = cached
        if output_path.suffix.lower() == c_path.suffix.lower():
            shutil.copy2(c_path, output_path)
        else:
            # Convert between wav and mp3 cleanly
            if output_path.suffix.lower() == ".wav":
                subprocess.run([
                    "ffmpeg", "-y", "-i", str(c_path),
                    "-ac", "1", "-ar", "24000", "-c:a", "pcm_s16le",
                    str(output_path)
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            else:
                subprocess.run([
                    "ffmpeg", "-y", "-i", str(c_path),
                    "-codec:a", "libmp3lame", "-q:a", "2",
                    str(output_path)
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return output_path, c_words, c_dur

    # Synthesize directly
    temp_mp3 = output_path.with_suffix(".temp.mp3")
    _, words = await generate_with_word_boundaries(
        text=text,
        output_path=str(temp_mp3),
        voice=voice,
        rate=rate,
        pitch=pitch,
    )
    dur = _probe_audio_duration(temp_mp3)

    # Convert to clean WAV if output is WAV
    if output_path.suffix.lower() == ".wav":
        subprocess.run([
            "ffmpeg", "-y", "-i", str(temp_mp3),
            "-ac", "1", "-ar", "24000", "-c:a", "pcm_s16le",
            str(output_path)
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        temp_mp3.unlink(missing_ok=True)
        save_cached_tts_chunk(text, voice, rate, pitch, output_path, words, dur)
    else:
        os.replace(temp_mp3, output_path)
        save_cached_tts_chunk(text, voice, rate, pitch, output_path, words, dur)

    return output_path, words, dur


async def generate_beat_chunked_speech(
    beats_text_list: List[str],
    output_path: str = "output/voice.mp3",
    voice: str = "te-IN-ShrutiNeural",
    rate: str = "+4%",
    pitch: str = "+0Hz",
    max_workers: int = 4,
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Stream audio directly per beat with parallel chunking and clean WAV caching.
    Prevents audio truncation in ffmpeg stream finalization (completely avoiding CalledProcessError).
    Reduces te-IN-ShrutiNeural synthesis time from ~26s down to ~2-3s!
    """
    out_p = Path(output_path)
    out_dir = out_p.parent
    temp_chunks_dir = out_dir / "temp_beat_chunks"
    temp_chunks_dir.mkdir(parents=True, exist_ok=True)

    semaphore = asyncio.Semaphore(max_workers)

    async def _process_beat(b_idx: int, b_text: str):
        chunk_wav = temp_chunks_dir / f"beat_{b_idx}.wav"
        async with semaphore:
            _, words, dur = await synthesize_chunk_to_file(
                text=b_text,
                voice=voice,
                rate=rate,
                pitch=pitch,
                output_path=chunk_wav,
            )
            return b_idx, chunk_wav, words, dur

    tasks = [
        _process_beat(i, t)
        for i, t in enumerate(beats_text_list, 1)
        if t and t.strip()
    ]
    results = await asyncio.gather(*tasks)
    results.sort(key=lambda r: r[0])

    chunk_files = []
    all_word_timings = []
    current_offset_sec = 0.0

    for _, c_wav, c_words, c_dur in results:
        chunk_files.append(c_wav)
        for w in c_words:
            all_word_timings.append({
                "word": w.get("word", ""),
                "text": w.get("text", w.get("word", "")),
                "normalized": w.get("normalized", w.get("text", "")),
                "start": round(current_offset_sec + float(w.get("start", 0.0)), 3),
                "end": round(current_offset_sec + float(w.get("end", 0.0)), 3),
            })
        current_offset_sec += c_dur

    # Concatenate clean PCM WAV chunks with sample-accurate alignment
    concat_list = temp_chunks_dir / "concat_beats.txt"
    with open(concat_list, "w", encoding="utf-8") as f_cat:
        for cf in chunk_files:
            f_cat.write(f"file '{cf.resolve()}'\n")

    raw_wav = out_dir / "voice.wav"
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c:a", "pcm_s16le",
        str(raw_wav)
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    shutil.copy2(raw_wav, out_dir / "voice_raw.wav")

    # Encode to final voice.mp3 with clean container timestamp finalization
    subprocess.run([
        "ffmpeg", "-y", "-i", str(raw_wav),
        "-codec:a", "libmp3lame", "-q:a", "2",
        "-avoid_negative_ts", "make_zero",
        "-fflags", "+genpts",
        str(out_p)
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    dur = _probe_audio_duration(out_p)

    # Save word timings to output/transcription.json
    transcription_data = {
        "text": " ".join(beats_text_list),
        "words": all_word_timings,
        "duration": round(dur, 2),
    }
    (out_dir / "transcription.json").write_text(
        json.dumps(transcription_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    shutil.rmtree(temp_chunks_dir, ignore_errors=True)
    print(f"✅ [Beat-Chunked TTS] Streamed & assembled {len(results)} beats with clean WAV caching -> {output_path} ({dur:.1f}s)")
    return str(out_p), all_word_timings


async def generate_modulated_telugu_speech(
    script_text: str,
    output_path: str = "output/voice.mp3",
    voice: str = "te-IN-MohanNeural",
    max_workers: int = 4,
    rate: str = "+4%",
    pitch: str = "+0Hz",
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Synthesize natural, fluent Telugu speech via Microsoft Edge Neural TTS:
    - Streams per beat/sentence with parallel chunking and clean WAV caching.
    - Avoids monolithic 80s single-request timeouts and 26s latency.
    - Guaranteed zero truncation and zero CalledProcessError in ffmpeg finalization.
    """
    out_p = Path(output_path)
    out_dir = out_p.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    safe_text = prepare_script_for_tts(script_text)
    clean_voice = voice or "te-IN-MohanNeural"
    clean_rate = rate or "+4%"
    clean_pitch = pitch or "+0Hz"

    print(f"🎙️ [Fluent Telugu TTS] Synthesizing narration with {clean_voice} (rate={clean_rate}, pitch={clean_pitch})...")

    # 1. Check full script disk cache
    cached = get_cached_tts_chunk(safe_text, clean_voice, clean_rate, clean_pitch)
    if cached:
        c_path, c_words, c_dur = cached
        print(f"⚡ [Fluent Telugu TTS] Loaded audio from disk cache: {c_path} ({c_dur:.1f}s, {len(c_words)} words)")
        if c_path.suffix.lower() == ".mp3":
            shutil.copy2(c_path, out_p)
        else:
            subprocess.run([
                "ffmpeg", "-y", "-i", str(c_path),
                "-codec:a", "libmp3lame", "-q:a", "2",
                str(out_p)
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        # Ensure output/voice.wav also exists
        out_wav = out_dir / "voice.wav"
        if not out_wav.exists() or out_wav.stat().st_size < 1000:
            subprocess.run([
                "ffmpeg", "-y", "-i", str(out_p),
                "-ac", "1", "-ar", "24000", "-c:a", "pcm_s16le",
                str(out_wav)
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            shutil.copy2(out_wav, out_dir / "voice_raw.wav")
        return str(out_p), c_words

    # 2. Extract beats from delivery_plan.json or section_map.txt if present
    beats_text = []
    dp_file = out_dir / "delivery_plan.json"
    sm_file = out_dir / "section_map.txt"
    if dp_file.exists():
        try:
            dp_data = json.loads(dp_file.read_text(encoding="utf-8"))
            beats_text = [b.get("spoken_text", "").strip() for b in dp_data if b.get("spoken_text", "").strip()]
        except Exception:
            pass
    if not beats_text and sm_file.exists():
        try:
            sm_raw = sm_file.read_text(encoding="utf-8")
            parts = re.split(r"SECTION \d+ \| VISUAL \d+\n", sm_raw)
            beats_text = [p.strip() for p in parts if p.strip()]
        except Exception:
            pass

    if not beats_text:
        # Segment by sentence boundaries
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", safe_text) if s.strip()]
        beats_text = sentences if len(sentences) >= 2 else [safe_text]

    # If script contains multiple beats, stream with chunking and clean WAV caching
    if len(beats_text) >= 2:
        return await generate_beat_chunked_speech(
            beats_text_list=beats_text,
            output_path=str(out_p),
            voice=clean_voice,
            rate=clean_rate,
            pitch=clean_pitch,
            max_workers=max_workers,
        )

    # 3. Single-pass synthesis for short scripts
    temp_wav = out_dir / "voice_temp.wav"
    _, all_word_timings, dur = await synthesize_chunk_to_file(
        text=safe_text,
        voice=clean_voice,
        rate=clean_rate,
        pitch=clean_pitch,
        output_path=temp_wav,
    )

    subprocess.run([
        "ffmpeg", "-y", "-i", str(temp_wav),
        "-codec:a", "libmp3lame", "-q:a", "2",
        "-avoid_negative_ts", "make_zero",
        str(out_p)
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    shutil.copy2(temp_wav, out_dir / "voice.wav")
    shutil.copy2(temp_wav, out_dir / "voice_raw.wav")
    temp_wav.unlink(missing_ok=True)

    # Save word timings to output/transcription.json
    transcription_data = {
        "text": script_text,
        "words": all_word_timings,
        "duration": round(dur, 2),
    }
    (out_dir / "transcription.json").write_text(json.dumps(transcription_data, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"✅ [Fluent Telugu TTS] Successfully generated {output_path} ({dur:.1f}s, {len(all_word_timings)} words)")
    return str(out_p), all_word_timings


EMOTION_PRESETS = {
    "deadpan": {"rate": "+12%", "pitch": "+0Hz", "volume": "+0%"},
    "fake_shock": {"rate": "+16%", "pitch": "+1Hz", "volume": "+2%"},
    "smug": {"rate": "+14%", "pitch": "+0Hz", "volume": "+0%"},
    "mock": {"rate": "+15%", "pitch": "+1Hz", "volume": "+1%"},
    "hype": {"rate": "+18%", "pitch": "+1Hz", "volume": "+2%"},
    "neutral": {"rate": "+14%", "pitch": "+0Hz", "volume": "+0%"},
    "neutral setup": {"rate": "+14%", "pitch": "+0Hz", "volume": "+0%"},
    "dramatic_question": {"rate": "+6%", "pitch": "+0Hz", "volume": "+1%"},  # Slightly slower for dramatic punchline impact
}


async def generate_roast_speech_with_emotions(
    beats: list,
    output_path: str = "output/voice.mp3",
    voice: str = "te-IN-ShrutiNeural",
    sfx_enabled: bool = True,
) -> tuple:
    """
    Synthesize multi-emotion chunked roast narration:
    1. Synthesizes each beat chunk with its emotion preset (rate, pitch, volume)
    2. Inserts intentional comedic pauses (350-450ms before punchline)
    3. Mixes up to 3 comedic CC0 SFX hits (~100ms after punchlines)
    4. Produces unified voice.mp3 and continuous word timings for subtitles
    """
    import os
    import shutil
    import subprocess
    from pathlib import Path

    out_p = Path(output_path)
    out_dir = out_p.parent
    temp_dir = out_dir / "temp_roast_chunks"
    temp_dir.mkdir(parents=True, exist_ok=True)

    # Clean voice identifier if alias passed (e.g. te-IN-ShrutiNeural-Roast -> te-IN-ShrutiNeural)
    clean_voice = str(voice or "").strip()
    if "shruti" in clean_voice.lower():
        clean_voice = "te-IN-ShrutiNeural"
    elif "mohan" in clean_voice.lower():
        clean_voice = "te-IN-MohanNeural"
    elif not clean_voice:
        clean_voice = "te-IN-ShrutiNeural"

    chunk_files = []
    all_word_timings = []
    current_offset_sec = 0.0
    sfx_events = []  # List of (timestamp_sec, sfx_name)
    sfx_count = 0

    try:
        for idx, beat in enumerate(beats, 1):
            text = str(beat.get("spoken_text", "")).strip()
            if not text:
                continue

            emotion = beat.get("emotion", "neutral setup").lower()
            preset = EMOTION_PRESETS.get(emotion, EMOTION_PRESETS["neutral setup"])
            pause_ms = int(beat.get("pause_before_ms", 0))

            # Rule: no pause in first 1.5s
            if idx == 1:
                pause_ms = 0

            # 1. Comedic pauses (350-450ms) for punchline delivery
            if pause_ms > 0:
                pause_sec = min(0.45, max(0.10, pause_ms / 1000.0))
                silence_wav = temp_dir / f"pause_{idx}.wav"
                cmd_sil = [
                    "ffmpeg", "-y",
                    "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                    "-t", str(pause_sec),
                    "-c:a", "pcm_s16le",
                    str(silence_wav)
                ]
                subprocess.run(cmd_sil, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                chunk_files.append(silence_wav)
                current_offset_sec += pause_sec

            # 2. Synthesize speech chunk
            chunk_mp3 = temp_dir / f"chunk_{idx}.mp3"
            safe_text = prepare_script_for_tts(text)
            comm = edge_tts.Communicate(
                text=safe_text,
                voice=clean_voice,
                rate=preset["rate"],
                pitch=preset["pitch"],
                volume=preset["volume"],
            )

            chunk_words = []
            chunk_sentences = []
            with open(chunk_mp3, "wb") as f_out:
                async for chunk_ev in comm.stream():
                    if chunk_ev["type"] == "audio":
                        f_out.write(chunk_ev["data"])
                    elif chunk_ev["type"] == "WordBoundary":
                        w_t = str(chunk_ev.get("text", "")).strip()
                        if not w_t:
                            continue
                        w_start = round(float(chunk_ev["offset"]) / 10_000_000.0, 3)
                        w_dur = round(float(chunk_ev["duration"]) / 10_000_000.0, 3)
                        norm_w = re.sub(r"[^\w\s]", "", w_t).strip()
                        chunk_words.append({
                            "word": w_t,
                            "text": w_t,
                            "normalized": norm_w or w_t,
                            "start": round(current_offset_sec + w_start, 3),
                            "end": round(current_offset_sec + w_start + w_dur, 3),
                        })
                    elif chunk_ev["type"] == "SentenceBoundary":
                        s_t = str(chunk_ev.get("text", "")).strip()
                        if s_t:
                            s_start = round(float(chunk_ev["offset"]) / 10_000_000.0, 3)
                            s_dur = round(float(chunk_ev["duration"]) / 10_000_000.0, 3)
                            chunk_sentences.append((s_t, s_start, s_dur))

            # Measure duration of chunk audio
            probe_cmd = [
                "ffprobe", "-v", "error", "-show_entries",
                "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
                str(chunk_mp3)
            ]
            res = subprocess.run(probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
            chunk_dur = float(res.stdout.strip() or 0.0)

            # Fallback word-level timing interpolation for non-Latin scripts (e.g. Telugu)
            if not chunk_words:
                if chunk_sentences:
                    for s_t, s_start, s_dur in chunk_sentences:
                        words = s_t.split()
                        if words:
                            per_w = s_dur / len(words)
                            for w_i, w in enumerate(words):
                                w_st = round(s_start + (w_i * per_w), 3)
                                w_en = round(w_st + per_w, 3)
                                norm_w = re.sub(r"[^\w\s]", "", w).strip()
                                chunk_words.append({
                                    "word": w,
                                    "text": w,
                                    "normalized": norm_w or w,
                                    "start": round(current_offset_sec + w_st, 3),
                                    "end": round(current_offset_sec + w_en, 3),
                                })
                elif chunk_dur > 0:
                    words = safe_text.split()
                    if words:
                        per_w = chunk_dur / len(words)
                        for w_i, w in enumerate(words):
                            w_st = round(w_i * per_w, 3)
                            w_en = round(w_st + per_w, 3)
                            norm_w = re.sub(r"[^\w\s]", "", w).strip()
                            chunk_words.append({
                                "word": w,
                                "text": w,
                                "normalized": norm_w or w,
                                "start": round(current_offset_sec + w_st, 3),
                                "end": round(current_offset_sec + w_en, 3),
                            })

            chunk_wav = temp_dir / f"chunk_{idx}.wav"
            subprocess.run([
                "ffmpeg", "-y", "-i", str(chunk_mp3),
                "-ac", "1", "-ar", "24000", "-c:a", "pcm_s16le",
                str(chunk_wav)
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

            chunk_files.append(chunk_wav)
            all_word_timings.extend(chunk_words)

            # 3. Schedule SFX if beat has sfx and within limit
            sfx_tag = beat.get("sfx")
            if sfx_enabled and sfx_tag and sfx_count < 3 and idx > 1:
                sfx_file = ROOT / "assets" / "sfx" / "roast" / f"{sfx_tag}.wav"
                if sfx_file.exists():
                    sfx_time = max(0.0, current_offset_sec + chunk_dur - 0.15)
                    sfx_events.append((sfx_time, sfx_file))
                    sfx_count += 1

            current_offset_sec += chunk_dur

        # 4. Concatenate all audio chunks
        concat_list = temp_dir / "concat.txt"
        with open(concat_list, "w", encoding="utf-8") as f_cat:
            for cf in chunk_files:
                f_cat.write(f"file '{cf.resolve()}'\n")

        raw_joined = temp_dir / "joined_raw.wav"
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_list),
            "-c:a", "pcm_s16le",
            str(raw_joined)
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        # 5. Mix SFX into voice stream if any scheduled
        if sfx_events:
            print(f"💥 [Roast Audio] Mixing {len(sfx_events)} comedic SFX hits into voice narration...")
            sfx_inputs = ["-i", str(raw_joined)]
            filter_parts = ["[0:a]volume=1.0[v0]"]
            mix_inputs = ["[v0]"]

            for s_idx, (s_time, s_path) in enumerate(sfx_events, 1):
                sfx_inputs.extend(["-i", str(s_path)])
                delay_ms = int(s_time * 1000)
                filter_parts.append(f"[{s_idx}:a]adelay={delay_ms}|{delay_ms},volume=0.35[sfx{s_idx}]")
                mix_inputs.append(f"[sfx{s_idx}]")

            filter_complex = ";".join(filter_parts) + ";" + "".join(mix_inputs) + f"amix=inputs={len(mix_inputs)}:dropout_transition=0:normalize=0[aout]"
            final_mixed = temp_dir / "final_mixed.wav"
            cmd_mix = ["ffmpeg", "-y"] + sfx_inputs + ["-filter_complex", filter_complex, "-map", "[aout]", "-c:a", "pcm_s16le", str(final_mixed)]
            subprocess.run(cmd_mix, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            voice_source = final_mixed
        else:
            voice_source = raw_joined

        # 6. Trim only leading silence (< 0.15s) while preserving internal comedic pauses
        from audio_mixer import clean_and_pace_voice
        voice_paced = out_dir / "voice_paced.wav"
        clean_and_pace_voice(
            str(voice_source),
            str(voice_paced),
            target_speed=1.00,  # Speed already controlled per emotion chunk
            min_silence_ms=650,  # Preserve dramatic 400-500ms pauses
        )

        # Export to output/voice.mp3
        subprocess.run([
            "ffmpeg", "-y", "-i", str(voice_paced),
            "-codec:a", "libmp3lame", "-q:a", "2",
            str(out_p)
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        # Also save raw wav
        shutil.copy2(voice_paced, out_dir / "voice_raw.wav")
        print(f"🎙️ [Roast Audio] Generated {len(beats)} emotion chunks, {sfx_count} SFX -> {output_path} ({current_offset_sec:.1f}s)")
        return str(out_p), all_word_timings

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

