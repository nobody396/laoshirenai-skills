# 老实人AI Skills

面向老实人AI用户的公开 Agent Skills 仓库。每个 Skill 独立安装、独立配置；不要求安装 Plugin 或 MCP。

## Skill 目录

| Skill | 用途 | 状态 |
|---|---|---|
| [`laoshirenai-imagegen`](skills/laoshirenai-imagegen) | 通过独立生图 Key 调用 `gpt-image-2` 生成和编辑图片 | macOS / Linux / Windows 已测试 |

后续面向用户的 Skills 统一放在 `skills/<skill-name>/`，彼此不共享密钥或运行状态。

## laoshirenai-imagegen

让 Codex 使用独立的老实人AI生图 Key 调用 `gpt-image-2`。文本模型不需要具备生图能力。

```text
用户提出生图或图片编辑需求
→ Codex 自动选择 laoshirenai-imagegen
→ 本地运行 OpenAI 官方 imagegen CLI
→ 调用 https://api.laoshirenai.com/v1/images/*
→ 保存图片并返回项目内路径
```

## 安装

在 Codex 中调用 `$skill-installer`，让它安装：

```text
https://github.com/nobody396/laoshirenai-skills/tree/main/skills/laoshirenai-imagegen
```

Skill 安装后即可被 Codex 自动发现，不需要安装 Plugin 或 MCP。

## 首次配置

不要把 API Key 粘贴到聊天中。请在本机终端运行：

macOS / Linux：

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/laoshirenai-imagegen/scripts/setup.py"
```

Windows PowerShell：

```powershell
py -3 "$HOME\.codex\skills\laoshirenai-imagegen\scripts\setup.py"
```

这一个命令会隐藏读取 Key、准备固定版本的 OpenAI SDK、检查生图分组和 `gpt-image-2` 权限；不会产生付费图片，也不会把 Key 放进命令参数、Shell 历史或项目 `.env`。完成后直接在 Codex 中说“生成一张……”或“编辑这张图片……”。

## 固定接口

- Base URL：`https://api.laoshirenai.com/v1`
- 模型：`gpt-image-2`
- 生成：`POST /images/generations`
- 编辑：`POST /images/edits`

模型和 Base URL 由 Skill 固定，Prompt 不能改到第三方域名。生图 Key 必须来自独立生图分组，不能复用文本模型 Key。

## 来源

核心图片 CLI 来自 [OpenAI 官方 imagegen Skill](https://github.com/openai/skills/tree/main/skills/.system/imagegen)，以固定提交原样保留。老实人AI只增加独立凭据配置、固定路由、诊断和启动包装。

详见 [`NOTICE`](skills/laoshirenai-imagegen/NOTICE) 和 [`UPSTREAM.json`](skills/laoshirenai-imagegen/UPSTREAM.json)。
