# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Frappe app (installed in a bench at `../..`, Frappe v16) that records the screen and/or camera in the browser and produces a share link immediately. Two halves:

- `frappe_recorder/` — Python backend: three DocTypes plus whitelisted HTTP methods.
- `frontend/` — Vue 3 + frappe-ui + Tailwind SPA, built by Vite into the Python package.

## Commands

Bench commands run from the bench root (`../..`); replace `<site>` with a site that has the app installed.

```bash
# Backend tests
bench --site <site> set-config allow_tests true          # once per site
bench --site <site> run-tests --app frappe_recorder
bench --site <site> run-tests --module frappe_recorder.frappe_recorder.doctype.screen_recording.test_screen_recording
bench --site <site> run-tests --module frappe_recorder.frappe_recorder.doctype.screen_recording.test_screen_recording --test test_guest_cannot_record

# After changing a DocType JSON
bench --site <site> migrate

# Frontend (from frontend/)
yarn dev      # Vite on :8080, proxies API calls to the bench; open http://<site>:8080/recorder
yarn build    # or, from the bench root: bench build --app frappe_recorder

# Lint / format (ruff, ruff-format, prettier, eslint)
pre-commit run --all-files
```

- The Vite dev server needs `"ignore_csrf": 1` in the site config.
- Google Drive uploads run on the `long` queue, so a worker must be running (`bench start`) to exercise them.
- There are no frontend tests. Backend tests are in `test_screen_recording.py`, `test_google_drive_settings.py` and `test_recorder_ai_settings.py`.
- CI runs the tests on pushes to `develop` and on pull requests; the linter workflow adds Frappe semgrep rules and pip-audit.

## Architecture

### One SPA, two URL prefixes

`hooks.py` `website_route_rules` send both `/recorder/<path>` and `/r/<path>` to the `recorder` www page. `www/recorder.py` supplies boot data (CSRF token, site name, user); `www/recorder.html` is **generated** by `yarn build`, along with `public/frontend/` — both are gitignored, so never edit them and expect a fresh checkout to 404 until the frontend is built.

`frontend/src/router.js` owns the routes: `/recorder` (Record), `/recorder/library`, `/recorder/settings` (System Manager only) and `/r/:token` (Watch, public). The `beforeEach` guard redirects guests to `/login` for everything except the Watch route.

### Access control lives in `api.py`, not in DocType permissions

All three DocTypes grant permissions only to System Manager. Regular users never touch them through the Desk or `frappe.client`; every operation goes through `frappe_recorder/api.py`, which writes with `ignore_permissions=True` after doing its own check:

- `_get_owned_doc(token)` — logged in, and `doc.owner` or a System Manager.
- `_get_viewable_doc(token)` — anyone if `is_public`, otherwise the owner or a System Manager.

A new endpoint must go through one of these helpers. Recordings are addressed by their 12-character `token` (the share-link secret), never by the document name (`REC-#####`). `_serialize` returns a reduced field set to non-owners — keep owner-only fields (Drive status, file size, `is_public`) inside its `is_owner` block.

### Recording pipeline (chunked upload)

The share link has to exist before the upload finishes, so recording is three calls:

1. `create_recording` inserts the doc with status `Recording` and reserves the token and `video_file` name.
2. `upload_chunk` appends bytes to the file. Chunks are strictly ordered by `chunks_received`: a repeated index is acknowledged and ignored (client retry), a skipped index is an error. The row is locked for the write, and the file is truncated to `bytes_received` first, so a retry never duplicates bytes.
3. `finalize_recording` sets status `Ready`, saves the thumbnail, and queues the Drive upload if Drive is active.

The client side is `frontend/src/composables/useRecorder.js`, a state machine (`idle → countdown → recording ⇄ paused → finishing`, plus `failed`). `MediaRecorder` emits a blob every 2 s; `pumpUploads` sends them one request at a time, in order, batching whatever queued up meanwhile, retrying with backoff but giving up on any 4xx. All chunks are also kept in memory so a failed upload can still be downloaded locally. Discarding, or navigating away inside the app, deletes the server-side recording; closing or reloading the tab only shows the `beforeunload` warning and leaves it in `Recording`.

`composables/compositor.js` handles Screen + Camera mode by drawing both onto a canvas and recording the canvas track. Its frame loop is driven by a Web Worker timer on purpose — `requestAnimationFrame` stalls when the tab is in the background, which is exactly when people are presenting.

`tasks.close_abandoned_recordings` (daily) rescues recordings stuck in `Recording` for 12+ hours: kept as `Ready` if any bytes arrived, deleted otherwise.

### File storage and streaming

Paths come from helpers in `doctype/screen_recording/screen_recording.py`:

- Videos: `private/files/recorder/<token>.<ext>` — private, served only through `api.stream` (so switching sharing off really revokes access). `stream` supports HTTP Range for seeking.
- Thumbnails: `public/files/recorder/<token>.jpg`.

These are plain files, not Frappe `File` documents. `on_trash` deletes the local files and deliberately leaves any Google Drive copy.

If a recording has no local video but has a `drive_file_id`, `stream` proxies the bytes (and the Range header) from Google Drive.

### Google Drive (`drive.py`)

Uses only `requests` against the Drive REST API — the app has no Python dependencies beyond Frappe, keep it that way.

- Config is the `Google Drive Settings` single. There is no OAuth client: the target folder is shared as "Anyone with the link → Editor", and access tokens come from the **uploader**, a Google Apps Script web app the admin deploys once (`UPLOADER_SCRIPT` in `drive.py`, shown on the settings page with the site's generated `uploader_secret` written in). `_access_token()` POSTs the secret to `uploader_url` and caches the returned token in Redis for 10 minutes.
- Older link-shared folders need a `resourcekey` from their link; it is stored as `folder_resource_key` and sent in `X-Goog-Drive-Resource-Keys`.
- `upload_recording` is the background job (resumable upload in 16 MB pieces). It records `Failed` + `drive_error` on the doc rather than raising. `retry_pending_uploads` (hourly) re-runs `Pending`/`Failed` ones. When `keep_local_copy` is off, the local file is removed after upload and playback switches to the Drive proxy.
- `import_from_drive` creates `source = "Google Drive"` recordings for videos already in the folder; these never have a local file.

`Screen Recording.status` and `google_drive_status` are independent: the first tracks the recording lifecycle, the second the Drive copy.

### Transcripts and AI notes (`ai.py`, `frontend/src/ai/`)

The models run in the **recording owner's browser**, not on the server, so the feature works on any host (including shared Frappe Cloud plans) with no Python dependencies and no API keys.

- `src/ai/whisper.worker.js` runs Whisper through `@huggingface/transformers` (WebGPU, else WASM); `src/ai/llm.worker.js` hosts WebLLM; `src/ai/engine.js` drives both: it downloads the video from `api.stream`, decodes its audio at 16 kHz, transcribes in 5-minute blocks, and splits long transcripts into parts for the ~4K-token browser models. `components/AiPanel.vue` is the Watch page UI (Assistant · Highlights · Transcript · SOP).
- The server only stores and serves results: `save_transcript` / `save_insights` / `save_sop` (owner, via `_get_owned_doc`) clean what the browser sends; `get_ai` (via `_get_viewable_doc`) is what viewers read. Text is stored as JSON/Markdown in Long Text fields on `Screen Recording`, with independent `transcript_status` / `insights_status` / `sop_status`.
- The prompts live once, in `ai.PROMPTS` (Python format strings), and reach the browser through `get_ai_config`; `engine.fill` fills them the same way.
- Optional Ollama (`Recorder AI Settings.ollama_url`): `generate_on_server` queues `run_on_server` on the `long` queue for owners without WebGPU, and `ask` answers viewers' questions (rate-limited). Ollama is called with `requests`.
- `frontend/package.json` replaces `sharp` and `onnxruntime-node` with empty stubs (`frontend/stubs/`): transformers.js only needs them in Node, and installing them downloads native binaries.

### Frontend API layer

`frontend/src/api.js` is the single place that names backend methods; pages call `api.*` rather than `call()` directly. `upload_chunk` uses raw `fetch` with `FormData` and `window.csrf_token` because the body is binary. `session` is a shared reactive object populated once by `loadSession()`.

`Recording Folder` (a plain DocType with a parent link and `is_group`, not a Frappe tree/`NestedSet`) and the `folder` link on `Screen Recording` exist in the schema but nothing in `api.py` or the frontend uses them yet.

## Conventions

- Python: tabs, double quotes, 110-column lines (ruff config in `pyproject.toml`). User-facing strings go through `_()`.
- Frontend: no semicolons, single quotes (`frontend/.prettierrc.json`); the existing files use 2-space indent and long lines. That file does not set indent or width, and the root `.editorconfig` prescribes tabs and 99 columns for `*.js`/`*.vue`, which Prettier also reads — so `pre-commit run --all-files` may reformat `frontend/src` to tabs. Check the diff before committing a formatting run.
- `@` aliases `frontend/src`.
