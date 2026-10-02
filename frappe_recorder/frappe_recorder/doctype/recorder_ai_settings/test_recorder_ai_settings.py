# Copyright (c) 2026, Sathwik Guduguntla  and Contributors
# See license.txt

import json
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from frappe_recorder import ai, api

OWNER = "recorder-ai-owner@example.com"
VIEWER = "recorder-ai-viewer@example.com"

SEGMENTS = [
	{"start": 0, "end": 4.2, "text": "Open the Payment Entry list."},
	{"start": 25, "end": 31, "text": "Click New and pick the customer."},
	{"start": 99.5, "end": 104, "text": "Save it, and it stays in <b>draft</b> until submitted."},
]


def make_user(email):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		).insert(ignore_permissions=True)


def set_settings(**values):
	settings = frappe.get_single(ai.SETTINGS)
	settings.update({"enabled": 1, "ollama_url": None, "ollama_model": "qwen2.5:7b", **values})
	settings.save(ignore_permissions=True)


def ollama_reply(content):
	response = MagicMock()
	response.ok = True
	response.json.return_value = {"message": {"content": content}}
	return response


class TestRecorderAI(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_user(OWNER)
		make_user(VIEWER)

	def setUp(self):
		frappe.set_user("Administrator")
		set_settings()
		frappe.set_user(OWNER)
		self.token = api.create_recording(title="Payments")["token"]
		frappe.db.set_value(api.DOCTYPE, {"token": self.token}, {"status": "Ready", "duration_seconds": 120})

	def tearDown(self):
		frappe.set_user("Administrator")
		set_settings()

	def test_owner_saves_transcript_and_anyone_with_the_link_reads_it(self):
		data = ai.save_transcript(self.token, json.dumps(SEGMENTS), language="en", model="whisper-base")
		self.assertEqual(data["transcript_status"], "Ready")
		self.assertEqual(len(data["transcript"]), 3)
		# HTML from a model or a tampered request is dropped
		self.assertEqual(data["transcript"][2]["text"], "Save it, and it stays in draft until submitted.")

		frappe.set_user("Guest")
		data = ai.get_ai(self.token)
		self.assertEqual(data["language"], "en")
		self.assertEqual(data["transcript"][1]["start"], 25)
		self.assertNotIn("ai_error", data)
		self.assertEqual(api.get_recording(self.token)["transcript_status"], "Ready")

	def test_only_the_owner_can_save(self):
		frappe.set_user(VIEWER)
		with self.assertRaises(frappe.PermissionError):
			ai.save_transcript(self.token, json.dumps(SEGMENTS))
		frappe.set_user("Guest")
		with self.assertRaises(frappe.AuthenticationError):
			ai.save_sop(self.token, "# Hijacked")

	def test_private_recording_ai_is_private_too(self):
		ai.save_transcript(self.token, json.dumps(SEGMENTS))
		api.update_recording(self.token, is_public=0)
		frappe.set_user(VIEWER)
		with self.assertRaises(frappe.PermissionError):
			ai.get_ai(self.token)

	def test_insights_are_cleaned(self):
		data = ai.save_insights(
			self.token,
			summary="## Overview\nPayments <script>alert(1)</script>are drafts.",
			highlights=json.dumps(
				[
					{"time": "1:39", "title": "Draft created"},
					{"time": "0:25", "title": "New entry"},
					{"time": "9:59", "title": "After the end of the video"},
					{"time": "soon", "title": "No time"},
				]
			),
			questions=json.dumps(["Can drafts be edited?", "", "Are reminders sent?"]),
		)
		self.assertEqual(data["insights_status"], "Ready")
		self.assertNotIn("<script>", data["summary"])
		self.assertEqual(
			data["highlights"],
			[{"time": 25.0, "title": "New entry"}, {"time": 99.0, "title": "Draft created"}],
		)
		self.assertEqual(data["questions"], ["Can drafts be edited?", "Are reminders sent?"])

	def test_failure_and_reset(self):
		data = ai.report_failure(self.token, "insights", "This device has no WebGPU.")
		self.assertEqual(data["insights_status"], "Failed")
		self.assertEqual(data["ai_error"], "This device has no WebGPU.")
		# a late failure report from an earlier attempt doesn't undo a saved transcript
		ai.save_transcript(self.token, json.dumps(SEGMENTS))
		self.assertEqual(ai.report_failure(self.token, "transcript", "late")["transcript_status"], "Ready")
		data = ai.reset_ai(self.token)
		self.assertEqual(data["insights_status"], "Not Started")
		self.assertIsNone(data["ai_error"])

	def test_turned_off(self):
		frappe.set_user("Administrator")
		set_settings(enabled=0)
		frappe.set_user(OWNER)
		self.assertFalse(ai.get_ai_config()["enabled"])
		with self.assertRaises(frappe.ValidationError):
			ai.save_transcript(self.token, json.dumps(SEGMENTS))

	def test_config_gives_the_browser_the_prompts(self):
		config = ai.get_ai_config()
		self.assertTrue(config["enabled"])
		self.assertFalse(config["server_ai"])
		self.assertIn("{transcript}", config["prompts"]["insights"])
		self.assertEqual(set(config["prompts"]), {"insights", "part", "insights_from_parts", "sop", "ask"})
		# WebLLM's JSON mode fails without an explicit schema
		self.assertEqual(config["insights_schema"]["required"], ["summary", "highlights", "questions"])

	def test_times(self):
		self.assertEqual(ai.parse_time("2:15"), 135)
		self.assertEqual(ai.parse_time("1:02:15"), 3735)
		self.assertEqual(ai.parse_time(42), 42)
		self.assertIsNone(ai.parse_time("later"))
		self.assertEqual(ai.format_time(3735), "1:02:15")
		self.assertEqual(ai.transcript_lines(SEGMENTS[:1]), ["[0:00] Open the Payment Entry list."])

	def test_split_and_relevant_lines(self):
		many = [
			{"start": i * 5, "end": i * 5 + 4, "text": f"step number {i} explained here"} for i in range(200)
		]
		parts = ai.split_transcript(many, 1000)
		self.assertGreater(len(parts), 1)
		self.assertEqual(sum(len(p) for p in parts), 200)
		lines = ai.relevant_lines(many, "what about step number 150?", 400)
		self.assertTrue(any("step number 150" in line for line in lines))
		self.assertLessEqual(sum(len(line) + 1 for line in lines), 400)

	@patch("frappe_recorder.ai.requests")
	def test_server_insights_sop_and_questions(self, requests):
		frappe.set_user("Administrator")
		set_settings(ollama_url="http://localhost:11434")
		frappe.set_user(OWNER)
		ai.save_transcript(self.token, json.dumps(SEGMENTS))
		name = frappe.db.get_value(api.DOCTYPE, {"token": self.token})

		with patch("frappe_recorder.ai.frappe.enqueue") as enqueue:
			self.assertEqual(ai.generate_on_server(self.token, "insights")["insights_status"], "Processing")
		self.assertEqual(enqueue.call_args.kwargs["kind"], "insights")

		requests.post.return_value = ollama_reply(
			json.dumps(
				{
					"summary": "## Overview\nCreating a payment entry.",
					"highlights": [{"time": "0:25", "title": "New entry"}],
					"questions": ["Can drafts be edited?"],
				}
			)
		)
		ai.run_on_server(name, "insights")
		data = ai.get_ai(self.token)
		self.assertEqual(data["insights_status"], "Ready")
		self.assertEqual(data["highlights"], [{"time": 25.0, "title": "New entry"}])
		self.assertEqual(data["ai_model"], "ollama:qwen2.5:7b")
		self.assertEqual(requests.post.call_args.kwargs["json"]["format"], "json")

		requests.post.return_value = ollama_reply(
			"# Create a payment entry\n## Steps\n1. Open the list (0:00)"
		)
		ai.run_on_server(name, "sop")
		self.assertTrue(ai.get_ai(self.token)["sop"].startswith("# Create a payment entry"))

		requests.post.return_value = ollama_reply("It stays a draft until submitted (1:39).")
		frappe.set_user("Guest")
		self.assertIn("draft", ai.ask(self.token, "What happens after saving?")["answer"])

	@patch("frappe_recorder.ai.requests")
	def test_bad_server_reply_marks_failed(self, requests):
		frappe.set_user("Administrator")
		set_settings(ollama_url="http://localhost:11434")
		frappe.set_user(OWNER)
		ai.save_transcript(self.token, json.dumps(SEGMENTS))
		name = frappe.db.get_value(api.DOCTYPE, {"token": self.token})
		requests.post.return_value = ollama_reply("not json at all")
		ai.run_on_server(name, "insights")
		data = ai.get_ai(self.token)
		self.assertEqual(data["insights_status"], "Failed")
		self.assertTrue(data["ai_error"])

	def test_questions_need_a_server(self):
		ai.save_transcript(self.token, json.dumps(SEGMENTS))
		with self.assertRaises(frappe.ValidationError):
			ai.ask(self.token, "Anything?")
