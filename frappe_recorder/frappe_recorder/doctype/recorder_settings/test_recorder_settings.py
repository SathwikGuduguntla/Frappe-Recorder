# Copyright (c) 2026, Sathwik Guduguntla  and Contributors
# See license.txt

import io

import frappe
from frappe.tests.utils import FrappeTestCase
from werkzeug.datastructures import FileStorage

from frappe_recorder.api import recording as api

OTHER_KEY = "another-device-key-0123456789"
USER = "recorder-visitor-login@example.com"


def set_settings(**values):
	settings = frappe.get_single("Recorder Settings")
	settings.update(
		{"allow_guest_recording": 1, "guest_max_recording_mb": 500, "guest_recordings_per_hour": 0, **values}
	)
	settings.save(ignore_permissions=True)


class TestRecordingWithoutLogin(FrappeTestCase):
	"""Visitors record without an account; their browser's device key makes them the owner."""

	def setUp(self):
		set_settings()
		self.previous_request = getattr(frappe.local, "request", None)
		frappe.local.request_ip = "203.0.113.7"
		frappe.cache.delete_value("frappe_recorder:guest_recordings:203.0.113.7")
		# a fresh browser for every test
		self.key = f"device-key-{frappe.generate_hash(length=20)}"
		self.use_key(self.key)
		frappe.set_user("Guest")

	def tearDown(self):
		frappe.local.request = self.previous_request
		frappe.set_user("Administrator")
		set_settings()

	def use_key(self, key, files=None):
		headers = {api.DEVICE_KEY_HEADER: key} if key else {}
		frappe.local.request = frappe._dict(headers=headers, files=files or {})

	def upload(self, name, index, data):
		self.use_key(self.key, {"chunk": FileStorage(stream=io.BytesIO(data), filename=f"chunk-{index}")})
		try:
			return api.upload_chunk(name, index)
		finally:
			self.use_key(self.key)

	def record(self):
		created = api.create_recording(title="Visitor demo")
		self.upload(created["name"], 0, b"visitor-video")
		api.finalize_recording(created["name"], duration_seconds=2)
		return created

	def test_visitor_records_and_manages_from_their_browser(self):
		created = self.record()
		self.assertEqual(frappe.db.get_value("Screen Recording", created["name"], "owner"), "Guest")
		self.assertEqual([r.name for r in api.get_recordings()], [created["name"]])

		data = api.get_recording(created["share_id"])
		self.assertTrue(data["is_owner"])
		self.assertFalse(data["can_make_private"])
		self.assertEqual(data["owner_name"], "Anonymous")
		api.update_recording(created["name"], title="Renamed by visitor")

		# another browser can watch, but not manage
		self.use_key(OTHER_KEY)
		self.assertEqual(api.get_recordings(), [])
		self.assertFalse(api.get_recording(created["share_id"])["is_owner"])
		with self.assertRaises(frappe.PermissionError):
			api.update_recording(created["name"], title="Hijacked")
		with self.assertRaises(frappe.PermissionError):
			api.delete_recording(created["name"])

		self.use_key(self.key)
		api.delete_recording(created["name"])
		self.assertFalse(frappe.db.exists("Screen Recording", created["name"]))

	def test_visitor_recordings_stay_public(self):
		created = self.record()
		with self.assertRaises(frappe.ValidationError):
			api.update_recording(created["name"], is_public=0)

	def test_recording_needs_a_device_key(self):
		self.use_key(None)
		with self.assertRaises(frappe.ValidationError):
			api.create_recording(title="No key")

	def test_size_limit_for_visitors(self):
		set_settings(guest_max_recording_mb=1)
		created = api.create_recording(title="Too long")
		self.upload(created["name"], 0, b"x" * 700_000)
		with self.assertRaises(frappe.ValidationError):
			self.upload(created["name"], 1, b"x" * 700_000)

	def test_recordings_per_hour_limit(self):
		set_settings(guest_recordings_per_hour=2)
		api.create_recording(title="One")
		api.create_recording(title="Two")
		with self.assertRaises(frappe.RateLimitExceededError):
			api.create_recording(title="Three")

	def test_recording_without_login_can_be_switched_off(self):
		set_settings(allow_guest_recording=0)
		self.assertFalse(api.get_boot()["allow_guest_recording"])
		with self.assertRaises(frappe.AuthenticationError):
			api.create_recording(title="Not allowed")

	def test_logging_in_moves_device_recordings_to_the_account(self):
		created = self.record()
		if not frappe.db.exists("User", USER):
			frappe.set_user("Administrator")
			frappe.get_doc(
				{"doctype": "User", "email": USER, "first_name": "Visitor", "send_welcome_email": 0}
			).insert(ignore_permissions=True)
		frappe.set_user(USER)
		api.get_boot()
		self.assertEqual(frappe.db.get_value("Screen Recording", created["name"], "owner"), USER)
		self.assertEqual([r.name for r in api.get_recordings()], [created["name"]])
