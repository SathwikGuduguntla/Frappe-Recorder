# Copyright (c) 2026, Sathwik Guduguntla  and contributors
# For license information, please see license.txt

"""Transcripts, summaries, highlights and SOPs for recordings.

The models are open source and run in the recording owner's browser (Whisper through
transformers.js for speech, a small Qwen/Llama model through WebLLM for writing), so this
works on any server or hosting plan and costs nothing per use. The browser sends back
only the finished text, which this module checks and stores.

The prompts live here, once, and are handed to the browser by `get_ai_config`.
"""

import json
import re

import frappe
from frappe import _
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


@frappe.whitelist(allow_guest=True)
def get_ai_config():
	"""What the browser needs to run the models, and the prompts to give them."""
	settings = _settings()
	return {
		"enabled": is_enabled(),
		"whisper_model": settings.whisper_model or "onnx-community/whisper-base",
		"llm_model": settings.llm_model or "Qwen2.5-1.5B-Instruct-q4f16_1-MLC",
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
		"whisper_models": settings.meta.get_field("whisper_model").options.split("\n"),
		"llm_models": settings.meta.get_field("llm_model").options.split("\n"),
	}


@frappe.whitelist(methods=["POST"])
def save_ai_settings(
	enabled: int = 1,
	whisper_model: str | None = None,
	llm_model: str | None = None,
):
	frappe.only_for("System Manager")
	settings = frappe.get_single(SETTINGS)
	settings.update(
		{
			"enabled": cint(enabled),
			"whisper_model": whisper_model or settings.whisper_model,
			"llm_model": llm_model or settings.llm_model,
		}
	)
	settings.save()
	return get_ai_settings()


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
