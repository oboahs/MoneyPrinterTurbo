from pathlib import Path


MAIN_PATH = Path("webui/Main.py")
OLD_NAS_PAGE = Path("webui/pages/99_NAS硬件加速.py")


def replace_once(text: str, old: str, new: str, description: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{description}: expected 1 match, found {count}")
    return text.replace(old, new, 1)


def main() -> None:
    text = MAIN_PATH.read_text(encoding="utf-8")

    import_anchor = "from webui.subtitle_preview import render_subtitle_preview\n"
    nas_import = (
        "from webui.nas_hardware_acceleration import "
        "render_nas_hardware_acceleration_settings\n"
    )
    if nas_import not in text:
        text = replace_once(
            text,
            import_anchor,
            import_anchor + nas_import,
            "NAS settings import anchor",
        )

    old_tabs = '''        (
            middle_config_panel,
            right_config_panel,
            cache_config_panel,
            left_config_panel,
        ) = st.tabs(
            [
                tr("LLM Settings Tab"),
                tr("Material API Tab"),
                tr("Cache Management Tab"),
                tr("Interface Settings Tab"),
            ]
        )
'''
    new_tabs = '''        (
            middle_config_panel,
            right_config_panel,
            cache_config_panel,
            left_config_panel,
            nas_hardware_panel,
        ) = st.tabs(
            [
                tr("LLM Settings Tab"),
                tr("Material API Tab"),
                tr("Cache Management Tab"),
                tr("Interface Settings Tab"),
                "NAS 硬件加速",
            ]
        )
'''
    if "nas_hardware_panel" not in text:
        text = replace_once(text, old_tabs, new_tabs, "settings tabs")

    cache_call = "        _render_cache_management_settings(cache_config_panel)\n"
    nas_call = (
        "\n        with nas_hardware_panel:\n"
        "            render_nas_hardware_acceleration_settings()\n"
    )
    if "render_nas_hardware_acceleration_settings()" not in text:
        text = replace_once(
            text,
            cache_call,
            cache_call + nas_call,
            "NAS settings panel insertion",
        )

    text = text.replace(
        '    st.session_state["custom_position_input"] = str(custom_position)\n',
        '    st.session_state["custom_position_slider"] = custom_position\n',
    )
    text = text.replace(
        '    st.session_state["custom_position_input"] = str(defaults["custom_position"])\n',
        '    st.session_state["custom_position_slider"] = float(defaults["custom_position"])\n',
    )

    old_custom_control = '''            if params.subtitle_position == "custom":
                saved_custom_position = config.ui.get(
                    "custom_position", DEFAULT_SUBTITLE_SETTINGS["custom_position"]
                )
                st.session_state.setdefault(
                    "custom_position_input", str(saved_custom_position)
                )
                custom_position = st.text_input(
                    tr("Custom Position (% from top)"),
                    key="custom_position_input",
                    disabled=subtitle_settings_disabled,
                )
                try:
                    params.custom_position = float(custom_position)
                    if params.custom_position < 0 or params.custom_position > 100:
                        st.error(tr("Please enter a value between 0 and 100"))
                    else:
                        _set_runtime_config(
                            "ui", "custom_position", params.custom_position
                        )
                except ValueError:
                    st.error(tr("Please enter a valid number"))
'''
    new_custom_control = '''            if params.subtitle_position == "custom":
                saved_custom_position = config.ui.get(
                    "custom_position", DEFAULT_SUBTITLE_SETTINGS["custom_position"]
                )
                try:
                    saved_custom_position = float(saved_custom_position)
                except (TypeError, ValueError):
                    saved_custom_position = float(
                        DEFAULT_SUBTITLE_SETTINGS["custom_position"]
                    )
                saved_custom_position = min(100.0, max(0.0, saved_custom_position))
                st.session_state.setdefault(
                    "custom_position_slider", saved_custom_position
                )
                params.custom_position = st.slider(
                    tr("Custom Position (% from top)"),
                    min_value=0.0,
                    max_value=100.0,
                    step=1.0,
                    format="%.0f%%",
                    key="custom_position_slider",
                    disabled=subtitle_settings_disabled,
                )
                _set_runtime_config("ui", "custom_position", params.custom_position)
'''
    if old_custom_control in text:
        text = replace_once(
            text,
            old_custom_control,
            new_custom_control,
            "custom subtitle position control",
        )

    if "custom_position_input" in text:
        raise RuntimeError("legacy custom_position_input key still exists")
    if text.count("custom_position_slider") != 4:
        raise RuntimeError(
            "expected custom_position_slider in restore, reset, and render paths"
        )

    MAIN_PATH.write_text(text, encoding="utf-8")

    if OLD_NAS_PAGE.exists():
        OLD_NAS_PAGE.unlink()


if __name__ == "__main__":
    main()
