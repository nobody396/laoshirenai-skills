# 老实人AI Images 参数

The public contract is intentionally small:

| Capability | Endpoint | Required fields |
|---|---|---|
| Generate | `POST /v1/images/generations` | `model`, `prompt` |
| Edit | `POST /v1/images/edits` | `model`, `prompt`, one or more images |

Defaults:

- model: `gpt-image-2` (fixed by the launcher)
- size: `1024x1024`
- quality: `low` for drafts; `medium` or `high` for finals
- n: `1`
- output format: `png`

Supported edit inputs:

- one image
- multiple ordered images
- one optional mask matching the first image

The launcher preserves the OpenAI official CLI surface. Provider/model combinations can reject otherwise valid OpenAI parameters. Treat the deployed 老实人AI gateway and the selected image group as the source of truth; do not infer production support from the official reference alone.
