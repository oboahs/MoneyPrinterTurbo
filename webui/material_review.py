from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

from app.models.schema import MaterialInfo, VideoAspect
from app.services import material


MAX_REVIEW_ITEMS = 24


def normalize_terms(value: Any) -> list[str]:
    """Normalize WebUI keyword input into an ordered, de-duplicated term list."""
    if isinstance(value, str):
        raw_terms = re.split(r"[,，\n]", value)
    elif isinstance(value, (list, tuple)):
        raw_terms = value
    else:
        raw_terms = []

    terms: list[str] = []
    seen: set[str] = set()
    for raw_term in raw_terms:
        term = str(raw_term or "").strip()
        if not term:
            continue
        normalized_key = term.casefold()
        if normalized_key in seen:
            continue
        seen.add(normalized_key)
        terms.append(term)
    return terms


def build_review_fingerprint(
    *,
    source: str,
    video_aspect: VideoAspect | str,
    video_script: str,
    video_terms: Any,
    clip_duration: int,
    video_count: int,
    match_script_order: bool,
) -> str:
    aspect = VideoAspect(video_aspect)
    payload = {
        "source": str(source or ""),
        "video_aspect": aspect.value,
        "video_script": str(video_script or "").strip(),
        "video_terms": normalize_terms(video_terms),
        "clip_duration": int(clip_duration),
        "video_count": int(video_count),
        "match_script_order": bool(match_script_order),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _estimate_narration_seconds(video_script: str) -> float:
    text = re.sub(r"\s+", " ", str(video_script or "")).strip()
    if not text:
        return 0.0

    cjk_chars = re.findall(
        r"[\u3400-\u4dbf\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]",
        text,
    )
    remaining = re.sub(
        r"[\u3400-\u4dbf\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]",
        " ",
        text,
    )
    words = re.findall(r"\b[\w]+(?:[-'’][\w]+)*\b", remaining, re.UNICODE)
    punctuation_count = len(re.findall(r"[,，.。!?！？;；:：]", text))
    return len(cjk_chars) / 4.2 + len(words) / 2.6 + punctuation_count * 0.12


def estimate_review_item_count(
    *,
    video_script: str,
    terms: list[str],
    clip_duration: int,
    video_count: int,
) -> tuple[int, float, bool]:
    clip_seconds = max(1, int(clip_duration))
    narration_seconds = _estimate_narration_seconds(video_script)
    if narration_seconds <= 0:
        narration_seconds = max(1, len(terms)) * clip_seconds

    # Add headroom because actual TTS duration can differ from text-only estimation.
    target_seconds = narration_seconds * 1.25 * max(1, int(video_count))
    raw_count = max(len(terms), int(math.ceil(target_seconds / clip_seconds)))
    capped = raw_count > MAX_REVIEW_ITEMS
    return min(MAX_REVIEW_ITEMS, raw_count), target_seconds, capped


def fetch_review_plan(
    *,
    source: str,
    video_aspect: VideoAspect | str,
    video_script: str,
    video_terms: Any,
    clip_duration: int,
    video_count: int,
    match_script_order: bool,
) -> dict[str, Any]:
    terms = normalize_terms(video_terms)
    if not terms:
        return {
            "fingerprint": build_review_fingerprint(
                source=source,
                video_aspect=video_aspect,
                video_script=video_script,
                video_terms=video_terms,
                clip_duration=clip_duration,
                video_count=video_count,
                match_script_order=match_script_order,
            ),
            "slots": [],
            "target_count": 0,
            "estimated_seconds": 0.0,
            "capped": False,
            "source": source,
            "video_aspect": VideoAspect(video_aspect).value,
            "clip_duration": int(clip_duration),
        }

    target_count, estimated_seconds, capped = estimate_review_item_count(
        video_script=video_script,
        terms=terms,
        clip_duration=clip_duration,
        video_count=video_count,
    )

    candidate_groups: list[tuple[str, list[MaterialInfo]]] = []
    for term in terms:
        candidates = material.search_video_candidates(
            source=source,
            search_term=term,
            minimum_duration=max(1, int(clip_duration)),
            video_aspect=VideoAspect(video_aspect),
        )
        candidate_groups.append((term, list(candidates)))

    slots: list[dict[str, Any]] = []
    used_urls: set[str] = set()
    offsets = [0 for _ in candidate_groups]
    while len(slots) < target_count:
        added_in_round = False
        for group_index, (term, candidates) in enumerate(candidate_groups):
            while offsets[group_index] < len(candidates):
                item = candidates[offsets[group_index]]
                offsets[group_index] += 1
                if not item.url or item.url in used_urls:
                    continue
                used_urls.add(item.url)
                slots.append({"term": term, "item": item})
                added_in_round = True
                break
            if len(slots) >= target_count:
                break
        if not added_in_round:
            break

    return {
        "fingerprint": build_review_fingerprint(
            source=source,
            video_aspect=video_aspect,
            video_script=video_script,
            video_terms=video_terms,
            clip_duration=clip_duration,
            video_count=video_count,
            match_script_order=match_script_order,
        ),
        "slots": slots,
        "target_count": target_count,
        "estimated_seconds": estimated_seconds,
        "capped": capped,
        "source": str(source),
        "video_aspect": VideoAspect(video_aspect).value,
        "clip_duration": int(clip_duration),
    }


def find_replacement(
    *,
    plan: dict[str, Any],
    slot_index: int,
    search_term: str,
) -> dict[str, Any] | None:
    slots = list(plan.get("slots") or [])
    if slot_index < 0 or slot_index >= len(slots):
        return None

    normalized_term = str(search_term or "").strip()
    if not normalized_term:
        return None

    current_item = slots[slot_index].get("item")
    current_url = getattr(current_item, "url", "")
    used_urls = {
        getattr(slot.get("item"), "url", "")
        for index, slot in enumerate(slots)
        if index != slot_index
    }
    candidates = material.search_video_candidates(
        source=str(plan.get("source") or "pexels"),
        search_term=normalized_term,
        minimum_duration=max(1, int(plan.get("clip_duration") or 1)),
        video_aspect=VideoAspect(plan.get("video_aspect") or VideoAspect.portrait.value),
    )
    for item in candidates:
        if not item.url or item.url == current_url or item.url in used_urls:
            continue
        return {"term": normalized_term, "item": item}
    return None


def confirmed_materials(plan: dict[str, Any] | None) -> list[MaterialInfo]:
    if not plan:
        return []
    materials: list[MaterialInfo] = []
    for slot in plan.get("slots") or []:
        item = slot.get("item") if isinstance(slot, dict) else None
        if isinstance(item, MaterialInfo) and item.url:
            materials.append(item)
    return materials
