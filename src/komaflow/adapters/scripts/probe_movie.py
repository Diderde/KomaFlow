"""用 Blender 读视频的帧数/时长/分辨率（不依赖外部 ffprobe）。

用法：
    blender --background --factory-startup --python probe_movie.py -- <video>
"""

import json
import sys
from pathlib import Path

import bpy


def main() -> int:
    argv = sys.argv
    if "--" not in argv:
        print("PROBE_FAIL 缺少参数")
        return 2
    target = Path(argv[argv.index("--") + 1])
    if not target.is_file():
        print("PROBE_FAIL 文件不存在")
        return 3
    clip = bpy.data.movieclips.load(str(target))
    payload = {
        "frames": int(clip.frame_duration),
        "fps": float(clip.fps) or 0.0,
        "width": int(clip.size[0]),
        "height": int(clip.size[1]),
    }
    if payload["fps"] > 0:
        payload["duration"] = payload["frames"] / payload["fps"]
    else:
        payload["duration"] = 0.0
    print("PROBE_OK " + json.dumps(payload))
    return 0


if __name__ == "__main__":
    sys.exit(main())
