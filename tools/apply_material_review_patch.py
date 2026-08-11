from pathlib import Path


MAIN_PATH = Path("webui/Main.py")
MATERIAL_PATH = Path("app/services/material.py")
TASK_PATH = Path("app/services/task.py")
WEBUI_TASK_PATH = Path("app/services/webui_task.py")
ZH_PATH = Path("webui/i18n/zh.json")
EN_PATH = Path("webui/i18n/en.json")


def replace_once(text: str, old: str, new: str, description: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{description}: expected 1 match, found {count}")
    return text.replace(old, new, 1)


def patch_material() -> None:
    text = MATERIAL_PATH.read_text(encoding="utf-8")
    helper = '''\n\ndef search_video_candidates(\n    source: str,\n    search_term: str,\n    minimum_duration: int,\n    video_aspect: VideoAspect = VideoAspect.portrait,\n) -> List[MaterialInfo]:\n    """Search online material candidates without downloading them.\n\n    This is used by the optional WebUI review flow. It intentionally reuses the\n    same provider implementations, orientation filtering, API-key handling and\n    24-hour search cache as the normal generation pipeline.\n    """\n    normalized_source = str(source or "pexels").strip().lower()\n    searchers = {\n        "pexels": search_videos_pexels,\n        "pixabay": search_videos_pixabay,\n        "coverr": search_videos_coverr,\n    }\n    remote_search_videos = searchers.get(normalized_source)\n    if remote_search_videos is None:\n        raise ValueError(f"unsupported online video source: {source}")\n\n    return _search_videos_with_cache(\n        provider=normalized_source,\n        search_videos=remote_search_videos,\n        search_term=search_term,\n        minimum_duration=minimum_duration,\n        video_aspect=VideoAspect(video_aspect),\n    )\n'''
    if "def search_video_candidates(" not in text:
        text = replace_once(
            text,
            "\n\ndef download_videos(\n",
            helper + "\n\ndef download_videos(\n",
            "material candidate helper insertion",
        )

    old_signature = '''def download_videos(\n    task_id: str,\n    search_terms: List[str],\n    source: str = "pexels",\n    video_aspect: VideoAspect = VideoAspect.portrait,\n    video_concat_mode: VideoConcatMode = VideoConcatMode.random,\n    audio_duration: float = 0.0,\n    max_clip_duration: int = 5,\n    match_script_order: bool = False,\n) -> List[str]:\n'''
    new_signature = '''def download_videos(\n    task_id: str,\n    search_terms: List[str],\n    source: str = "pexels",\n    video_aspect: VideoAspect = VideoAspect.portrait,\n    video_concat_mode: VideoConcatMode = VideoConcatMode.random,\n    audio_duration: float = 0.0,\n    max_clip_duration: int = 5,\n    match_script_order: bool = False,\n    preferred_items: List[MaterialInfo] | None = None,\n) -> List[str]:\n'''
    if "preferred_items: List[MaterialInfo] | None = None" not in text:
        text = replace_once(text, old_signature, new_signature, "download signature")

    old_provider = '''    provider = "pexels"\n    remote_search_videos = search_videos_pexels\n    if source == "pixabay":\n        provider = "pixabay"\n        remote_search_videos = search_videos_pixabay\n    elif source == "coverr":\n        provider = "coverr"\n        remote_search_videos = search_videos_coverr\n\n    def search_videos(\n        search_term: str,\n        minimum_duration: int,\n        video_aspect: VideoAspect,\n    ) -> List[MaterialInfo]:\n        return _search_videos_with_cache(\n            provider=provider,\n            search_videos=remote_search_videos,\n            search_term=search_term,\n            minimum_duration=minimum_duration,\n            video_aspect=video_aspect,\n        )\n'''
    new_provider = '''    source = str(source or "pexels").strip().lower()\n\n    def search_videos(\n        search_term: str,\n        minimum_duration: int,\n        video_aspect: VideoAspect,\n    ) -> List[MaterialInfo]:\n        return search_video_candidates(\n            source=source,\n            search_term=search_term,\n            minimum_duration=minimum_duration,\n            video_aspect=video_aspect,\n        )\n'''
    if old_provider in text:
        text = replace_once(text, old_provider, new_provider, "download provider resolver")

    text = replace_once(
        text,
        "    if match_script_order:\n        return _download_videos_by_script_order(\n",
        "    if match_script_order and not preferred_items:\n        return _download_videos_by_script_order(\n",
        "manual review script-order bypass",
    )

    old_candidates = '''    valid_video_items = []\n    valid_video_urls = []\n    found_duration = 0.0\n    for search_term in search_terms:\n'''
    new_candidates = '''    valid_video_items = []\n    valid_video_urls = []\n    found_duration = 0.0\n\n    # WebUI-reviewed materials are trusted only through the internal task channel.\n    # Keep them first, then append the normal search pool as an automatic fallback.\n    # This way an expired CDN URL or a narration that is longer than the preview\n    # estimate cannot make the generation fail solely because review was enabled.\n    reviewed_items = _filter_materials_by_aspect(\n        list(preferred_items or []),\n        video_aspect,\n    )\n    for item in reviewed_items:\n        if item.provider != source or not item.url or item.url in valid_video_urls:\n            continue\n        valid_video_items.append(item)\n        valid_video_urls.append(item.url)\n        found_duration += item.duration\n\n    for search_term in search_terms:\n'''
    if "reviewed_items = _filter_materials_by_aspect(" not in text:
        text = replace_once(text, old_candidates, new_candidates, "reviewed candidates")

    text = replace_once(
        text,
        "    if concat_mode_value == VideoConcatMode.random.value:\n        random.shuffle(valid_video_items)\n",
        "    if concat_mode_value == VideoConcatMode.random.value and not preferred_items:\n        random.shuffle(valid_video_items)\n",
        "reviewed order preservation",
    )

    MATERIAL_PATH.write_text(text, encoding="utf-8")


def patch_task() -> None:
    text = TASK_PATH.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "def get_video_materials(task_id, params, video_terms, audio_duration):\n",
        "def get_video_materials(\n    task_id, params, video_terms, audio_duration, preferred_materials=None\n):\n",
        "get video materials signature",
    )
    text = replace_once(
        text,
        "            match_script_order=params.match_materials_to_script,\n        )\n",
        "            match_script_order=params.match_materials_to_script,\n            preferred_items=preferred_materials,\n        )\n",
        "pass reviewed materials to downloader",
    )

    old_pipeline_signature = '''def _run_pipeline(\n    task_id,\n    params: VideoParams,\n    stop_at: str = "video",\n    voice_preview: dict | None = None,\n):\n'''
    new_pipeline_signature = '''def _run_pipeline(\n    task_id,\n    params: VideoParams,\n    stop_at: str = "video",\n    voice_preview: dict | None = None,\n    preferred_materials=None,\n):\n'''
    text = replace_once(
        text, old_pipeline_signature, new_pipeline_signature, "pipeline signature"
    )
    text = replace_once(
        text,
        "    downloaded_videos = get_video_materials(\n        task_id, params, video_terms, audio_duration\n    )\n",
        "    downloaded_videos = get_video_materials(\n        task_id,\n        params,\n        video_terms,\n        audio_duration,\n        preferred_materials=preferred_materials,\n    )\n",
        "pipeline reviewed materials",
    )

    old_start_signature = '''def start(\n    task_id,\n    params: VideoParams,\n    stop_at: str = "video",\n    voice_preview: dict | None = None,\n):\n'''
    new_start_signature = '''def start(\n    task_id,\n    params: VideoParams,\n    stop_at: str = "video",\n    voice_preview: dict | None = None,\n    preferred_materials=None,\n):\n'''
    text = replace_once(text, old_start_signature, new_start_signature, "start signature")
    text = replace_once(
        text,
        "            stop_at=stop_at,\n            voice_preview=voice_preview,\n        )\n",
        "            stop_at=stop_at,\n            voice_preview=voice_preview,\n            preferred_materials=preferred_materials,\n        )\n",
        "start reviewed materials",
    )
    TASK_PATH.write_text(text, encoding="utf-8")


def patch_webui_task() -> None:
    text = WEBUI_TASK_PATH.read_text(encoding="utf-8")
    if not text.startswith("import copy\n"):
        text = "import copy\n" + text

    old_worker_signature = '''def _run_generation(\n    task_id: str,\n    params: VideoParams,\n    capture_logs: bool,\n    voice_preview: dict | None = None,\n) -> dict:\n'''
    new_worker_signature = '''def _run_generation(\n    task_id: str,\n    params: VideoParams,\n    capture_logs: bool,\n    voice_preview: dict | None = None,\n    preferred_materials=None,\n) -> dict:\n'''
    text = replace_once(
        text, old_worker_signature, new_worker_signature, "webui worker signature"
    )
    text = replace_once(
        text,
        "                params=params,\n                voice_preview=voice_preview,\n            )\n",
        "                params=params,\n                voice_preview=voice_preview,\n                preferred_materials=preferred_materials,\n            )\n",
        "webui worker reviewed materials",
    )

    old_submit_signature = '''def submit_generation(\n    task_id: str,\n    params: VideoParams,\n    capture_logs: bool = True,\n    voice_preview: dict | None = None,\n) -> None:\n'''
    new_submit_signature = '''def submit_generation(\n    task_id: str,\n    params: VideoParams,\n    capture_logs: bool = True,\n    voice_preview: dict | None = None,\n    preferred_materials=None,\n) -> None:\n'''
    text = replace_once(
        text, old_submit_signature, new_submit_signature, "webui submit signature"
    )
    text = replace_once(
        text,
        "    voice_preview_snapshot = dict(voice_preview) if voice_preview else None\n",
        "    voice_preview_snapshot = dict(voice_preview) if voice_preview else None\n"
        "    preferred_materials_snapshot = (\n"
        "        copy.deepcopy(preferred_materials) if preferred_materials else None\n"
        "    )\n",
        "reviewed materials snapshot",
    )
    text = replace_once(
        text,
        "            capture_logs=capture_logs,\n            voice_preview=voice_preview_snapshot,\n        )\n",
        "            capture_logs=capture_logs,\n            voice_preview=voice_preview_snapshot,\n"
        "            preferred_materials=preferred_materials_snapshot,\n        )\n",
        "submit reviewed materials",
    )
    WEBUI_TASK_PATH.write_text(text, encoding="utf-8")


def patch_main() -> None:
    text = MAIN_PATH.read_text(encoding="utf-8")
    import_anchor = "from webui.subtitle_preview import render_subtitle_preview\n"
    if "from webui import material_review\n" not in text:
        text = replace_once(
            text,
            import_anchor,
            import_anchor + "from webui import material_review\n",
            "material review import",
        )

    dialog_block = r'''

def _dismiss_material_review_dialog():
    st.session_state["material_review_dialog_open"] = False


def _material_review_fingerprint(params) -> str:
    return material_review.build_review_fingerprint(
        source=params.video_source,
        video_aspect=params.video_aspect,
        video_script=params.video_script,
        video_terms=params.video_terms,
        clip_duration=params.video_clip_duration,
        video_count=params.video_count,
        match_script_order=params.match_materials_to_script,
    )


def _get_confirmed_material_review_materials(params):
    if params.video_source == "local":
        return None
    plan = st.session_state.get("material_review_plan")
    if not plan:
        return None
    current_fingerprint = _material_review_fingerprint(params)
    if (
        plan.get("fingerprint") != current_fingerprint
        or st.session_state.get("material_review_confirmed_fingerprint")
        != current_fingerprint
    ):
        return None
    materials = material_review.confirmed_materials(plan)
    return materials or None


@st.dialog(
    tr("Filter Materials"),
    width="large",
    on_dismiss=_dismiss_material_review_dialog,
)
def _render_material_review_dialog():
    plan = st.session_state.get("material_review_plan") or {}
    slots = list(plan.get("slots") or [])
    if not slots:
        st.warning(tr("Material Fetch Empty"))
        return

    st.caption(tr("Material Review Help").format(count=len(slots)))
    if plan.get("capped"):
        st.info(tr("Material Review Capped"))

    for index, slot in enumerate(slots):
        item = slot.get("item")
        if item is None:
            continue
        source_info = item.source_info if isinstance(item.source_info, dict) else {}
        with st.container(border=True):
            preview_col, action_col = st.columns([1.25, 1.0], vertical_alignment="top")
            with preview_col:
                st.markdown(tr("Material Item").format(index=index + 1))
                st.video(item.url)
            with action_col:
                st.caption(
                    f"{item.provider} · {int(item.duration or 0)}s · "
                    f"{source_info.get('asset_id') or '-'}"
                )
                st.write(f"**{tr('Video Keywords')}**: {slot.get('term') or '-'}")
                query_key = (
                    f"material_review_query_{plan.get('fingerprint', '')[:10]}_{index}"
                )
                st.session_state.setdefault(query_key, slot.get("term") or "")
                replacement_term = st.text_input(
                    tr("Replacement Search Term"),
                    key=query_key,
                ).strip()
                if st.button(
                    tr("Search Replacement"),
                    key=f"replace_material_{plan.get('fingerprint', '')[:10]}_{index}",
                    icon=":material/refresh:",
                    use_container_width=True,
                ):
                    with st.spinner(tr("Searching Replacement Material")):
                        replacement = material_review.find_replacement(
                            plan=plan,
                            slot_index=index,
                            search_term=replacement_term,
                        )
                    if replacement is None:
                        st.warning(tr("No Replacement Material"))
                    else:
                        plan["slots"][index] = replacement
                        st.session_state["material_review_plan"] = plan
                        st.session_state["material_review_confirmed_fingerprint"] = ""
                        st.toast(tr("Material Replacement Updated"))
                        st.rerun(scope="fragment")

                source_page = source_info.get("source_page")
                if source_page:
                    st.link_button(
                        tr("Open Material Source"),
                        source_page,
                        icon=":material/open_in_new:",
                        use_container_width=True,
                    )

    cancel_col, confirm_col = st.columns(2)
    if cancel_col.button(
        tr("Cancel Material Review"),
        key="cancel_material_review",
        use_container_width=True,
    ):
        st.session_state["material_review_dialog_open"] = False
        st.rerun(scope="app")
    if confirm_col.button(
        tr("Confirm Material Selection"),
        key="confirm_material_review",
        type="primary",
        icon=":material/check:",
        use_container_width=True,
    ):
        st.session_state["material_review_confirmed_fingerprint"] = plan.get(
            "fingerprint", ""
        )
        st.session_state["material_review_dialog_open"] = False
        st.toast(tr("Material Selection Confirmed"))
        st.rerun(scope="app")

'''
    if "def _render_material_review_dialog():" not in text:
        text = replace_once(
            text,
            "\n\ndef _render_video_settings(panel, params):\n",
            dialog_block + "\n\ndef _render_video_settings(panel, params):\n",
            "material review dialog insertion",
        )

    review_controls = r'''

            if params.video_source != "local":
                review_fingerprint = _material_review_fingerprint(params)
                review_plan = st.session_state.get("material_review_plan")
                plan_is_current = bool(
                    review_plan
                    and review_plan.get("fingerprint") == review_fingerprint
                    and review_plan.get("slots")
                )
                if review_plan and not plan_is_current:
                    st.warning(tr("Material Review Stale"))

                fetch_col, filter_col = st.columns(2)
                if fetch_col.button(
                    tr("Fetch Materials"),
                    key="fetch_materials_button",
                    icon=":material/download:",
                    use_container_width=True,
                ):
                    review_terms = material_review.normalize_terms(params.video_terms)
                    if not review_terms:
                        st.warning(tr("Material Fetch Requires Keywords"))
                    else:
                        try:
                            with st.spinner(tr("Fetching Materials")):
                                review_plan = material_review.fetch_review_plan(
                                    source=params.video_source,
                                    video_aspect=params.video_aspect,
                                    video_script=params.video_script,
                                    video_terms=params.video_terms,
                                    clip_duration=params.video_clip_duration,
                                    video_count=params.video_count,
                                    match_script_order=params.match_materials_to_script,
                                )
                        except Exception as exc:
                            logger.warning(
                                f"material review fetch failed: {type(exc).__name__}: {exc}"
                            )
                            st.error(
                                tr("Material Fetch Failed").format(error=str(exc))
                            )
                        else:
                            st.session_state["material_review_plan"] = review_plan
                            st.session_state["material_review_confirmed_fingerprint"] = ""
                            st.session_state["material_review_dialog_open"] = False
                            plan_is_current = bool(review_plan.get("slots"))
                            if plan_is_current:
                                st.toast(
                                    tr("Material Fetch Complete").format(
                                        count=len(review_plan["slots"])
                                    )
                                )
                            else:
                                st.warning(tr("Material Fetch Empty"))

                if filter_col.button(
                    tr("Filter Materials"),
                    key="filter_materials_button",
                    icon=":material/video_library:",
                    use_container_width=True,
                    disabled=not plan_is_current,
                ):
                    st.session_state["material_review_dialog_open"] = True

                if plan_is_current:
                    item_count = len(review_plan.get("slots") or [])
                    if (
                        st.session_state.get("material_review_confirmed_fingerprint")
                        == review_fingerprint
                    ):
                        st.success(
                            tr("Material Review Ready").format(count=item_count)
                        )
                    else:
                        st.info(
                            tr("Material Review Pending").format(count=item_count)
                        )

                if (
                    st.session_state.get("material_review_dialog_open", False)
                    and plan_is_current
                ):
                    _render_material_review_dialog()
'''
    if "key=\"fetch_materials_button\"" not in text:
        text = replace_once(
            text,
            "\n            video_codec_options = [\n",
            review_controls + "\n\n            video_codec_options = [\n",
            "material review controls insertion",
        )

    text = replace_once(
        text,
        "                voice_preview=reusable_voice_preview,\n            )\n",
        "                voice_preview=reusable_voice_preview,\n"
        "                preferred_materials=_get_confirmed_material_review_materials(params),\n"
        "            )\n",
        "submit confirmed material review",
    )
    MAIN_PATH.write_text(text, encoding="utf-8")


def patch_translations() -> None:
    zh = ZH_PATH.read_text(encoding="utf-8")
    en = EN_PATH.read_text(encoding="utf-8")
    zh_anchor = '    "Video Source": "视频来源",\n'
    en_anchor = '    "Video Source": "Video Source",\n'
    zh_insert = '''    "Fetch Materials": "获取素材",\n    "Filter Materials": "筛选素材",\n    "Material Fetch Requires Keywords": "请先生成或填写视频关键词。",\n    "Fetching Materials": "正在搜索并匹配素材...",\n    "Material Fetch Complete": "已获取 {count} 条待筛选素材。",\n    "Material Fetch Empty": "没有找到可用素材，请检查关键词、视频来源和 API 配置。",\n    "Material Fetch Failed": "获取素材失败：{error}",\n    "Material Review Stale": "视频来源、比例、关键词、片段时长或视频数量已变化，请重新获取素材。",\n    "Material Review Pending": "已获取 {count} 条素材但尚未确认；现在直接生成仍会使用原自动流程。",\n    "Material Review Ready": "已确认 {count} 条筛选素材；生成时会优先使用这些素材，不足部分自动补齐。",\n    "Material Review Help": "共 {count} 条准备使用的素材。默认保留；需要替换哪一条，就修改搜索词并点击“重新搜索替换”。",\n    "Material Review Capped": "为避免筛选窗口过长，当前最多预览 24 条；如果实际配音更长，生成时会自动补齐额外素材。",\n    "Material Item": "**素材 {index}**",\n    "Replacement Search Term": "替换搜索词",\n    "Search Replacement": "重新搜索替换",\n    "Searching Replacement Material": "正在搜索替换素材...",\n    "No Replacement Material": "没有找到不同的可用素材，可以换一个搜索词再试。",\n    "Material Replacement Updated": "已替换该条素材，请确认筛选结果。",\n    "Open Material Source": "查看素材来源",\n    "Cancel Material Review": "取消",\n    "Confirm Material Selection": "确认筛选结果",\n    "Material Selection Confirmed": "筛选结果已确认，生成时将优先使用这些素材。",\n'''
    en_insert = '''    "Fetch Materials": "Fetch Materials",\n    "Filter Materials": "Review Materials",\n    "Material Fetch Requires Keywords": "Generate or enter video keywords first.",\n    "Fetching Materials": "Searching and matching materials...",\n    "Material Fetch Complete": "Fetched {count} materials for review.",\n    "Material Fetch Empty": "No usable materials were found. Check the keywords, source and API configuration.",\n    "Material Fetch Failed": "Failed to fetch materials: {error}",\n    "Material Review Stale": "The source, aspect ratio, keywords, clip duration or video count changed. Fetch materials again.",\n    "Material Review Pending": "{count} materials are ready for review but not confirmed. Generating now still uses the original automatic flow.",\n    "Material Review Ready": "{count} reviewed materials are confirmed. Generation will prefer them and automatically fill any shortage.",\n    "Material Review Help": "{count} planned materials are listed below. Keep them by default, or change a search term and replace an individual clip.",\n    "Material Review Capped": "The review window shows at most 24 clips. If the final narration is longer, generation automatically fills extra materials.",\n    "Material Item": "**Material {index}**",\n    "Replacement Search Term": "Replacement search term",\n    "Search Replacement": "Search replacement",\n    "Searching Replacement Material": "Searching replacement material...",\n    "No Replacement Material": "No different usable material was found. Try another search term.",\n    "Material Replacement Updated": "Material replaced. Confirm the review result to use it.",\n    "Open Material Source": "Open material source",\n    "Cancel Material Review": "Cancel",\n    "Confirm Material Selection": "Confirm reviewed materials",\n    "Material Selection Confirmed": "Reviewed materials confirmed. Generation will prefer this selection.",\n'''
    if '"Fetch Materials"' not in zh:
        zh = replace_once(zh, zh_anchor, zh_anchor + zh_insert, "Chinese translations")
    if '"Fetch Materials"' not in en:
        en = replace_once(en, en_anchor, en_anchor + en_insert, "English translations")
    ZH_PATH.write_text(zh, encoding="utf-8")
    EN_PATH.write_text(en, encoding="utf-8")


def main() -> None:
    patch_material()
    patch_task()
    patch_webui_task()
    patch_main()
    patch_translations()


if __name__ == "__main__":
    main()
