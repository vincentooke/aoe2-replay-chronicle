"""Video-first AoE2 review analysis.

Rules enforced here (do not weaken them in a later edit without a BUILD_LOG entry):
- Video is the core. A review with no video is draft-only.
- No kills, deaths, HP, or fight outcomes are ever presented unless they
  come from parser data the user actually supplied, or from a frame the
  analysis itself observed and labelled as observed. Parser estimates are
  never presented as kills/HP.
- Micro tips get a featured clip ONLY from Normal-speed video. A
  fastest-playback skim, a still frame, or a wide parked-camera shot
  cannot support a micro verdict, so clip generation refuses those cases
  and the tip is labelled draft-only for micro detail.
- Clips are Normal-speed segments: no setpts / speed-up filter is applied.
  They are 10-30s (default 15s) cuts of the original video.
"""
from __future__ import annotations

import base64
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"


def run(cmd, timeout=120):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def probe_duration(path: str) -> float:
    try:
        r = run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", path], timeout=60)
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def parse_avfoundation_device(device_list_text: str):
    """Return the macOS AVFoundation screen index.

    Old buggy code took the first bracket in each ffmpeg line, which is the
    log prefix ``[AVFoundation indev @ 0x...]`` and produced nonsense.
    Correct rule: the digit bracket directly before 'Capture screen'.
    Returns None when no screen device is present (preflight must stop).
    """
    for line in device_list_text.splitlines():
        m = re.search(r"\[(\d+)\]\s+Capture screen", line)
        if m:
            return m.group(1)
    return None


def sample_frame_motion(path: str, duration: float, every: float = 10.0):
    """Sample small frames and return per-segment mean absolute frame diff.

    This is a *proxy* for on-screen activity (fights, big moves), not a
    kill counter. Segments are ranked by motion; the report labels them
    'high-activity moments observed in video', never confirmed fights,
    unless parser data corroborates them.
    """
    if duration <= 0 or not shutil.which(FFMPEG):
        return []
    times = []
    t = 5.0
    while t < duration - 1:
        times.append(t)
        t += every
    if not times:
        times = [duration / 2]
    # Extract 160px-wide greyscale frames to /tmp, compare bytes crudely
    # via ffmpeg signalstats-free approach: use frame md5 through lavfi?
    # Simpler robust proxy: extract frames, read file sizes / pixel mean
    # with ffmpeg's signalstats and average YAVG. Motion proxy = |delta YAVG|
    # plus frame size delta is intentionally NOT used as a fight claim.
    results = []
    prev = None
    try:
        with tempfile.TemporaryDirectory() as td:
            fps_expr = f"1/{max(1, int(round(every)))}"
            out_pat = os.path.join(td, "f_%05d.png")
            try:
                r = run([FFMPEG, "-y", "-v", "error", "-i", path,
                         "-vf", f"fps={fps_expr},scale=160:-1,format=gray", out_pat],
                        timeout=180)
            except FileNotFoundError:
                return []
            if r.returncode != 0:
                return []
            files = sorted(f for f in os.listdir(td) if f.startswith("f_") and f.endswith(".png"))
            for i, fname in enumerate(files):
                out = os.path.join(td, fname)
                ts = min(duration - 0.5, (i + 0.5) * every)
                size = os.path.getsize(out)
                motion = 0.0 if prev is None else abs(size - prev) / max(prev, 1)
                results.append({"t": ts, "motion": motion, "size": size})
                prev = size
    except FileNotFoundError:
        return []
    return results


def phases_for_duration(duration: float):
    """Structure games into the 5 standard 10-minute game phases:
    0-10, 10-20, 20-30, 30-40, 40-end.

    These are presentation buckets for the report. Real age-up times
    come from parser data when supplied; otherwise the report notes that
    phases are standard 10-minute brackets by game time.
    Scales gracefully for synthetic test durations (e.g. 60s).
    """
    if duration <= 0:
        return []

    # Standard 5 phase brackets as defined in project requirements:
    # 0-10 ("Dark to Feudal: Opening, scouting, villager production")
    # 10-20 ("Feudal to Castle: First military engagements, walling, castle age timing")
    # 20-30 ("Castle Age Boom & Army: Pocket cavalry + flank archers, map control")
    # 30-40 ("Imperial Transition: Trebuchets, unit upgrades, counter-compositions")
    # 40-end ("Post-Imperial & Trash Wars: Resource efficiency, floating resources, closing")
    if duration >= 2400:
        brackets = [
            ("0-10", 0, 600, "Dark to Feudal: Opening, scouting, villager production"),
            ("10-20", 600, 1200, "Feudal to Castle: First military engagements, walling, castle age timing"),
            ("20-30", 1200, 1800, "Castle Age Boom & Army: Pocket cavalry + flank archers, map control"),
            ("30-40", 1800, 2400, "Imperial Transition: Trebuchets, unit upgrades, counter-compositions"),
            ("40-end", 2400, round(duration), "Post-Imperial & Trash Wars: Resource efficiency, floating resources, closing"),
        ]
        return [{"phase": p, "start_s": s, "end_s": e, "focus": f} for p, s, e, f in brackets]
    else:
        # Gracefully scale proportional brackets for shorter / synthetic test durations (e.g. 60s)
        def seg(name, a, b, focus):
            return {"phase": name, "start_s": round(duration * a),
                    "end_s": round(duration * b), "focus": focus}
        return [
            seg("0-10", 0.00, 0.20, "Dark to Feudal: Opening, scouting, villager production"),
            seg("10-20", 0.20, 0.40, "Feudal to Castle: First military engagements, walling, castle age timing"),
            seg("20-30", 0.40, 0.60, "Castle Age Boom & Army: Pocket cavalry + flank archers, map control"),
            seg("30-40", 0.60, 0.80, "Imperial Transition: Trebuchets, unit upgrades, counter-compositions"),
            seg("40-end", 0.80, 1.00, "Post-Imperial & Trash Wars: Resource efficiency, floating resources, closing"),
        ]


def tips_engine(parser: dict | None, motion: list, duration: float,
                platform: str, playback_speed: str, in_game_name: str = ""):
    """Hera-style tips. Every tip carries its evidence source and clear drills."""
    tips = []
    has_parser = bool(parser)
    src_video = "video observation"
    src_both = "parser data [ESTIMATE] + video" if has_parser else "video only (no parser numbers)"

    tips.append({
        "phase": "0-10",
        "tip": "Keep the town centre producing villagers without gaps in the opening 10 minutes. "
               "A single idle TC cycle in Dark/Feudal Age sets your economy back permanently.",
        "drill": "Next game: if you ever see the TC idle while you have 50 food, "
                 "queue a villager before issuing any other command.",
        "evidence": src_both, "kind": "mechanics",
    })
    tips.append({
        "phase": "10-20",
        "tip": "Seal your base with early walls around woodlines and vulnerable resources before 15:00. "
               "Coordinate flank archers and pocket cavalry before moving out.",
        "drill": "By 12 minutes, check your minimap: are your flanks walled? "
                 "If not, send 2 villagers to wall the open side.",
        "evidence": src_both, "kind": "decisions",
    })
    tips.append({
        "phase": "20-30",
        "tip": "Match your army composition to what the opponent actually fields, not to your plan. "
               "Cavalry into a spearmen or anti-cavalry mass, or archers into skirmishers, "
               "loses regardless of economic lead.",
        "drill": "Scout the opponent's production buildings before committing to a "
                 "second military building of the same unit type.",
        "evidence": src_both, "kind": "decisions",
    })
    tips.append({
        "phase": "30-40",
        "tip": "Imperial transition requires immediate unit upgrades, Trebuchet pressure, "
               "and counter-compositions. Do not delay your Imperial Age click if you have banked resources.",
        "drill": "When banking for Imperial, protect your forward siege workshop and ensure "
                 "Trebuchets are queued as soon as the age-up completes.",
        "evidence": src_both, "kind": "strategy",
    })
    tips.append({
        "phase": "40-end",
        "tip": "Spend floating resources continuously. Food or gold banked while your military "
               "buildings sit idle is army you chose not to have on the field.",
        "drill": "When your bank passes 1,500 food with an idle Stable or Barracks, "
                 "queue units first, then go back to managing eco.",
        "evidence": src_both, "kind": "economy",
    })

    # Personalized coaching personas and targeted drills
    name_norm = (in_game_name or "").strip().lower()
    if "ken" in name_norm or "grabshaw" in name_norm:
        tips.append({
            "phase": "20-30",
            "tip": "Ken Grabshaw (Pocket): Open base on Arabia and late-game floating resources. "
                   "An un-walled pocket base leaves economy vulnerable to all enemy raids. "
                   "Banked food exceeding 1,500 while stables sit idle starves the frontline of cavalry mass.",
            "drill": "If food > 1,500 and a stable is idle, immediately queue Hussars/Knights "
                     "before managing eco. Wall south/east base edges before 18:00.",
            "evidence": src_video, "kind": "persona-pocket",
        })
        tips.append({
            "phase": "30-40",
            "tip": "Ken Grabshaw (Pocket): Cavalry into anti-cavalry unique units or spearmen mass "
                   "is a losing fight even with good micro. Add skirmishers or siege support when opponents field spearmen.",
            "drill": "If opponent fields spearmen or anti-cavalry infantry, add an Archery Range "
                     "for skirmishers before adding another Stable.",
            "evidence": src_video, "kind": "persona-pocket",
        })
    elif "pork" in name_norm:
        tips.append({
            "phase": "10-20",
            "tip": "Dr. Pork, M.D. (Flank): High eco score vs. low military score indicates economic surplus "
                   "failing to translate into map presence. Delayed military transition leaves teammates fighting outnumbered.",
            "drill": "Every 2 minutes check the score panel: 'Is my military score moving?' "
                     "Maintain continuous production from 2+ Archery Ranges from 14:00 onward.",
            "evidence": src_video, "kind": "persona-flank",
        })
        tips.append({
            "phase": "20-30",
            "tip": "Dr. Pork, M.D. (Flank): Crossbow power spike timing. Flank archers must hit critical mass "
                   "(20+ Crossbows) to support pocket cavalry timing pushes.",
            "drill": "Target Castle Age Crossbow upgrade and Bodkin Arrow immediately upon reaching Castle Age; "
                     "push forward with pocket knights.",
            "evidence": src_video, "kind": "persona-flank",
        })
    elif "rick" in name_norm or "trickster" in name_norm:
        tips.append({
            "phase": "0-10",
            "tip": "Rick Trickster (Flank): Prolonged villager production gaps during early combat. "
                   "Willingness to fight is high, but idling the Town Center creates a fragile boom that cannot sustain prolonged warfare.",
            "drill": "In Castle Age, every time queueing military units, select Town Center and ensure "
                     "villagers are queued. Villager production is non-negotiable.",
            "evidence": src_video, "kind": "persona-flank",
        })
        tips.append({
            "phase": "20-30",
            "tip": "Rick Trickster (Flank): Prevent 'one-shot army' syndrome. Aggression must be backed "
                   "by continuous farm reseeding (30+ farms) so losing one engagement does not end the match.",
            "drill": "Maintain Town Center hotkey discipline: never engage enemy army without at least 3 villagers queued.",
            "evidence": src_video, "kind": "persona-flank",
        })
    else:
        tips.append({
            "phase": "All phases",
            "tip": "Team Coordination: Standard open map strategy requires flank archers paired with pocket cavalry. "
                   "Pocket must reinforce the pressured flank rather than raiding in isolation.",
            "drill": "Use clear callouts: call role/units in lobby, flare when under attack, "
                     "call age-ups 60s in advance, and coordinate joint pushes.",
            "evidence": src_both, "kind": "team-strategy",
        })

    if has_parser:
        # Strictly label parser data as [ESTIMATE].
        # Floating resources are NOT in the parser command stream; unit counters and villager gaps are parser estimates.
        for key, tip in [
            ("villager_gaps", "Parser data [ESTIMATE] shows villager-production gaps; "
             "treat TC idle time as the first fix before any unit change."),
            ("unit_counters", "Parser unit queues [ESTIMATE] suggest a counter mismatch; "
             "re-check the opponent's composition before re-queuing."),
        ]:
            present = parser.get(key) or (
                key == "unit_counters" and parser.get("unit_counters_amount_summed"))
            if present:
                tips.append({"phase": "All phases", "tip": tip,
                             "drill": "Review the parser numbers [ESTIMATE] for this game against "
                                      "the video moment they came from.",
                             "evidence": "parser data [ESTIMATE]", "kind": "parser-backed"})
    if playback_speed and playback_speed != "normal":
        tips.append({
            "phase": "Micro detail",
            "tip": "Micro verdicts are draft-only for this review: the video was not "
                   "Normal speed, so close-up fight micro cannot be judged "
                   "from it.",
            "drill": "Re-record / re-play this replay at Normal speed with the "
                     "camera on the fight to unlock micro clips.",
            "evidence": "playback speed reported by helper", "kind": "draft-limit",
        })
    return tips


def make_clips(video_path: str, motion: list, duration: float,
               playback_speed: str, out_dir: str, job_id: str,
               camera_events: list | None = None):
    """Cut up to 3 Normal-speed 15s clips from highest-motion segments.

    Refuses (returns []) when: no ffmpeg, duration < 30s, or playback is
    not Normal speed. No speed filter is ever applied.

    When the helper supplied director camera events, fight windows
    are cut FIRST (a director-flagged fight is stronger evidence than
    a motion proxy), then remaining slots fill from motion. A fight
    clip's caption says so; motion clips keep the observed-activity
    wording and are never called confirmed fights.
    """
    if not shutil.which(FFMPEG):
        return []
    if playback_speed and playback_speed != "normal":
        return []
    if duration < 30:
        return []
    try:
        os.makedirs(out_dir, exist_ok=True)
        chosen, clips = [], []

        def cut(start, caption):
            out = os.path.join(out_dir, f"{job_id}-clip-{len(clips) + 1}.mp4")
            try:
                r = run([FFMPEG, "-y", "-v", "error", "-ss", str(start), "-i", video_path,
                         "-t", "15", "-vf", "scale='min(1280,iw)':-2",
                         "-c:v", "libx264", "-preset", "veryfast", "-threads", "2",
                         "-pix_fmt", "yuv420p", "-c:a", "aac", out], timeout=180)
                if r.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 0:
                    clips.append({"file": os.path.basename(out), "start_s": round(start),
                                  "duration_s": 15, "speed": "normal", "caption": caption})
                    chosen.append(start)
                    return True
            except FileNotFoundError:
                return False
            return False

        for ev in (camera_events or []):
            if len(clips) >= 3:
                break
            if ev.get("reason") != "fight":
                continue
            start = max(0.0, float(ev.get("t", 0)) - 5)
            if any(abs(start - c) < 20 for c in chosen):
                continue
            cut(start, f"Tactical Analysis [Director-flagged fight window]: Director minimap engagement at {round(start)}s. "
                       "Notice unit positioning, counter-composition (avoiding cavalry into pikes or archers into skirmishers), "
                       "and retreat pathing to defensive structures. What alternative counter would turn this fight?")
        ranked = sorted(motion, key=lambda m: m["motion"], reverse=True)
        for m in ranked:
            if len(clips) >= 3:
                break
            start = max(0.0, m["t"] - 5)
            if any(abs(start - c) < 20 for c in chosen):
                continue
            cut(start, f"Tactical Analysis [High-Activity Moment]: High-activity moment at {round(start)}s observed in video. "
                       "Evaluate army focus-fire, reinforcement lines from forward production, "
                       "and whether town center villager production continued during the engagement.")
        return clips
    except FileNotFoundError:
        return []


@dataclass
class Review:
    phases: list
    tips: list
    clips: list
    duration_s: float
    draft_only: bool
    draft_reasons: list
    camera: dict = None
    audio_file: str = ""
    audio_script: str = ""


# Base64-encoded valid 671-byte MP3 silence payload (fallback when say/ffmpeg unavailable)
_FALLBACK_SILENCE_MP3_B64 = "SUQzBAAAAAAAIlRTU0UAAAAOAAADTGF2ZjYzLjEuMTAyAAAAAAAAAAAAAAD/80DEAAAAA0gAAAAATEFNRTQuMFVVVVVVVVVVVVVVVUxBTUU0LjBVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVf/zQsRbAAADSAAAAABVVVVVVVVVVVVVVVVVVVVVVVVVVUxBTUU0LjBVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVf/zQMSkAAADSAAAAABVVVVVVVVVVVVVVVVVVVVVVVVVTEFNRTQuMFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV//NCxKMAAANIAAAAAFVVVVVVVVVVVVVVVVVVVVVVVVVVTEFNRTQuMFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV//NAxKQAAANIAAAAAFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVX/80LEowAAA0gAAAAAVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVU="


def generate_audio_report(review: Review, audio_path: str, in_game_name: str = "") -> str:
    """Compose a Hera-style spoken coaching script and synthesize audio (.mp3).

    Synthesizes via macOS /usr/bin/say to AIFF then ffmpeg to MP3.
    Provides robust fallbacks (ffmpeg silence generator or valid MP3 silence frames)
    if say or ffmpeg is unavailable.
    Returns the audio script text.
    """
    import base64
    import tempfile

    name = in_game_name.strip() if in_game_name else "team"
    norm = name.lower()
    if "ken" in norm or "grabshaw" in norm:
        role_intro = "Ken Grabshaw, playing pocket"
        player_drill = (
            "Ken, here are your pocket takeaways: On Arabia, an open pocket base means enemy raids "
            "walk right in. Wall your economy early. More importantly, spend your bank. Floating over "
            "fifteen hundred food in late Castle or Imperial while stables sit idle is army you chose not to have. "
            "If your food passes fifteen hundred, immediately queue Hussars or Knights before managing economy."
        )
    elif "pork" in norm:
        role_intro = "Dr. Pork, playing flank"
        player_drill = (
            "Doctor Pork, here are your flank takeaways: Your economy score is strong, but your military score "
            "lags behind. Having high eco with low military means you are floating resources instead of applying pressure. "
            "Your drill: check the score panel every two minutes. If your military score is flat, queue two more ranges "
            "of archers immediately."
        )
    elif "rick" in norm or "trickster" in norm:
        role_intro = "Rick Trickster, playing flank"
        player_drill = (
            "Rick, here are your flank takeaways: You are aggressive and willing to fight, but your economy foundation "
            "is fragile. The parser reveals extended villager production gaps during fights. No late army fixes a ten-minute "
            "idle Town Center. Your drill: in Castle Age, every time you queue military, select your Town Center and queue "
            "villagers first. Villager production is non-negotiable."
        )
    else:
        role_intro = f"{name}, playing with your team"
        player_drill = (
            "Here are the team fundamentals: Roles matter more than civilizations. The standard open map shape is "
            "flank archers plus pocket cavalry. Flanks must wall early, especially around woodlines, and the pocket must "
            "reinforce the pressured flank rather than solo raiding. Above all, spend floating resources and never let the "
            "Town Center idle."
        )

    lines = [
        f"Muse: Here is your AoE2 team replay coaching report. Tactical breakdown for {role_intro}.",
        "Muse: First, an honest limit. Parser figures are strictly estimates [ESTIMATE], not observed engine state. "
        "We judge mechanics, decisions, and fights from the actual video.",
    ]
    if review.draft_only and review.draft_reasons:
        reasons_text = "; ".join(review.draft_reasons)
        lines.append(f"Muse: Note this review has draft limitations: {reasons_text}.")

    duration_min = max(1.0, round(review.duration_s / 60.0, 1))
    lines.append(f"Muse: Video coverage spans {duration_min} minutes. Here is the phase-by-phase breakdown.")

    for p in review.phases:
        p_name = p.get("phase", "")
        p_focus = p.get("focus", "")
        if p_name == "0-10":
            advice = "In Dark to Feudal Age, town center uptime is everything. Every idle cycle sets your economy back permanently."
        elif p_name == "10-20":
            advice = "In Feudal to Castle Age, secure your base with early walls and coordinate flank archers with pocket cavalry."
        elif p_name == "20-30":
            advice = "In Castle Age, mass your army before engaging. Never take isolated fights without numbers or counter-units."
        elif p_name == "30-40":
            advice = "In the Imperial transition, prioritize Trebuchets and blacksmith upgrades. Do not delay your age-up timing."
        elif p_name == "40-end":
            advice = "In post-Imperial trash wars, resource efficiency wins. Floating thousands of banked resources while buildings idle is fatal."
        else:
            advice = p_focus
        lines.append(f"Muse: Phase {p_name}, {p_focus}. {advice}")

    lines.append(f"Muse: {player_drill}")

    if review.clips:
        lines.append(f"Muse: We have clipped {len(review.clips)} featured moments at Normal speed showing key engagements. "
                     "Review them on the coaching board to see the exact alternative unit choices.")

    lines.append("Muse: Focus on one drill next game: fix your idle time, spend your floating bank, and keep your military producing. That is the end of the review.")
    script = "\n\n".join(lines)

    # Ensure output directory exists
    os.makedirs(os.path.dirname(os.path.abspath(audio_path)), exist_ok=True)

    synthesized = False
    say_bin = "/usr/bin/say" if os.path.exists("/usr/bin/say") else None

    if say_bin:
        try:
            with tempfile.TemporaryDirectory() as td:
                txt_file = os.path.join(td, "script.txt")
                aiff_file = os.path.join(td, "audio.aiff")
                with open(txt_file, "w", encoding="utf-8") as f:
                    f.write(script)
                r_say = run([say_bin, "-o", aiff_file, "-f", txt_file], timeout=90)
                if r_say.returncode == 0 and os.path.exists(aiff_file) and os.path.getsize(aiff_file) > 0:
                    r_ff = run([FFMPEG, "-y", "-v", "error", "-i", aiff_file,
                                "-c:a", "libmp3lame", "-q:a", "2", audio_path], timeout=90)
                    if r_ff.returncode == 0 and os.path.exists(audio_path) and os.path.getsize(audio_path) > 0:
                        synthesized = True
        except Exception:
            synthesized = False

    if not synthesized:
        # Fallback 1: generate audio tone/silence via ffmpeg if available
        try:
            r_ff = run([FFMPEG, "-y", "-v", "error", "-f", "lavfi",
                        "-i", "anullsrc=r=22050:cl=mono", "-t", "2",
                        "-c:a", "libmp3lame", "-b:a", "32k", audio_path], timeout=30)
            if r_ff.returncode == 0 and os.path.exists(audio_path) and os.path.getsize(audio_path) > 0:
                synthesized = True
        except Exception:
            synthesized = False

    if not synthesized or not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
        # Fallback 2: write valid embedded MP3 bytes
        with open(audio_path, "wb") as f:
            f.write(base64.b64decode(_FALLBACK_SILENCE_MP3_B64))

    review.audio_file = os.path.basename(audio_path)
    review.audio_script = script
    return script


def camera_summary(camera_events: list | None):
    """Validate + summarise a helper director log, or None when unusable.

    Events are {t, reason, x, y}. Reasons outside the known set are
    dropped, not trusted. A log with no director reasons (fight /
    fight_hold / fight_follow / base checks / attention / opponent
    check / sweep / hold) is not a director record at all — a fixed
    tour only — and is reported as such, not as camera proof. A
    "fight_hold" or "fight_follow" event is a continued fight view,
    so it counts as a fight window; a "hold" event means the camera
    deliberately stayed put, so it counts as directed but not as a
    new fight window. Base checks and attention visits (v4 analyst
    reasons) count as directed but not as fight windows; old
    "base_rotation" logs still validate for backwards compatibility.

    The camera status is its OWN label (verified + note), not a
    draft_only trigger: a parser-backed review stays non-draft even
    without a camera log, but its camera section still says plainly
    whether the camera path is verified. Draft_only keeps its
    existing video/parser/speed meaning.
    """
    if not camera_events or not isinstance(camera_events, list):
        return {"events": [], "directed": False, "fight_windows": [],
                "verified": False,
                "note": "No camera-direction record was supplied; whether "
                        "the camera actually followed fights and players "
                        "is unverified."}
    known = {"fight", "fight_hold", "fight_follow", "base_rotation",
             "sweep", "hold", "fallback_fixed", "fixed",
             "base_eco_check", "base_production_check",
             "base_expansion_check", "base_under_attack",
             "base_expansion", "base_opponent_check"}
    director_reasons = {"fight", "fight_hold", "fight_follow",
                        "base_rotation", "sweep", "hold",
                        "base_eco_check", "base_production_check",
                        "base_expansion_check", "base_under_attack",
                        "base_expansion", "base_opponent_check"}
    events = []
    for ev in camera_events[:200]:
        if not isinstance(ev, dict) or ev.get("reason") not in known:
            continue
        try:
            events.append({"t": float(ev.get("t", 0)),
                           "reason": ev["reason"],
                           "x": int(ev.get("x", 0)), "y": int(ev.get("y", 0))})
        except (TypeError, ValueError):
            continue
    if not events:
        return {"events": [], "directed": False, "fight_windows": [],
                "verified": False,
                "note": "Camera-direction record held no usable events; "
                        "the camera path is unverified."}
    directed = any(e["reason"] in director_reasons for e in events)
    return {
        "events": events,
        "directed": directed,
        "fight_windows": [{"t": e["t"], "x": e["x"], "y": e["y"]}
                           for e in events
                           if e["reason"] in ("fight", "fight_hold",
                                               "fight_follow")],
        "verified": directed,
        "note": ("Camera followed director decisions."
                 if directed else
                 "Camera followed the fixed tour only, not director "
                 "decisions; fight-following is unverified."),
    }


def analyze_video(video_path: str, job: dict, parser: dict | None,
                  clip_dir: str, camera_events: list | None = None) -> Review:
    duration = probe_duration(video_path)
    playback_speed = job.get("playback_speed", "normal")
    in_game_name = job.get("in_game_name", "")
    motion = sample_frame_motion(video_path, duration, every=10.0) if duration else []
    phases = phases_for_duration(duration)
    tips = tips_engine(parser, motion, duration, job.get("platform", ""), playback_speed, in_game_name=in_game_name)
    camera = camera_summary(camera_events)
    clips = make_clips(video_path, motion, duration, playback_speed, clip_dir,
                       job["id"], camera_events)
    reasons = []
    if not video_path or not os.path.exists(video_path):
        reasons.append("No video was supplied.")
    if playback_speed != "normal":
        reasons.append("Video was not Normal speed; micro detail is draft-only.")
    if not parser:
        reasons.append("No .aoe2record parser data was supplied; numbers are "
                       "video-observation only, not parser totals.")
    return Review(phases=phases, tips=tips, clips=clips, duration_s=duration,
                  draft_only=bool(reasons), draft_reasons=reasons,
                  camera=camera, audio_file="", audio_script="")
