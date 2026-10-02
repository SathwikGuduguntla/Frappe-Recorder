# Copyright (c) 2026, Sathwik Guduguntla  and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from frappe_recorder import api
from frappe_recorder.drive import parse_folder_id


class TestScreenRecording(FrappeTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

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
