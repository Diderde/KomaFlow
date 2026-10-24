# Third-Party Notices (English)

This software bundles the components listed below. Everything else is written
for this project.

| Component | License | Notes |
| --- | --- | --- |
| **MMD still-render script** (`_internal/komaflow/adapters/vendor/MMD渲染.py`) | **MIT** (full text in `LICENSE_MMD渲染.txt`) | Runs inside Blender to render the three-view "Model view" feature. Integrated as an unmodified copy from the standalone open-source project "MMD render toolkit" v2.0.1. |
| **Blender** | GPL (varies by version) | **Not bundled.** Called as an external process only. The user installs it. |
| **mmd_tools** (Blender add-on) | GPL | **Not bundled.** Installed by the user inside Blender; used through Blender. |
| **FFmpeg** | LGPL v2.1+ / GPL (depends on build) | **Not bundled.** Used for muxing/encoding; user installs it and keeps it on PATH. |
| **Python / Tcl-Tk runtime** | PSF License / Tcl-Tk License | Bundled by PyInstaller as part of the frozen executable. |

## What this package does NOT contain

No character models, textures, motions, stages, music, fonts, or rendered
footage. No third-party code beyond the components listed above.

## Rights and takedown

If you believe something in this package infringes your rights, open an issue in
the repository Issues the repository with the specific file and reason (please put
`[侵权申诉]` / "takedown" in the subject). Verified issues are removed or
fixed promptly.

## Trademarks

"MMD", "MikuMikuDance", "VOCALOID", "Blender" and other names are trademarks of
their respective owners. This project is not affiliated with or endorsed by any
of them. Character names that may appear in third-party notices are used only
for identification (nominative use).
