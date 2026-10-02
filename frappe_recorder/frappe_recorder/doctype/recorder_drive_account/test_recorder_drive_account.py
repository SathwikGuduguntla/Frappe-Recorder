# Copyright (c) 2026, Sathwik Guduguntla  and Contributors
# See license.txt

import os
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from frappe_recorder.api import drive
from frappe_recorder.api import recording as api

TEST_USER = "recorder-drive@example.com"
FOLDER_ID = "1FolderIdForRecordingsXYZ"


def response(status_code=200, json=None, headers=None):
	res = MagicMock()
	res.status_code = status_code
	res.ok = 200 <= status_code < 300
	res.json.return_value = json or {}
	res.headers = headers or {}
	res.text = str(json)
	return res


class TestRecorderDriveAccount(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not frappe.db.exists("User", TEST_USER):
			frappe.get_doc(
				{"doctype": "User", "email": TEST_USER, "first_name": "Drive", "send_welcome_email": 0}
			).insert(ignore_permissions=True)
		settings = frappe.get_doc("Google Drive Settings")
		settings.update({"enabled": 1, "client_id": "client-id", "client_secret": "client-secret"})
		settings.save(ignore_permissions=True)

	def setUp(self):
		frappe.set_user(TEST_USER)
		frappe.cache.delete_value(f"frappe_recorder:access_token:{TEST_USER}")
		frappe.db.delete("Recorder Drive Account", {"user": TEST_USER})
		frappe.get_doc(
			{
				"doctype": "Recorder Drive Account",
				"user": TEST_USER,
				"google_email": "me@gmail.com",
				"refresh_token": "refresh-token",
				"folder_link": f"https://drive.google.com/drive/folders/{FOLDER_ID}",
				"folder_id": FOLDER_ID,
				"folder_name": "Recordings",
				"auto_upload": 1,
				"keep_local_copy": 0,
				"share_on_drive": 1,
			}
		).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.set_user("Administrator")

	def make_recording(self, data=None):
		data = data or os.urandom(1000)
		created = api.create_recording(title="Drive demo / test")
		doc = frappe.get_doc("Screen Recording", created["name"])
		path = frappe.get_site_path("public", "files", f"recording-{doc.share_id}.webm")
		with open(path, "wb") as f:
			f.write(data)
		with patch.object(frappe, "enqueue") as enqueue:
			api.finalize_recording(doc.name, duration_seconds=5)
		enqueue.assert_called_once()
		return frappe.get_doc("Screen Recording", doc.name)

	def test_status_and_authorize_url(self):
		status = drive.get_status()
		self.assertTrue(status["configured"])
		self.assertTrue(status["connected"])
		self.assertEqual(status["folder_name"], "Recordings")

		url = drive.get_authorize_url()
		self.assertIn("client_id=client-id", url)
		self.assertIn("access_type=offline", url)
		self.assertIn(drive.get_redirect_uri().replace(":", "%3A").replace("/", "%2F"), url)

	def test_finished_recording_is_queued_for_drive(self):
		doc = self.make_recording()
		self.assertEqual(doc.google_drive_status, "Queued")

	@patch("frappe_recorder.api.drive.requests")
	def test_resumable_upload_shares_and_removes_local_copy(self, requests):
		doc = self.make_recording()
		path = frappe.get_site_path("public", doc.video_file.lstrip("/"))

		requests.post.return_value = response(json={"access_token": "token", "expires_in": 3600})
		requests.request.side_effect = [
			response(headers={"Location": "https://upload.example/session"}),  # start session
			response(json={"id": "perm"}),  # share with anyone
		]
		# Drive acknowledges only part of the first piece, then completes
		requests.put.side_effect = [
			response(308, headers={"Range": "bytes=0-499"}),
			response(200, json={"id": "drive-file-id"}),
		]

		drive.upload_recording(doc.name)

		doc.reload()
		self.assertEqual(doc.google_drive_status, "Synced")
		self.assertEqual(doc.drive_file_id, "drive-file-id")
		self.assertIn("drive-file-id", doc.drive_web_link)

		metadata = requests.request.call_args_list[0].kwargs["json"]
		self.assertEqual(metadata["parents"], [FOLDER_ID])
		self.assertEqual(metadata["name"], "Drive demo   test.webm")
		second_put = requests.put.call_args_list[1].kwargs
		self.assertEqual(second_put["headers"]["Content-Range"], "bytes 500-999/1000")

		# keep_local_copy is off: the share page now plays from Drive
		self.assertFalse(doc.video_file)
		self.assertFalse(os.path.exists(path))
		data = api.get_recording(doc.share_id)
		self.assertEqual(data["drive_file_id"], "drive-file-id")

	@patch("frappe_recorder.api.drive.requests")
	def test_failed_upload_is_reported(self, requests):
		doc = self.make_recording()
		requests.post.return_value = response(json={"access_token": "token", "expires_in": 3600})
		requests.request.return_value = response(403, json={"error": {"message": "Insufficient permissions"}})

		drive.upload_recording(doc.name)

		doc.reload()
		self.assertEqual(doc.google_drive_status, "Failed")
		self.assertIn("Insufficient permissions", doc.drive_error)
		self.assertTrue(doc.video_file)

	@patch("frappe_recorder.api.drive.requests")
	def test_save_folder_validates_link(self, requests):
		requests.post.return_value = response(json={"access_token": "token", "expires_in": 3600})
		requests.request.return_value = response(
			json={
				"id": "1AnotherFolderId123",
				"name": "Team videos",
				"mimeType": drive.FOLDER_MIME_TYPE,
				"capabilities": {"canAddChildren": True},
			}
		)
		status = drive.save_folder("https://drive.google.com/drive/u/0/folders/1AnotherFolderId123")
		self.assertEqual(status["folder_id"], "1AnotherFolderId123")
		self.assertEqual(status["folder_name"], "Team videos")

		with self.assertRaises(frappe.ValidationError):
			drive.save_folder("https://example.com/whatever")

	def test_site_account_is_used_for_visitor_recordings(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Recorder Drive Account", {"user": "Guest"})
		frappe.get_doc(
			{
				"doctype": "Recorder Drive Account",
				"user": "Guest",
				"refresh_token": "site-refresh-token",
				"folder_id": FOLDER_ID,
				"folder_name": "Site recordings",
				"auto_upload": 1,
			}
		).insert(ignore_permissions=True)
		self.assertEqual(drive.get_status(site=1)["folder_name"], "Site recordings")
		self.assertTrue(drive.should_auto_upload("Guest"))

		frappe.set_user("Guest")
		status = drive.get_status()
		self.assertTrue(status["visitor"])
		self.assertTrue(status["connected"])
		self.assertNotIn("google_email", status)

		# only System Managers manage the site's Drive
		frappe.set_user(TEST_USER)
		with self.assertRaises(frappe.PermissionError):
			drive.get_status(site=1)
