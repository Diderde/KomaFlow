# -*- coding: utf-8 -*-
"""把「渲染模型」调好的材质观感迁移到我们的工程上（保留物理）。

用法（由适配层调用）::

    blender --background --python apply_look.py -- <spec.json>

spec 字段：
    work_blend : 我们的工程（已建物理/烘焙，**会被就地保存**）
    look_blend : 能力包存出来的工程（只有材质观感有用）
    report : 结果写这里
    suffix : 迁移后材质名的后缀（默认 ``_look``，避免覆盖原件）

做法：
  1. 从 look_blend **只 append 材质**（不 append 物体，避免两套骨架）
  2. 按**基础名**匹配：``biaoq`` ↔ ``biaoq_mmd``（能力包会给材质名加后缀）
  3. 逐个把材质槽换成迁移过来的那份
  4. 存盘

⚠️ 只换材质，不碰几何/骨架/物理 —— 那些属于我们这条链，换掉就全乱了。
"""

from __future__ import annotations

import json
import sys
import traceback

import bpy

SPEC = sys.argv[sys.argv.index("--") + 1]
with open(SPEC, encoding="utf-8") as handle:
    spec = json.load(handle)

report = {"ok": False, "replaced": [], "missing": [], "errors": []}


def _log_view(copied: dict) -> None:
    print("[LOOK] 色彩管理 =", copied)


def base_name(name: str) -> str:
    """去掉能力包加的后缀，用于匹配。

    实测能力包会把材质名改成 ``原名_mmd``（也可能有 ``_look`` / ``.001``）。
    """
    for suffix in ("_mmd", "_look", "_anime"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    # Blender 的重名后缀 .001 / .002
    if len(name) > 4 and name[-4] == "." and name[-3:].isdigit():
        return name[:-4]
    return name


def main() -> int:
    work = spec["work_blend"]
    look = spec["look_blend"]
    suffix = spec.get("suffix") or "_look"

    bpy.ops.wm.open_mainfile(filepath=work)

    # 记下迁移前就存在的材质，稍后据此区分"新来的"
    before = set(bpy.data.materials.keys())

    with bpy.data.libraries.load(look) as (src, dst):
        dst.materials = list(src.materials)

    imported = [m for m in bpy.data.materials
                if m is not None and m.name not in before]
    if not imported:
        report["errors"].append("look 工程里没有可用的材质")
        _write(spec, report)
        return 1
    report["imported_count"] = len(imported)

    # 基础名 → 迁移进来的材质
    incoming: dict[str, object] = {}
    for mat in imported:
        incoming.setdefault(base_name(mat.name), mat)

    # 我们的材质（排除 mmd_tools 的刚体辅助材质）
    targets = [m for m in bpy.data.materials
               if m.name in before and not m.name.startswith("mmd_tools_rigid")]

    mapping: dict[str, object] = {}
    for mat in targets:
        key = base_name(mat.name)
        if key in incoming:
            mapping[mat.name] = incoming[key]
        else:
            report["missing"].append(mat.name)

    if not mapping:
        report["errors"].append("一个材质都没匹配上（名字规则可能变了）")
        _write(spec, report)
        return 1

    # 逐槽替换：用 object.material_slots[i].material = 新材质
    replaced_objs = 0
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        slots = getattr(obj, "material_slots", None)
        if not slots:
            continue
        touched = False
        for slot in slots:
            mat = slot.material
            if mat is None:
                continue
            new = mapping.get(mat.name)
            if new is not None and slot.material is not new:
                slot.material = new
                touched = True
        if touched:
            replaced_objs += 1

    # ── 色彩管理也必须跟着迁移 ──
    #
    # 实测：只换材质，画面几乎没变化。原因是两边场景的**色彩变换不同**：
    # 我们工程用 AgX（会压灰、压高光），能力包用 Standard（保留色块）。
    # 卡渲的观感有一半来自这里，不迁等于白搬材质。
    copied_view = {}
    try:
        with bpy.data.libraries.load(look) as (src, dst):
            dst.scenes = list(src.scenes)
        look_scene = bpy.data.scenes[-1] if bpy.data.scenes else None
        if look_scene is not None:
            target = bpy.context.scene
            for attr in ("view_transform", "look", "exposure", "gamma"):
                try:
                    value = getattr(look_scene.view_settings, attr)
                    setattr(target.view_settings, attr, value)
                    copied_view[attr] = str(value)
                except (AttributeError, TypeError):
                    continue
            _log_view(copied_view)
    except Exception as exc: # noqa: BLE001 - 迁不过去不算致命
        report["errors"].append(f"色彩管理迁移失败：{exc}")

    report["view_settings"] = copied_view
    report["replaced"] = sorted(mapping.keys())
    report["replaced_count"] = len(mapping)
    report["objects_touched"] = replaced_objs
    report["ok"] = True
    bpy.ops.wm.save_mainfile()
    _write(spec, report)
    print(f"[LOOK] 迁移材质 {len(mapping)} 个，涉及物体 {replaced_objs} 个")
    return 0


def _write(spec: dict, payload: dict) -> None:
    target = spec.get("report")
    if not target:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    try:
        main()
    except Exception: # noqa: BLE001
        report["errors"].append(traceback.format_exc()[-1500:])
        _write(spec, report)
        raise
