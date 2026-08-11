from pathlib import Path
import runpy


source = Path("trigger/tools/apply_material_review_patch.py")
text = source.read_text(encoding="utf-8")
old = '''    text = replace_once(\n        text,\n        "            match_script_order=params.match_materials_to_script,\\n        )\\n",\n        "            match_script_order=params.match_materials_to_script,\\n            preferred_items=preferred_materials,\\n        )\\n",\n        "pass reviewed materials to downloader",\n    )\n'''
new = '''    text = replace_once(\n        text,\n        "            audio_duration=audio_duration * params.video_count,\\n"\n        "            max_clip_duration=params.video_clip_duration,\\n"\n        "            match_script_order=params.match_materials_to_script,\\n"\n        "        )\\n",\n        "            audio_duration=audio_duration * params.video_count,\\n"\n        "            max_clip_duration=params.video_clip_duration,\\n"\n        "            match_script_order=params.match_materials_to_script,\\n"\n        "            preferred_items=preferred_materials,\\n"\n        "        )\\n",\n        "pass reviewed materials to downloader",\n    )\n'''
if text.count(old) != 1:
    raise RuntimeError(f"patch-script fix anchor mismatch: {text.count(old)}")
text = text.replace(old, new, 1)
patched = Path("/tmp/apply_material_review_patch.py")
patched.write_text(text, encoding="utf-8")
runpy.run_path(str(patched), run_name="__main__")
