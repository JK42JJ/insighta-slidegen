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

from pathlib import Path


FRAME_RATE = 1  # frames per second extracted from video


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

    TODO: implement yt-dlp subprocess + opencv frame extraction loop.
    """
    raise NotImplementedError(
        f"TODO: download_frames youtube_video_id={youtube_video_id}"
    )
