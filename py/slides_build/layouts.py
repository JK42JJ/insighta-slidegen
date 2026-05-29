"""
Google Slides layout helpers.

Maps insighta-slidegen layout names to Slides API request shapes.
Each layout function returns a list of Slides API AnyType request dicts
suitable for batchUpdate().

Layout names must match LayoutEnum in src/types/slide-manifest.ts.
"""

from __future__ import annotations

from typing import Any

# Slides API placeholder object id prefix (must be unique per presentation)
_OBJ_PREFIX = "slidegen"


def make_cover_requests(
    slide_object_id: str,
    title: str,
    one_liner: str,
) -> list[dict[str, Any]]:
    """
    Build batchUpdate requests for a "cover" layout slide.

    Layout: full-bleed title centered + one_liner subtitle below.

    TODO: implement — insertText into title/subtitle placeholder shapes.
    Returns placeholder empty list until implemented.
    """
    # TODO: implement Google Slides batchUpdate request list
    return []


def make_section_intro_requests(
    slide_object_id: str,
    title: str,
    summary: str,
) -> list[dict[str, Any]]:
    """
    Build batchUpdate requests for a "section_intro" layout slide.

    TODO: implement — section title + paragraph summary text.
    """
    return []


def make_key_points_requests(
    slide_object_id: str,
    title: str,
    key_points: list[str],
    max_items: int = 5,
) -> list[dict[str, Any]]:
    """
    Build batchUpdate requests for a "key_points" layout slide.

    Truncates key_points to max_items before inserting.

    TODO: implement — bulleted list insertText requests.
    """
    return []


def make_figure_requests(
    slide_object_id: str,
    image_url: str,
    caption: str | None,
    layout: str,
) -> list[dict[str, Any]]:
    """
    Build batchUpdate requests to insert an image figure into a slide.

    layout: "figure_full" (full bleed) or "figure_caption" (with caption text box).

    TODO: implement — createImage request + optional insertText for caption.
    """
    return []


def make_qa_requests(
    slide_object_id: str,
    question: str,
    answer: str,
) -> list[dict[str, Any]]:
    """
    Build batchUpdate requests for a "qa_pair" layout slide.

    TODO: implement — two text boxes: bold question + answer paragraph.
    """
    return []


def make_summary_requests(
    slide_object_id: str,
    one_liner: str,
    key_concepts: list[str],
) -> list[dict[str, Any]]:
    """
    Build batchUpdate requests for a "summary" layout slide.

    TODO: implement — one_liner title + key_concepts bulleted list.
    """
    return []
