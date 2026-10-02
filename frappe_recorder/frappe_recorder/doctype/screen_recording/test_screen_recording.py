# Copyright (c) 2026, Sathwik Guduguntla  and Contributors
# See license.txt

import io
from types import SimpleNamespace

import frappe
from frappe.tests.utils import FrappeTestCase

from frappe_recorder import api
from frappe_recorder.drive import parse_folder_id


def upload(token: str, index: int, content: bytes):
	frappe.local.request = SimpleNamespace(files={"chunk": SimpleNamespace(stream=io.BytesIO(content))})
	try:
		return api.upload_chunk(token, index)
	finally:
		del frappe.local.request


class TestScreenRecording(FrappeTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_retried_chunk_is_not_appended_twice(self):
		token = api.create_recording(title="Chunks")["token"]
		path = api._get_doc(token).local_video_path()
		self.addCleanup(api.delete_recording, token)

		upload(token, 0, b"aaa")
		self.assertEqual(upload(token, 0, b"aaa"), {"received": 1})

		# A request that died after writing part of chunk 1, before it was committed.
		with open(path, "ab") as f:
			f.write(b"b")
		upload(token, 1, b"bbb")

		with open(path, "rb") as f:
			self.assertEqual(f.read(), b"aaabbb")
		self.assertRaises(frappe.ValidationError, upload, token, 3, b"ddd")

	def test_recording_gets_a_share_link(self):
		created = api.create_recording(title="Demo")
		self.assertTrue(created["share_url"].endswith(f"/r/{created['token']}"))

	def test_private_recording_is_hidden_from_guests(self):
		token = api.create_recording(title="Private")["token"]
		api.update_recording(token, is_public=0)

		frappe.set_user("Guest")
		self.assertRaises(frappe.PermissionError, api.get_recording, token)

	def test_guest_can_open_a_shared_recording(self):
		token = api.create_recording(title="Shared")["token"]

		frappe.set_user("Guest")
		recording = api.get_recording(token)
		self.assertEqual(recording["title"], "Shared")
		self.assertFalse(recording["is_owner"])

	def test_guest_cannot_record(self):
		frappe.set_user("Guest")
		self.assertRaises(frappe.AuthenticationError, api.create_recording, title="Nope")

	def test_drive_folder_links(self):
		folder = "1AbCdEfGhIjKlMnOpQrStUvWxYz012345"
		self.assertEqual(parse_folder_id(f"https://drive.google.com/drive/folders/{folder}"), folder)
		self.assertEqual(
			parse_folder_id(f"https://drive.google.com/drive/u/1/folders/{folder}?usp=sharing"), folder
		)
		self.assertEqual(parse_folder_id(f"https://drive.google.com/open?id={folder}"), folder)
		self.assertEqual(parse_folder_id(folder), folder)
		self.assertIsNone(parse_folder_id("https://example.com/not-drive"))
