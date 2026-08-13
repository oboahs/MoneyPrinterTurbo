from pathlib import Path


def patch_main() -> None:
    main_path = Path("webui/Main.py")
    main_text = main_path.read_text(encoding="utf-8")

    dialog_anchor = main_text.index("def _render_material_review_dialog():")
    loop_start = main_text.index(
        "    for index, slot in enumerate(slots):\n", dialog_anchor
    )
    loop_end = main_text.index(
        "    cancel_col, confirm_col = st.columns(2)\n", loop_start
    )
    compact_grid = '''    # 素材筛选以缩略图浏览为主。固定每行 6 张，让单个预览宽度约为
    # 对话框内容区的六分之一；替换搜索和来源链接折叠到卡片中，避免操作区
    # 再把缩略图撑回大尺寸。仅改变 WebUI 排版，不修改下载素材或成片分辨率。
    review_column_count = 6
    for row_start in range(0, len(slots), review_column_count):
        row_columns = st.columns(review_column_count, gap="small")
        for offset, review_col in enumerate(row_columns):
            index = row_start + offset
            if index >= len(slots):
                break

            slot = slots[index]
            item = slot.get("item")
            if item is None:
                continue
            source_info = (
                item.source_info if isinstance(item.source_info, dict) else {}
            )

            with review_col:
                with st.container(border=True):
                    st.caption(tr("Material Item").format(index=index + 1))
                    st.video(item.url)
                    st.caption(
                        f"{item.provider} · {int(item.duration or 0)}s · "
                        f"{source_info.get('asset_id') or '-'}"
                    )
                    st.caption(
                        f"{tr('Video Keywords')}: {slot.get('term') or '-'}"
                    )

                    with st.expander(tr("Replacement Search Term")):
                        query_key = (
                            "material_review_query_"
                            f"{plan.get('fingerprint', '')[:10]}_{index}"
                        )
                        st.session_state.setdefault(
                            query_key, slot.get("term") or ""
                        )
                        replacement_term = st.text_input(
                            tr("Replacement Search Term"),
                            key=query_key,
                            label_visibility="collapsed",
                        ).strip()
                        if st.button(
                            tr("Search Replacement"),
                            key=(
                                "replace_material_"
                                f"{plan.get('fingerprint', '')[:10]}_{index}"
                            ),
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
                                st.session_state[
                                    "material_review_confirmed_fingerprint"
                                ] = ""
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

'''
    main_text = main_text[:loop_start] + compact_grid + main_text[loop_end:]

    old_docstring = (
        '    """渲染低成本短试听、完整文案时长估算和按需完整配音预览。"""'
    )
    new_docstring = (
        '    """渲染音色试听、完整文案时长估算和可直接复用于成片的配音预览。"""'
    )
    if old_docstring not in main_text:
        raise RuntimeError("voice preview docstring anchor not found")
    main_text = main_text.replace(old_docstring, new_docstring, 1)

    old_play_button = '''    short_preview_requested = preview_columns[0].button(
        tr("Play Voice"),
        key="play_voice_button",
        icon=":material/graphic_eq:",
        use_container_width=True,
    )'''
    new_play_button = '''    short_preview_requested = preview_columns[0].button(
        tr("Play Voice"),
        key="play_voice_button",
        icon=":material/graphic_eq:",
        help=(tr("Full Voiceover Preview Cost Hint") if script_content else None),
        use_container_width=True,
    )'''
    if old_play_button not in main_text:
        raise RuntimeError("Play Voice button anchor not found")
    main_text = main_text.replace(old_play_button, new_play_button, 1)

    old_preview_route = '''    if short_preview_requested:
        preview_type = "sample"
        preview_content = sample_content
    elif full_preview_requested:
        preview_type = "full"
        preview_content = script_content
'''
    new_preview_route = '''    if short_preview_requested:
        # 已经有视频文案时，普通“试听”也直接走完整文案链路。这样试听缓存
        # 会使用 full 指纹，参数不变时正式任务可以直接复用同一份音频，
        # 避免生成式 TTS 因短样例和长文案的停顿/韵律差异造成速度错觉。
        if script_content:
            preview_type = "full"
            preview_content = script_content
        else:
            preview_type = "sample"
            preview_content = sample_content
    elif full_preview_requested:
        preview_type = "full"
        preview_content = script_content
'''
    if old_preview_route not in main_text:
        raise RuntimeError("voice preview routing anchor not found")
    main_text = main_text.replace(old_preview_route, new_preview_route, 1)

    main_path.write_text(main_text, encoding="utf-8")


def patch_task() -> None:
    task_path = Path("app/services/task.py")
    task_text = task_path.read_text(encoding="utf-8")
    old_voice_dispatch = "voice_name=voice.parse_voice_name(params.voice_name),"
    new_voice_dispatch = "voice_name=params.voice_name,"
    if task_text.count(old_voice_dispatch) != 1:
        raise RuntimeError("formal TTS voice dispatch anchor count changed")
    task_text = task_text.replace(old_voice_dispatch, new_voice_dispatch, 1)
    task_path.write_text(task_text, encoding="utf-8")


def verify() -> None:
    import ast

    main_text = Path("webui/Main.py").read_text(encoding="utf-8")
    task_text = Path("app/services/task.py").read_text(encoding="utf-8")
    ast.parse(main_text)
    ast.parse(task_text)
    assert "review_column_count = 6" in main_text
    assert 'row_columns = st.columns(review_column_count, gap="small")' in main_text
    assert 'if script_content:\n            preview_type = "full"' in main_text
    assert "voice_name=voice.parse_voice_name(params.voice_name)," not in task_text
    assert "voice_name=params.voice_name," in task_text


if __name__ == "__main__":
    patch_main()
    patch_task()
    verify()
    print("Material preview and TTS consistency patch applied successfully")
