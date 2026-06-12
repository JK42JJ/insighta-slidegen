"""
Frame acquisition module.

Downloads video frames for the requested time sections using yt-dlp + opencv.
Output: directory of JPEG frames at 1-fps (adjustable) for scene detection.

Entry function: download_frames(youtube_video_id, sections) → frames_dir

Algorithm:
    1. yt-dlp: download video to /tmp/slidegen-frames/<video_id>/video.mp4
       (skip if already cached from a previous job in the same process lifetime).
    2. opencv VideoCapture: seek to each section [from_sec, to_sec], extract
       frames at FRAME_RATE fps (default 1), write as JPEG.
    3. Return pathlib.Path to the frames directory.

Mode note: this module has no vision API calls; mode gate is irrelevant here.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import cv2


FRAME_RATE = 1  # frames per second extracted from video

# Residential-egress rule: yt-dlp runs on the Mac Mini ONLY, and goes out via
# the Webshare proxy rather than the bare home IP. Full proxy URL
# (http://user:pass@host:port) injected at service launch; unset = direct
# (existing behavior — env default stays a no-op per the config rollback rule).
ENV_YTDLP_PROXY = "SLIDEGEN_YTDLP_PROXY"


def download_frames(
    youtube_video_id: str,
    sections: list[dict],
    output_root: str = "/tmp/slidegen-frames",
) -> Path:
    """
    Download and extract frames for each section.

    Args:
        youtube_video_id: 11-char YouTube video id.
        sections: list of {"index": int, "from_sec": float, "to_sec": float}.
        output_root: base directory for frame storage.

    Returns:
        Path to directory containing extracted JPEG frames,
        named <timestamp_sec>_<section_index>.jpg.
    """
    frames_dir = Path(output_root) / youtube_video_id
    frames_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: Download video (cached if exists)
    video_path = frames_dir / "video.mp4"
    if not video_path.exists():
        _download_video(youtube_video_id, video_path)

    # Step 2: Extract frames for each section
    for section in sections:
        _extract_section_frames(video_path, section, frames_dir)

    return frames_dir


def _download_video(youtube_video_id: str, output_path: Path) -> None:
    """Download video from YouTube using yt-dlp (proxied when configured)."""
    url = f"https://www.youtube.com/watch?v={youtube_video_id}"
    cmd = [
        "yt-dlp",
        "-f",
        "bestvideo[height<=720][ext=mp4]/bestvideo[height<=720]/best[height<=720]",
        "-o",
        str(output_path),
        "--no-playlist",
    ]
    proxy = os.environ.get(ENV_YTDLP_PROXY, "")
    if proxy:
        cmd += ["--proxy", proxy]
    cmd.append(url)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp failed: {result.stderr}")


def _extract_section_frames(
    video_path: Path, section: dict, frames_dir: Path
) -> None:
    """Extract frames from a video section using opencv."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open video: {video_path}")

    from_sec = section["from_sec"]
    to_sec = section["to_sec"]
    section_index = section["index"]

    # Seek to start of section
    cap.set(cv2.CAP_PROP_POS_MSEC, from_sec * 1000)

    t = from_sec
    while t < to_sec:
        ret, frame = cap.read()
        if not ret:
            break

        # Get current timestamp (in seconds)
        timestamp_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
        timestamp_sec = int(timestamp_ms / 1000)

        # Write frame to JPEG
        out_path = frames_dir / f"{timestamp_sec}_{section_index}.jpg"
        cv2.imwrite(str(out_path), frame)

        # Advance by FRAME_RATE seconds
        next_ms = (t + FRAME_RATE) * 1000
        cap.set(cv2.CAP_PROP_POS_MSEC, next_ms)
        t += FRAME_RATE

    cap.release()
