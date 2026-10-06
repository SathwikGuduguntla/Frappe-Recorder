# Copyright (c) 2026, Sathwik Guduguntla  and Contributors
# See license.txt

import json

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
	settings.update({"enabled": 1, **values})
	settings.save(ignore_permissions=True)


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
