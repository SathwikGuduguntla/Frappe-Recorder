# Copyright (c) 2026, Sathwik Guduguntla  and contributors
# For license information, please see license.txt

"""Transcripts, summaries, highlights and SOPs for recordings.

The models are open source and run in the recording owner's browser (Whisper through
transformers.js for speech, a small Qwen/Llama model through WebLLM for writing), so this
works on any server or hosting plan and costs nothing per use. The browser sends back
only the finished text, which this module checks and stores.

Optionally an admin can point the app at an Ollama server. Summaries and SOPs can then be
made there, for owners whose device can't run the writing model, and viewers can ask
questions about a video.

The prompts live here, once, and are handed to the browser by `get_ai_config`, so both
paths write the same way.
"""

import json
import re

import frappe
import requests
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint, flt

from frappe_recorder.api import _get_owned_doc, _get_viewable_doc, _is_owner

SETTINGS = "Recorder AI Settings"
DOCTYPE = "Screen Recording"
STATUSES = ("Not Started", "Processing", "Ready", "Failed")

MAX_SEGMENTS = 20000
MAX_SEGMENT_TEXT = 2000
MAX_SUMMARY = 50000
MAX_SOP = 100000
MAX_HIGHLIGHTS = 30
MAX_QUESTIONS = 5
MAX_QUESTION_LENGTH = 500

# Roughly how much transcript one request may carry. The browser models read about
# 4,000 tokens at a time, so the browser splits long transcripts itself; this is the
# Ollama equivalent.
OLLAMA_CHUNK_CHARS = 24000
OLLAMA_TIMEOUT = 600

SYSTEM_PROMPT = (
	"You write clear notes about screen recordings from their transcripts. The transcript was "
	"made by speech recognition, so it can contain misheard words; read through them. Use only "
	"what the transcript says: never invent features, names, numbers or steps. Times are "
	"written as m:ss and refer to the position in the video."
)

# Shape of the summary reply. The browser model is held to it while it writes (WebLLM's
# JSON mode needs an explicit schema), so the reply always parses.
INSIGHTS_SCHEMA = {
	"type": "object",
	"properties": {
		"summary": {"type": "string"},
		"highlights": {
			"type": "array",
			"items": {
				"type": "object",
				"properties": {"time": {"type": "string"}, "title": {"type": "string"}},
				"required": ["time", "title"],
			},
		},
		"questions": {"type": "array", "items": {"type": "string"}},
	},
	"required": ["summary", "highlights", "questions"],
}

PROMPTS = {
	"insights": (
		"Here is the transcript of a screen recording, one line per segment, each starting with "
		"its time.\n\n{transcript}\n\n"
		"Reply with JSON only, in this shape:\n"
		'{{"summary": "...", "highlights": [{{"time": "m:ss", "title": "..."}}], '
		'"questions": ["..."]}}\n'
		"- summary: Markdown with these sections: ## Overview (2-3 sentences), ## Key points "
		"(bullets), ## Questions raised (bullets, or 'None noted.'), ## Open questions (bullets, "
		"or 'None noted.').\n"
		"- highlights: 3 to 8 key moments, in order, each with the time it starts and a short title.\n"
		"- questions: 3 short questions a viewer might ask about this video."
	),
	"part": (
		"Here is part of the transcript of a screen recording, from {start} to {end}, one line per "
		"segment, each starting with its time.\n\n{transcript}\n\n"
		"Write 5 to 8 Markdown bullet points covering what happens in this part. Start each bullet "
		"with the time it refers to, like '- (2:15) ...'. Reply with the bullets only."
	),
	"insights_from_parts": (
		"Here are notes on each part of a screen recording, in order. Each bullet starts with the "
		"time it refers to.\n\n{transcript}\n\n"
		"Reply with JSON only, in this shape:\n"
		'{{"summary": "...", "highlights": [{{"time": "m:ss", "title": "..."}}], '
		'"questions": ["..."]}}\n'
		"- summary: Markdown with these sections: ## Overview (2-3 sentences), ## Key points "
		"(bullets), ## Questions raised (bullets, or 'None noted.'), ## Open questions (bullets, "
		"or 'None noted.').\n"
		"- highlights: 3 to 8 key moments, in order, each with the time it starts and a short title.\n"
		"- questions: 3 short questions a viewer might ask about this video."
	),
	"sop": (
		"Here is the transcript of a screen recording that shows how to do something, one line per "
		"segment, each starting with its time.\n\n{transcript}\n\n"
		"Write a standard operating procedure (SOP) in Markdown that someone could follow without "
		"watching the video:\n"
		"# <title>\n## Purpose\n## Before you start (what is needed, or 'Nothing.')\n"
		"## Steps (a numbered list; end each step with the time it is shown, like (2:15))\n"
		"## Tips (bullets, or leave the section out)\n"
		"Reply with the Markdown only."
	),
	"ask": (
		"Here is the transcript of a screen recording, one line per segment, each starting with "
		"its time.\n\n{transcript}\n\n"
		"Answer this question about the video: {question}\n"
		"Use only the transcript. If it does not cover the question, say so in one sentence. "
		"Mention the time when it helps, like (2:15). Keep the answer short."
	),
}


# ---------------------------------------------------------------- settings


def _settings():
	return frappe.get_cached_doc(SETTINGS)


def is_enabled() -> bool:
	return bool(cint(_settings().enabled))


def server_ai_available() -> bool:
	settings = _settings()
	return bool(is_enabled() and settings.ollama_url and settings.ollama_model)


@frappe.whitelist(allow_guest=True)
def get_ai_config():
	"""What the browser needs to run the models, and the prompts to give them."""
	settings = _settings()
	return {
		"enabled": is_enabled(),
		"whisper_model": settings.whisper_model or "onnx-community/whisper-base",
		"llm_model": settings.llm_model or "Qwen2.5-1.5B-Instruct-q4f16_1-MLC",
		"server_ai": server_ai_available(),
		"system_prompt": SYSTEM_PROMPT,
		"prompts": PROMPTS,
		"insights_schema": INSIGHTS_SCHEMA,
	}


@frappe.whitelist()
def get_ai_settings():
	frappe.only_for("System Manager")
	settings = frappe.get_single(SETTINGS)
	return {
		"enabled": cint(settings.enabled),
		"whisper_model": settings.whisper_model,
		"llm_model": settings.llm_model,
		"ollama_url": settings.ollama_url,
		"ollama_model": settings.ollama_model,
		"whisper_models": settings.meta.get_field("whisper_model").options.split("\n"),
		"llm_models": settings.meta.get_field("llm_model").options.split("\n"),
	}


@frappe.whitelist(methods=["POST"])
def save_ai_settings(
	enabled: int = 1,
	whisper_model: str | None = None,
	llm_model: str | None = None,
	ollama_url: str | None = None,
	ollama_model: str | None = None,
):
	frappe.only_for("System Manager")
	settings = frappe.get_single(SETTINGS)
	ollama_url = (ollama_url or "").strip().rstrip("/")
	if ollama_url and not re.match(r"^https?://[^\s/]+", ollama_url):
		frappe.throw(_("The Ollama URL should look like http://localhost:11434."))
	settings.update(
		{
			"enabled": cint(enabled),
			"whisper_model": whisper_model or settings.whisper_model,
			"llm_model": llm_model or settings.llm_model,
			"ollama_url": ollama_url,
			"ollama_model": (ollama_model or "").strip(),
		}
	)
	settings.save()
	return get_ai_settings()


@frappe.whitelist(methods=["POST"])
def test_ollama():
	"""Checks the Ollama server answers and has the chosen model."""
	frappe.only_for("System Manager")
	settings = _settings()
	if not settings.ollama_url:
		frappe.throw(_("Add the Ollama URL first."))
	try:
		response = requests.get(f"{settings.ollama_url}/api/tags", timeout=15)
		response.raise_for_status()
		models = [m.get("name") for m in response.json().get("models", [])]
	except (requests.RequestException, ValueError):
		frappe.throw(
			_("Could not reach Ollama at {0}. Is it running, and reachable from this server?").format(
				settings.ollama_url
			)
		)
	wanted = settings.ollama_model or ""
	found = any(name == wanted or name.split(":")[0] == wanted for name in models)
	return {"models": models, "found": found}


# ---------------------------------------------------------------- reading


def _load(value, default):
	try:
		return json.loads(value) if value else default
	except ValueError:
		return default


@frappe.whitelist(allow_guest=True)
def get_ai(token: str):
	"""Everything made for a recording. Anyone who can watch it can read it."""
	doc = _get_viewable_doc(token)
	data = {
		"transcript_status": doc.transcript_status or "Not Started",
		"language": doc.transcript_language,
		"transcript": _load(doc.transcript, []),
		"insights_status": doc.insights_status or "Not Started",
		"summary": doc.summary or "",
		"highlights": _load(doc.highlights, []),
		"questions": _load(doc.suggested_questions, []),
		"sop_status": doc.sop_status or "Not Started",
		"sop": doc.sop or "",
	}
	if _is_owner(doc):
		data["ai_error"] = doc.ai_error
		data["ai_model"] = doc.ai_model
	return data


# ---------------------------------------------------------------- saving (from the owner's browser)


def _check_enabled():
	if not is_enabled():
		frappe.throw(_("Transcripts and AI are turned off on this site."))


def _clean_text(value, limit: int) -> str:
	return frappe.utils.strip_html(str(value or "")).strip()[:limit]


def _parse(value, kind=list):
	if isinstance(value, str):
		value = _load(value, None)
	if not isinstance(value, kind):
		frappe.throw(_("Invalid data."))
	return value


@frappe.whitelist(methods=["POST"])
def save_transcript(token: str, segments, language: str | None = None, model: str | None = None):
	"""Stores the transcript the owner's browser made."""
	_check_enabled()
	doc = _get_owned_doc(token)
	segments = _parse(segments)[:MAX_SEGMENTS]

	cleaned = []
	for segment in segments:
		if not isinstance(segment, dict):
			continue
		text = _clean_text(segment.get("text"), MAX_SEGMENT_TEXT)
		if not text:
			continue
		start = max(flt(segment.get("start")), 0)
		end = max(flt(segment.get("end")), start)
		cleaned.append({"start": round(start, 2), "end": round(end, 2), "text": text})
	cleaned.sort(key=lambda s: s["start"])

	doc.db_set(
		{
			"transcript": json.dumps(cleaned, ensure_ascii=False),
			"transcript_language": _clean_text(language, 20) or None,
			"transcript_status": "Ready",
			"ai_model": _clean_text(model, 140) or None,
			"ai_error": None,
		},
		update_modified=False,
	)
	return get_ai(token)


@frappe.whitelist(methods=["POST"])
def save_insights(
	token: str, summary: str | None = None, highlights=None, questions=None, model: str | None = None
):
	"""Stores the summary, highlights and suggested questions the owner's browser wrote."""
	_check_enabled()
	doc = _get_owned_doc(token)
	data = {
		"summary": summary,
		"highlights": _parse(highlights or "[]"),
		"questions": _parse(questions or "[]"),
	}
	_store_insights(doc, data, model)
	return get_ai(token)


@frappe.whitelist(methods=["POST"])
def save_sop(token: str, sop: str, model: str | None = None):
	_check_enabled()
	doc = _get_owned_doc(token)
	_store_sop(doc, sop, model)
	return get_ai(token)


@frappe.whitelist(methods=["POST"])
def report_failure(token: str, kind: str, error: str | None = None):
	"""The owner's browser could not finish a step (no WebGPU, out of memory, ...)."""
	doc = _get_owned_doc(token)
	field = _status_field(kind)
	# A late report from an earlier attempt must not hide a result saved since.
	if doc.get(field) != "Ready":
		doc.db_set({field: "Failed", "ai_error": _clean_text(error, 500) or None}, update_modified=False)
	return get_ai(token)


@frappe.whitelist(methods=["POST"])
def reset_ai(token: str):
	"""Clears everything, so the owner can transcribe again."""
	doc = _get_owned_doc(token)
	doc.db_set(
		{
			"transcript": None,
			"transcript_language": None,
			"transcript_status": "Not Started",
			"summary": None,
			"highlights": None,
			"suggested_questions": None,
			"insights_status": "Not Started",
			"sop": None,
			"sop_status": "Not Started",
			"ai_model": None,
			"ai_error": None,
		},
		update_modified=False,
	)
	return get_ai(token)


def _status_field(kind: str) -> str:
	fields = {"transcript": "transcript_status", "insights": "insights_status", "sop": "sop_status"}
	if kind not in fields:
		frappe.throw(_("Unknown step: {0}").format(kind))
	return fields[kind]


def _store_insights(doc, data: dict, model: str | None):
	summary = _clean_markdown(data.get("summary"), MAX_SUMMARY)
	duration = flt(doc.duration_seconds) or None

	highlights = []
	for item in (data.get("highlights") if isinstance(data.get("highlights"), list) else [])[:MAX_HIGHLIGHTS]:
		if not isinstance(item, dict):
			continue
		title = _clean_text(item.get("title"), 200)
		seconds = parse_time(item.get("time"))
		if not title or seconds is None or (duration and seconds > duration + 5):
			continue
		highlights.append({"time": seconds, "title": title})
	highlights.sort(key=lambda h: h["time"])

	questions = [
		_clean_text(q, 300)
		for q in (data.get("questions") if isinstance(data.get("questions"), list) else [])[:MAX_QUESTIONS]
	]
	questions = [q for q in questions if q]

	if not summary:
		frappe.throw(_("The summary is empty."))
	doc.db_set(
		{
			"summary": summary,
			"highlights": json.dumps(highlights, ensure_ascii=False),
			"suggested_questions": json.dumps(questions, ensure_ascii=False),
			"insights_status": "Ready",
			"ai_model": _clean_text(model, 140) or doc.ai_model,
			"ai_error": None,
		},
		update_modified=False,
	)


def _store_sop(doc, sop: str | None, model: str | None):
	sop = _clean_markdown(sop, MAX_SOP)
	if not sop:
		frappe.throw(_("The SOP is empty."))
	doc.db_set(
		{
			"sop": sop,
			"sop_status": "Ready",
			"ai_model": _clean_text(model, 140) or doc.ai_model,
			"ai_error": None,
		},
		update_modified=False,
	)


def _clean_markdown(value, limit: int) -> str:
	# The frontend escapes everything before rendering its small Markdown subset, so this
	# only has to drop HTML a model may have produced and cap the size.
	text = re.sub(r"<[^>]+>", "", str(value or ""))
	return text.strip()[:limit]


def parse_time(value) -> float | None:
	"""'2:15', '1:02:15' or a number of seconds -> seconds."""
	if isinstance(value, int | float):
		return max(float(value), 0)
	match = re.fullmatch(r"\s*(?:(\d+):)?(\d{1,2}):(\d{2})(?:\.\d+)?\s*", str(value or ""))
	if not match:
		return None
	hours, minutes, seconds = (int(part or 0) for part in match.groups())
	return float(hours * 3600 + minutes * 60 + seconds)


def format_time(seconds) -> str:
	seconds = int(flt(seconds))
	hours, rest = divmod(seconds, 3600)
	minutes, secs = divmod(rest, 60)
	return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def transcript_lines(segments: list) -> list[str]:
	return [f"[{format_time(s['start'])}] {s['text']}" for s in segments]


# ---------------------------------------------------------------- optional Ollama server


@frappe.whitelist(methods=["POST"])
def generate_on_server(token: str, kind: str):
	"""For owners whose browser can't run the writing model: let the Ollama server do it."""
	if not server_ai_available():
		frappe.throw(_("No Ollama server is set up on this site."))
	if kind not in ("insights", "sop"):
		frappe.throw(_("Unknown step: {0}").format(kind))
	doc = _get_owned_doc(token)
	if doc.transcript_status != "Ready":
		frappe.throw(_("Make the transcript first."))

	doc.db_set({_status_field(kind): "Processing", "ai_error": None}, update_modified=False)
	frappe.enqueue(
		"frappe_recorder.ai.run_on_server",
		queue="long",
		timeout=3600,
		enqueue_after_commit=True,
		job_id=f"frappe_recorder:ai:{kind}:{doc.name}",
		deduplicate=True,
		recording=doc.name,
		kind=kind,
	)
	return get_ai(token)


def run_on_server(recording: str, kind: str):
	"""Background job (long queue)."""
	doc = frappe.get_doc(DOCTYPE, recording)
	model = f"ollama:{_settings().ollama_model}"
	frappe.db.savepoint("recorder_ai")
	try:
		segments = _load(doc.transcript, [])
		if kind == "insights":
			_store_insights(doc, _server_insights(segments), model)
		else:
			text = "\n".join(transcript_lines(segments))[: OLLAMA_CHUNK_CHARS * 4]
			_store_sop(doc, _ollama(PROMPTS["sop"].format(transcript=text)), model)
	except Exception as e:
		frappe.db.rollback(save_point="recorder_ai")
		doc.db_set({_status_field(kind): "Failed", "ai_error": str(e)[:500]}, update_modified=False)
		frappe.log_error(title=f"Recorder: AI {kind} failed")
	frappe.db.commit()


def _server_insights(segments: list) -> dict:
	parts = split_transcript(segments, OLLAMA_CHUNK_CHARS)
	if len(parts) <= 1:
		reply = _ollama(
			PROMPTS["insights"].format(transcript="\n".join(transcript_lines(segments))), json_mode=True
		)
	else:
		notes = []
		for part in parts:
			notes.append(
				_ollama(
					PROMPTS["part"].format(
						start=format_time(part[0]["start"]),
						end=format_time(part[-1]["end"]),
						transcript="\n".join(transcript_lines(part)),
					)
				)
			)
		reply = _ollama(PROMPTS["insights_from_parts"].format(transcript="\n\n".join(notes)), json_mode=True)
	data = _load(reply, None)
	if not isinstance(data, dict):
		frappe.throw(_("The model did not return the expected format. Try again."))
	return data


def split_transcript(segments: list, max_chars: int) -> list[list]:
	"""Consecutive groups of segments whose text stays under `max_chars`."""
	parts, current, size = [], [], 0
	for segment in segments:
		length = len(segment["text"]) + 10
		if current and size + length > max_chars:
			parts.append(current)
			current, size = [], 0
		current.append(segment)
		size += length
	if current:
		parts.append(current)
	return parts


def _ollama(prompt: str, json_mode: bool = False, timeout: int = OLLAMA_TIMEOUT) -> str:
	settings = _settings()
	body = {
		"model": settings.ollama_model,
		"messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
		"stream": False,
		"options": {"temperature": 0.2, "num_ctx": 16384},
	}
	if json_mode:
		body["format"] = "json"
	try:
		response = requests.post(f"{settings.ollama_url}/api/chat", json=body, timeout=timeout)
	except requests.RequestException as e:
		frappe.throw(_("Could not reach the Ollama server: {0}").format(e))
	if not response.ok:
		frappe.throw(_("The Ollama server returned an error: {0}").format(response.text[:300]))
	return (response.json().get("message") or {}).get("content", "").strip()


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=20, seconds=60 * 60)
def ask(token: str, question: str):
	"""Viewers' questions, answered by the Ollama server. (Owners can also ask in their
	own browser, which needs no server.)"""
	if not server_ai_available():
		frappe.throw(_("Questions need an Ollama server, which this site has not set up."))
	doc = _get_viewable_doc(token)
	question = _clean_text(question, MAX_QUESTION_LENGTH)
	if not question:
		frappe.throw(_("Type a question first."))
	segments = _load(doc.transcript, [])
	if not segments:
		frappe.throw(_("This video has no transcript yet."))

	text = "\n".join(relevant_lines(segments, question, OLLAMA_CHUNK_CHARS))
	answer = _ollama(PROMPTS["ask"].format(transcript=text, question=question), timeout=110)
	return {"answer": _clean_markdown(answer, 5000)}


def relevant_lines(segments: list, question: str, max_chars: int) -> list[str]:
	"""The whole transcript when it fits; otherwise the segments sharing the most words with
	the question, plus their neighbours, kept in video order."""
	lines = transcript_lines(segments)
	if sum(len(line) + 1 for line in lines) <= max_chars:
		return lines

	words = {w for w in re.findall(r"\w{3,}", question.lower())}
	scores = [len(words & set(re.findall(r"\w{3,}", s["text"].lower()))) for s in segments]
	ranked = sorted(range(len(segments)), key=lambda i: scores[i], reverse=True)

	chosen, size = set(), 0
	for index in ranked:
		for i in (index - 1, index, index + 1):
			if 0 <= i < len(lines) and i not in chosen and size + len(lines[i]) + 1 <= max_chars:
				chosen.add(i)
				size += len(lines[i]) + 1
		if size >= max_chars * 0.9:
			break
	return [lines[i] for i in sorted(chosen)]
