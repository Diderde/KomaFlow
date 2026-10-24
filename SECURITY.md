# 安全策略

## 报告问题

如果发现本项目的安全问题（例如命令注入、路径穿越、任意文件写入），
请**不要**开公开 Issue。用本仓库的 **Security → Report a vulnerability** 私密报告，或在 Issue 里只写“请提供私密联系方式”，维护者会主动私信你。

请附：受影响的版本、复现步骤、影响范围。

## 已知边界（不是漏洞）

- 程序会启动 `blender.exe` 与 `ffmpeg.exe` 子进程，参数以**列表**传递，不经 shell。
- 「安装 mmd_tools」会让 Blender 访问官方扩展库，这是用户主动触发的行为。
- 未签名的 exe 会被 SmartScreen 提示，属预期。
