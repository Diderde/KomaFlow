# KomaFlow

> English: [README.en.md](README.en.md)

把 MMD 的**模型（.pmx）**和**动作（.vmd）**拖进来，调用你电脑上已装的 Blender
完成「装配 → 物理预热 → 分段渲染 → 合并出片」，输出 MP4 或带透明通道的 MOV。

Windows 独立程序（不是 Blender 插件）。**V1.1.0-beta**。

---

## 它做什么

| 步骤 | 说明 |
|---|---|
| 装配 | 导入 PMX / 追加 `.blend` 舞台 / 挂 VMD 动作与镜头 |
| 物理 | 用 `mmd_tools` 的 `build_rig` 建骨骼跟随约束，再烘焙点缓存 |
| 预热 | 默认 30 帧静置，让头发裙摆先收敛；第 30 帧起动作才生效 |
| 渲染 | 按段渲染（每段一个 Blender 进程），断点续渲 |
| 出片 | 外部 FFmpeg 合并；透明走 PNG 序列 → 带 alpha 的 MOV |

## 环境要求

| 需要 | 说明 |
|---|---|
| **Windows 10 / 11 64 位** | 只支持 Windows |
| **Blender 5.0 – 5.99** | 实测 5.2.3 LTS；**不随包分发**，用你自己装的 |
| **mmd_tools 扩展** | `bl_ext.blender_org.mmd_tools`；界面里可一键触发安装 |
| **FFmpeg** | 需自备并加进 `PATH`；**同样不随包分发** |
| Python 3.10+ | 仅源码运行时需要；**零 pip 依赖** |

## 使用

**方式一：发行包**

1. 下载 Release 里的 `KomaFlow_V1.1.0-beta.zip` 并解压
2. 双击 `KomaFlow.exe`
3. 拖入 `.pmx` → 拖入 `.vmd` → 点「开始渲染」

**方式二：源码运行**

```bat
python run.py
```

## 关键设计（几个常见疑问）

- **不打包 Blender、不打包 FFmpeg**：两者都是各自的许可，本项目只通过**子进程**调用，
  不分发、不链接，因此仓库里不含 GPL 代码。
- **不内置任何素材**：仓库里没有模型、动作、贴图、成片。
- **零运行时依赖**：只用 Python 标准库 + Tk。
- **工程可交付**：装配完成会在出图目录留一份 `.blend`（含烘焙好的物理），
  可以直接用 Blender 打开改材质 / 灯光 / 镜头，再回来渲。
- **联网只有一处**：界面里的「安装 mmd_tools」会让 Blender 去官方扩展库下载；不点就不会联网。
- **不改系统**：不写注册表、不装服务、不采集遥测。

## 目录

```
src/komaflow/                      程序本体
  core/                            纯逻辑（不依赖 bpy / tk）
  adapters/                        调 Blender、调 FFmpeg
  adapters/vendor/                 MMD 静帧渲染器（MIT，见同目录 LICENSE / NOTICE）
  ui/                              Tk 界面
tests/                             279 项单元测试
tools/                             打包（PyInstaller spec）、LOGO 生成、资源导出
docs/                              架构说明、使用细节
```

跑测试：

```bat
set PYTHONPATH=src
python -m unittest discover -s tests -t .
```

## 语言包（可选）

界面默认中文。想要英文界面，安装可选的英文语言包即可：

1. 下载 `KomaFlow_语言包_英文_v1.1.zip`
2. 解压后把 `locales` 文件夹放到 `KomaFlow.exe` 同级目录
3. 重新打开程序 —— 界面变英文

卸载：删掉该文件夹即可恢复中文。也可以放到
`%APPDATA%\KomaFlow\locales\en.json`。

想自己翻译或补漏，直接改 `locales/en.json`：它就是一个
`{"中文原文": "English"}` 的扁平字典。

## 已知限制

- **未做代码签名**：exe 首次运行会被 SmartScreen 拦，需点「更多信息 → 仍要运行」。
- **未配置 CI**：测试依赖 Tk，只在 Windows 上跑过。
- **物理是近似解算**：`build_rig` 用非碰撞距离约束近似 MMD 软约束，个别模型可能穿插或偏摆。
- **只在 Blender 5.x + mmd_tools 4.5.x 上验证**。

## 合规与素材

本项目**不含**任何模型 / 动作 / 贴图 / 成片，也**不授予**任何素材的使用权。
MMD 模型与动作的版权属于各自作者，常见规约为「禁止二次配布 / 禁止商用」——
使用前请自行阅读原作者说明。

## 关于代码生成方式

本项目的代码由 **AI 辅助生成**、经人工审阅与测试。除 `adapters/vendor/` 下的
第三方渲染器（MIT，已标注来源）外，未复制他人代码。

## 许可证

- 本项目代码：**MIT**（见 [LICENSE](LICENSE)）
- `adapters/vendor/MMD渲染.py`：**MIT**，版权归其作者，随附 `LICENSE_MMD渲染.txt`
  与 `NOTICE_MMD渲染.md`
- Blender、mmd_tools：**GPL**，本项目不分发、不修改，仅子进程调用

第三方组件清单见 [第三方来源与许可_发布版.md](第三方来源与许可_发布版.md)。

## 联系

| 渠道 | 用来做什么 |
|---|---|
| **GitHub Issue** | 日常问题、改进建议、使用报障 |
| **Issue（标注【侵权申诉】）** | 侵权申诉 / 隐私问题 / 商务合作，请附具体文件与理由 |

⚠️ 侵权与隐私问题请**走邮箱**，不要开公开 Issue（避免二次传播）。
