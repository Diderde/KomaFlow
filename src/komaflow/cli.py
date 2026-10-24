"""命令行入口。

对应需求：（核心逻辑必须能在**无界面环境**下单独跑）· （5 分钟找到该改哪里）。

界面层做好之后这里仍然保留 —— 自动化测试与排障都靠它。

用法::

    python -m komaflow.cli adapters
    python -m komaflow.cli discover
    python -m komaflow.cli plan --motion-length 1500 --preroll 30
    python -m komaflow.cli samples --total 7000 --count 100
    python -m komaflow.cli run --project demo.kfproj
    python -m komaflow.cli run --model 人物.pmx --motion 动作.vmd --work-dir work
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import unicodedata

from .adapters.discovery import describe_candidate, discover_blender
from .adapters.registry import ADAPTERS, BASELINE
from .branding import title
from .core import segment as seg
from .core.pipeline import STAGES, plan_run, run_project
from .core.project import Inputs, Output, Project


def _force_utf8_stdout() -> None:
    """Windows 终端默认 cp936，中文会乱码 —— 强制 UTF-8 输出。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def _display_width(text: str) -> int:
    """终端显示宽度。中文是双宽字符，不能按 len() 算，否则表格对不齐。"""
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def _pad(text: str, width: int, align: str = "left") -> str:
    space = " " * max(0, width - _display_width(text))
    return (space + text) if align == "right" else (text + space)


def _limit_type(raw: str) -> int | None:
    """``--limit`` 的取值：正整数，或 none 表示不分段（K-2.4 高级选项）。"""
    if raw.strip().lower() in ("none", "null", "off", "不分段"):
        return None
    value = int(raw)
    if value <= 0:
        raise argparse.ArgumentTypeError("单段上限必须是正整数，或 none 表示不分段")
    return value


def _resolve_total(args: argparse.Namespace) -> int:
    if args.total is not None:
        return args.total
    if getattr(args, "motion_length", None) is not None:
        return seg.project_total_frames(args.motion_length, args.preroll)
    raise SystemExit("请给出 --total（工程总帧数）或 --motion-length（动作时长，帧）之一。")


# --------------------------------------------------------------------------
# 子命令
# --------------------------------------------------------------------------


def cmd_adapters(args: argparse.Namespace) -> int:
    print(title())
    print()
    print("Blender 适配层（版本差异全部收在这里）")
    print("-" * 64)
    for adapter in ADAPTERS:
        print(f" {adapter.describe()}")
    print()
    print(f"统一基准版本：{BASELINE.label}")
    print(f" 引擎枚举 engine_eevee = {BASELINE.engine_eevee!r}")
    print(f" 出视频需先设 media_type = {BASELINE.needs_media_type_first}")
    print(f" 材质透明属性 = {BASELINE.material_transparency_attr!r}")
    print(f" 合成器节点树 = {BASELINE.compositor_attr!r}")
    print()
    print("核心逻辑层不出现任何版本判断；新增版本只需在此登记适配器。")
    return 0


def cmd_discover(args: argparse.Namespace) -> int:
    candidates = discover_blender([args.blender] if args.blender else None)
    if not candidates:
        print("没找到 Blender。本工具不自带 Blender，请先自行安装 Blender 5.x（K-7.8）。")
        return 1
    print(f"找到 {len(candidates)} 个 Blender（工具**不代选**，请自己指定要用哪个）：")
    for index, candidate in enumerate(candidates, 1):
        mark = " ←" if index == 1 else ""
        print(f" {index}. {describe_candidate(candidate)}{mark}")
    if len(candidates) == 1:
        print("\n只有一个候选，运行时可直接使用；探测到的版本以实测为准。")
    else:
        print("\n用 --blender <路径> 指定，或写进工程档的 blender_exe 字段。")
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    total = _resolve_total(args)

    if args.work_dir:
        run_plan = plan_run(total, args.work_dir, limit=args.limit, ext=args.ext)
        rows = [
            (item.segment.index + 1, item.segment.start, item.segment.end,
             item.segment.count, "已完成，跳过" if not item.should_render else "待渲染")
            for item in run_plan.segments
        ]
        summary = run_plan.summary()
        if args.json:
            print(json.dumps(
                {
                    "total_frames": total,
                    "limit": args.limit,
                    "segments": [
                        {"index": item.segment.index, "start": item.segment.start,
                         "end": item.segment.end, "count": item.segment.count,
                         "state": item.state.value, "should_render": item.should_render}
                        for item in run_plan.segments
                    ],
                    "summary": summary,
                },
                ensure_ascii=False, indent=2,
            ))
            return 0
    else:
        segments = seg.plan_segments(total, args.limit)
        rows = [(s.index + 1, s.start, s.end, s.count, "—") for s in segments]
        summary = (
            f"共 {len(segments)} 段。"
            if len(segments) > 1
            else "共 1 段 —— 总帧数未超过单段上限，一次渲完，不分段。"
        )
        if args.json:
            print(json.dumps(
                {"total_frames": total, "limit": args.limit,
                 "segments": [{"index": s.index, "start": s.start, "end": s.end,
                               "count": s.count, "filename": s.filename(args.ext)}
                              for s in segments],
                 "summary": summary},
                ensure_ascii=False, indent=2,
            ))
            return 0

    limit_text = "不分段" if args.limit is None else str(args.limit)
    if args.total is not None:
        print(f"工程总帧数 {total}（自第 0 帧起算，已含预热帧）")
    else:
        print(f"工程总帧数 {total} = 动作 {args.motion_length} + 预热 {args.preroll}（自第 0 帧起算）")
    print(f"单段上限 {limit_text}（天花板，不是固定切分单位）")
    print("-" * 60)

    headers = ("段", "起始帧", "结束帧", "帧数", "状态")
    cells = [(str(index), str(start), str(end), str(count), state)
             for index, start, end, count, state in rows]
    widths = [
        max(_display_width(header), *(_display_width(row[i]) for row in cells))
        for i, header in enumerate(headers)
    ]
    aligns = ("right", "right", "right", "right", "left")
    print(" ".join(_pad(headers[i], widths[i], aligns[i]) for i in range(len(headers))))
    for row in cells:
        print(" ".join(_pad(row[i], widths[i], aligns[i]) for i in range(len(row))))
    print("-" * 60)
    print(summary)
    if args.limit is not None and len(rows) > 1:
        print("提示：调小上限可降低单次失败的最大损失（实测启动开销仅约 17 秒，切细段几乎免费）。")
    return 0


def cmd_samples(args: argparse.Namespace) -> int:
    total = _resolve_total(args)
    policy = seg.sample_policy(total)
    count = args.count if args.count is not None else policy.maximum
    if count > policy.maximum:
        raise SystemExit(
            f"抽帧数 {count} 超过上限 {policy.maximum}（总帧数 {total} 帧时的规则：{policy.describe()}）。"
        )
    if count < policy.minimum and not policy.user_choice:
        raise SystemExit(
            f"抽帧数 {count} 低于下限 {policy.minimum}（总帧数 {total} 帧时的规则：{policy.describe()}）。"
        )
    frames = seg.pick_sample_frames(total, count)

    if args.json:
        print(json.dumps({"total_frames": total, "policy": policy.describe(),
                          "count": count, "frames": frames},
                         ensure_ascii=False, indent=2))
        return 0

    print(f"工程总帧数 {total}")
    print(f"抽帧规则：{policy.describe()}")
    print(f"本次抽取 {count} 帧（分层均匀、覆盖首尾、确定性 —— 同工程每次抽同一批）：")
    print(" " + ", ".join(str(f) for f in frames))
    return 0


def cmd_stages(args: argparse.Namespace) -> int:
    print("一次渲染的阶段（顺序即执行顺序）")
    print("-" * 64)
    for name, desc in STAGES:
        print(f" {name:<13} {desc}")
    print()
    print("界面走的是同一套阶段 —— 命令行与界面共用 core.pipeline.run_project。")
    return 0


def _project_from_args(args: argparse.Namespace) -> Project:
    project = Project(
        name=args.name or "cli",
        inputs=Inputs(
            route="blend" if args.blend else "assets",
            model=args.model,
            motion=args.motion,
            camera=args.camera,
            stage=args.stage,
            blend=args.blend,
        ),
        output=Output(dir=args.output_dir, basename=args.name or "KomaFlow"),
        blender_exe=args.blender,
    )
    if args.preroll is not None:
        project.params.preroll_frames = args.preroll
    if args.limit is not None:
        project.params.segment_limit = args.limit
    if args.width:
        project.params.width = args.width
    if args.height:
        project.params.height = args.height
    if args.fps:
        project.params.fps = args.fps
    if args.quality:
        project.params.quality = args.quality
    if args.frame_end is not None:
        project.params.frame_end = args.frame_end
    return project


def cmd_run(args: argparse.Namespace) -> int:
    project = Project.load(args.project) if args.project else _project_from_args(args)

    problems = project.validate()
    if problems:
        print("渲前体检发现问题：")
        for item in problems:
            print(f" · {item}")
        print("（本工具只给建议，不会替你改设置 —— K-6.4）")
        return 2

    for note in project.scope_warnings():
        print(f"提醒：{note}")

    if args.blender:
        project.blender_exe = args.blender

    cancel = threading.Event()
    last_line = {"text": ""}

    def on_event(event: dict) -> None:
        kind = event.get("type")
        if kind == "stage":
            print(f"\n▶ {event['stage']}：{event.get('message', '')}", flush=True)
        elif kind == "log":
            if last_line["text"]:
                print()
                last_line["text"] = ""
            prefix = " ! " if event.get("level") == "warn" else " · "
            print(prefix + str(event.get("message", "")), flush=True)
        elif kind == "segment":
            print(f"\n 第 {event['index'] + 1}/{event['total']} 段：帧 "
                  f"{event['frame_start']} ~ {event['frame_end']}", flush=True)
        elif kind == "progress":
            eta = event.get("eta_seconds") or 0
            line = (f" {event['percent']:6.2f}% 帧 {event['frame_done']}/{event['frame_total']}"
                    f" 本段 {event.get('seconds_per_frame') or 0:.2f} s/帧"
                    f" 预计剩余 {eta / 60:.1f} 分钟")
            last_line["text"] = line
            print("\r" + line.ljust(100), end="", flush=True)
        elif kind == "done":
            if last_line["text"]:
                print()
                last_line["text"] = ""
            print(f"\n✓ 完成：{event['output']}（{event['frames']} 帧，"
                  f"{event['duration']} 秒）", flush=True)
        elif kind == "error":
            if last_line["text"]:
                print()
                last_line["text"] = ""
            print(f"\n✗ 失败 [{event.get('kind')}]：{event.get('message')}", flush=True)

    try:
        result = run_project(
            project, args.work_dir, blender_exe=args.blender,
            on_event=on_event, cancel=cancel,
        )
    except KeyboardInterrupt:
        cancel.set()
        print("\n已请求中断；已完成的段会保留，重新运行会自动跳过它们。")
        return 130

    if result.ok:
        print(f"\n耗时 {result.elapsed_seconds / 60:.1f} 分钟；"
              f"渲了 {result.segments_rendered} 段，跳过 {result.segments_skipped} 段。")
        return 0
    for item in result.errors:
        print(f"\n错误：{item}")
    return 1


# --------------------------------------------------------------------------
# 入口
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="KomaFlow",
        description="KomaFlow —— MMD 本地渲染流水线",
    )
    parser.add_argument("--json", action="store_true", help="以 JSON 输出，便于脚本消费")
    sub = parser.add_subparsers(dest="command", required=True)

    p_adapters = sub.add_parser("adapters", help="列出 Blender 适配器与版本范围")
    p_adapters.set_defaults(func=cmd_adapters)

    p_discover = sub.add_parser("discover", help="自动探测本机 Blender（K-7.4）")
    p_discover.add_argument("--blender", help="额外追加一个候选路径")
    p_discover.set_defaults(func=cmd_discover)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--total", type=int, help="工程总帧数（含预热帧）")
        p.add_argument("--motion-length", type=int, dest="motion_length",
                       help="动作时长（帧）；与 --preroll 相加得到工程总帧数")
        p.add_argument("--preroll", type=int, default=seg.DEFAULT_PREROLL_FRAMES,
                       help=f"预热帧数，默认 {seg.DEFAULT_PREROLL_FRAMES}（K-1.1）")

    p_plan = sub.add_parser("plan", help="算分段计划（K-2）")
    add_common(p_plan)
    p_plan.add_argument("--limit", type=_limit_type, default=seg.DEFAULT_SEGMENT_LIMIT,
                        help=f"单段上限，默认 {seg.DEFAULT_SEGMENT_LIMIT}；none = 不分段")
    p_plan.add_argument("--work-dir", dest="work_dir",
                        help="给出工作目录则一并检查已有段产物，展示段级续渲效果")
    p_plan.add_argument("--ext", default="mp4", help="段产物扩展名，默认 mp4")
    p_plan.set_defaults(func=cmd_plan)

    p_samples = sub.add_parser("samples", help="算抽帧取样计划（K-3 / 设计取舍）")
    add_common(p_samples)
    p_samples.add_argument("--count", type=int, help="抽帧数量；默认取规则上限")
    p_samples.set_defaults(func=cmd_samples)

    p_stages = sub.add_parser("stages", help="列出一次渲染的阶段")
    add_common(p_stages)
    p_stages.set_defaults(func=cmd_stages)

    p_run = sub.add_parser("run", help="执行渲染（全链路）")
    p_run.add_argument("--project", help="工程档路径（.kfproj）；给了就不必再给素材参数")
    p_run.add_argument("--model", help="人物模型 .pmx / .pmd")
    p_run.add_argument("--motion", help="动作 .vmd")
    p_run.add_argument("--camera", help="镜头 .vmd（不给则自动生成正面机位）")
    p_run.add_argument("--stage", help="舞台 .pmx / .pmd")
    p_run.add_argument("--blend", help="已配好的 .blend 工程（路线 B）")
    p_run.add_argument("--name", help="工程名 / 输出基名")
    p_run.add_argument("--blender", help="指定用哪个 blender.exe（多个时必给，工具不代选）")
    p_run.add_argument("--work-dir", dest="work_dir", default="work", help="工作目录")
    p_run.add_argument("--output-dir", dest="output_dir", default="output", help="成片输出目录")
    p_run.add_argument("--preroll", type=int, help="预热帧数（默认 30）")
    p_run.add_argument("--limit", type=_limit_type, help="单段上限（默认 1000；none = 不分段）")
    p_run.add_argument("--width", type=int, help="分辨率宽（默认 2560）")
    p_run.add_argument("--height", type=int, help="分辨率高（默认 1440）")
    p_run.add_argument("--fps", type=int, help="帧率（默认 30）")
    p_run.add_argument("--quality", choices=("preview", "standard", "high"), help="画质档")
    p_run.add_argument("--frame-end", dest="frame_end", type=int, help="只渲到第 N 帧（试跑用）")
    p_run.set_defaults(func=cmd_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    _force_utf8_stdout()
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
