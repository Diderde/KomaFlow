"""用 Blender 的 VSE 把多段视频拼成一条（不需要外部 ffmpeg）。

用法：
    blender --background --factory-startup --python concat_vse.py -- spec.json

spec.json:
    {"inputs": ["a.mp4", "b.mp4"], "output": "out.mp4",
     "fps": 30, "width": 2560, "height": 1440}
"""

import json
import sys
from pathlib import Path

import bpy


def main() -> int:
    argv = sys.argv
    spec_path = Path(argv[argv.index("--") + 1]) if "--" in argv else None
    if spec_path is None or not spec_path.is_file():
        print("CONCAT_FAIL 缺少 spec")
        return 2

    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    inputs = [Path(p) for p in spec["inputs"]]
    missing = [str(p) for p in inputs if not p.is_file()]
    if missing:
        print(f"CONCAT_FAIL 缺输入：{missing[:3]}")
        return 3

    scene = bpy.context.scene
    scene.render.fps = int(spec.get("fps", 30))
    scene.render.fps_base = 1.0
    scene.render.resolution_x = int(spec.get("width", 2560))
    scene.render.resolution_y = int(spec.get("height", 1440))
    scene.render.resolution_percentage = 100
    scene.render.use_sequencer = True

    # 清理并建立序列编辑器
    if scene.sequence_editor is None:
        scene.sequence_editor_create()
    seq = scene.sequence_editor
    for strip in list(seq.sequences_all):
        seq.sequences.remove(strip)

    cursor = 1
    total = 0
    for path in inputs:
        strip = seq.sequences.new_movie(
            name=path.stem, filepath=str(path), channel=1, frame_start=cursor)
        # 显示到原有宽度
        try:
            strip.frame_final_duration = max(1, strip.frame_final_duration)
        except Exception:  # noqa: BLE001
            pass
        length = int(strip.frame_final_duration)
        cursor += length
        total += length

    scene.frame_start = 1
    scene.frame_end = max(1, total)

    out = Path(spec["output"])
    out.parent.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(out)
    # Blender 5.x：必须先切 media_type 才能选 FFMPEG
    scene.render.image_settings.media_type = "VIDEO"
    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.constant_rate_factor = "HIGH"
    scene.render.ffmpeg.ffmpeg_preset = "GOOD"

    print(f"CONCAT_BEGIN {len(inputs)} 段，共 {total} 帧 → {out}")
    bpy.ops.render.render(animation=True)

    ok = out.is_file() and out.stat().st_size > 0
    print(f"CONCAT_DONE ok={ok} size={out.stat().st_size if ok else 0}")
    return 0 if ok else 4


if __name__ == "__main__":
    sys.exit(main())
