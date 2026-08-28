---
name: laoshirenai-imagegen
description: Generate or edit raster images through the dedicated 老实人AI Images API. Use when Codex, Claude Code, or another coding agent should create a project image, transform existing images, combine references, or apply a mask even though the selected text model has no image-generation capability. Do not use for SVG, HTML/CSS, diagrams better expressed as code, or ordinary image inspection.
---

# 老实人AI 独立生图

Use the OpenAI official imagegen CLI through a thin 老实人AI launcher. The text model only plans the task and runs the CLI; all image work uses the dedicated image Key, `gpt-image-2`, and the standard Images endpoints.

## Required boundary

- Always run `scripts/imagegen.py`; never call the built-in image tool or `/v1/responses` image generation as a fallback.
- Base URL is fixed to `https://api.laoshirenai.com/v1` and the model is fixed to `gpt-image-2`.
- The image Key must come from the dedicated image group. Never reuse or overwrite the text-model Key.
- Never request, echo, log, or pass a Key as a command argument. The user configures it once through `scripts/configure.py`.
- Default to one image and one request. Do not automatically replay an ambiguous timeout because the upstream job may already have completed and been billed.
- Never overwrite an existing output unless the user explicitly requests it.

## First use

If `scripts/doctor.py --offline` reports that the Key is missing, ask the user to run this locally in an interactive terminal:

Use `python3` on macOS/Linux and `py -3` on Windows.

```bash
python3 /absolute/path/to/laoshirenai-imagegen/scripts/configure.py
```

Do not accept the Key in chat. After configuration, run:

```bash
python3 /absolute/path/to/laoshirenai-imagegen/scripts/doctor.py
```

`doctor.py` only checks `/v1/models`; it does not generate or charge for an image.

## Workflow

1. Decide whether the task is generation or editing.
2. Preserve the user's exact text and constraints. Use [the official prompt guidance](references/openai/prompting.md) only when prompt shaping materially helps.
3. Choose an output inside the current project when the result will be used by the project. Use `output/imagegen/` when the user provides no destination.
4. Run one of the commands below with absolute paths.
5. Inspect the saved image before claiming success. Report the absolute output path and the final prompt.

Generate:

```bash
python3 /absolute/path/to/laoshirenai-imagegen/scripts/imagegen.py generate \
  --prompt "<prompt>" \
  --size 1024x1024 \
  --quality low \
  --out /absolute/project/path/output/imagegen/result.png
```

Edit one or more images:

```bash
python3 /absolute/path/to/laoshirenai-imagegen/scripts/imagegen.py edit \
  --image /absolute/path/source.png \
  --prompt "<change and invariants>" \
  --quality low \
  --out /absolute/project/path/output/imagegen/edited.png
```

Add another `--image` for each reference. Add `--mask /absolute/path/mask.png` only when the user supplies or requests a real mask.

## Parameters

- Start with `1024x1024` and `quality=low` for fast drafts.
- Use `1536x1024` or `1024x1536` only when the requested composition needs it.
- Use medium/high quality only for a final or detail-sensitive asset.
- `n` is for variants of one prompt. Distinct prompts require distinct calls.
- Read [parameters](references/parameters.md) only when using less common image controls.
- Use [official sample prompts](references/openai/sample-prompts.md) only when a concrete template helps.

## Failure handling

- `doctor` cannot see `gpt-image-2`: the Key belongs to the wrong group; stop and request a dedicated image-group Key.
- HTTP 401/403: stop; do not retry or expose the response body if it may contain sensitive account details.
- HTTP 429/5xx before a confirmed result: report the failure. Do not automatically submit the same image job again.
- Output missing, empty, or undecodable: do not claim success.
- Editing unsupported by the deployed gateway: report that the image-edit release is not yet production-verified; do not silently switch to generation.

The upstream OpenAI files are pinned and unmodified. Attribution and the exact source commit are recorded in `NOTICE` and `UPSTREAM.json`.
