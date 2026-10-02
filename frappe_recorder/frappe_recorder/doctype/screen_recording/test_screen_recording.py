# Copyright (c) 2026, Sathwik Guduguntla  and Contributors
# See license.txt

import io
import os
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from werkzeug.datastructures import FileStorage

from frappe_recorder.api import recording as api
from frappe_recorder.api.drive import parse_folder_id

TEST_USER = "recorder-owner@example.com"
OTHER_USER = "recorder-other@example.com"
# 1x1 transparent PNG
THUMBNAIL = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="


def make_user(email):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		).insert(ignore_permissions=True)


class TestScreenRecording(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_user(TEST_USER)
		make_user(OTHER_USER)

	def setUp(self):
		frappe.set_user(TEST_USER)

	def tearDown(self):
		frappe.set_user("Administrator")

	def upload(self, recording, index, data):
		request = frappe._dict(
			files={"chunk": FileStorage(stream=io.BytesIO(data), filename=f"chunk-{index}")}
		)
		with patch.object(frappe, "request", request, create=True):
			return api.upload_chunk(recording, index)

	def record(self, chunks=(b"first-", b"second")):
		created = api.create_recording(title="Demo", recording_mode="Screen + Camera", mime_type="video/webm")
		for i, data in enumerate(chunks):
			self.upload(created["name"], i, data)
		return created

	def test_share_link_exists_before_recording_finishes(self):
		created = api.create_recording(title="Demo")
		self.assertTrue(created["share_id"])
		self.assertTrue(created["share_url"].endswith(f"/r/{created['share_id']}"))
		data = api.get_recording(created["share_id"])
		self.assertEqual(data["status"], "Recording")
		self.assertIsNone(data["video_url"])

	def test_chunks_are_appended_in_order_and_finalized(self):
		created = self.record()
		# a retried chunk is acknowledged but not written twice
		self.upload(created["name"], 1, b"second")
		with self.assertRaises(frappe.ValidationError):
			self.upload(created["name"], 5, b"gap")

		result = api.finalize_recording(created["name"], duration_seconds=12.4, thumbnail=THUMBNAIL)
		self.assertEqual(result["status"], "Ready")

		doc = frappe.get_doc("Screen Recording", created["name"])
		self.assertEqual(doc.duration_seconds, 12.4)
		self.assertTrue(doc.thumbnail)
		path = frappe.get_site_path("public", doc.video_file.lstrip("/"))
		with open(path, "rb") as f:
			self.assertEqual(f.read(), b"first-second")
		self.assertTrue(
			frappe.db.exists("File", {"attached_to_name": doc.name, "attached_to_field": "video_file"})
		)

	def test_large_recordings_ignore_upload_size_limit(self):
		created = api.create_recording(title="Long one")
		with patch("frappe.core.api.file.get_max_file_size", return_value=4):
			self.upload(created["name"], 0, b"more than four bytes")
			api.finalize_recording(created["name"], duration_seconds=1)
		self.assertEqual(frappe.db.get_value("Screen Recording", created["name"], "status"), "Ready")

	def test_guests_can_watch_and_comment_on_public_recordings(self):
		created = self.record()
		api.finalize_recording(created["name"], duration_seconds=3)

		frappe.set_user("Guest")
		data = api.get_recording(created["share_id"])
		self.assertFalse(data["is_owner"])
		self.assertTrue(data["video_url"])
		self.assertNotIn("drive_error", data)

		api.register_view(created["share_id"])
		api.register_view(created["share_id"])  # same viewer within an hour counts once
		comment = api.add_comment(
			created["share_id"], "Nice demo!", timestamp_seconds=1.5, commenter_name="Sam"
		)
		self.assertEqual(comment.commenter_name, "Sam")
		api.add_comment(created["share_id"], "🎉", comment_type="Reaction")
		with self.assertRaises(frappe.ValidationError):
			api.add_comment(created["share_id"], "not an emoji", comment_type="Reaction")

		frappe.set_user(TEST_USER)
		data = api.get_recording(created["share_id"])
		self.assertEqual(data["view_count"], 1)
		self.assertEqual(len(data["comments"]), 2)

	def test_private_recordings_are_hidden_from_others(self):
		created = self.record()
		api.finalize_recording(created["name"])
		api.update_recording(created["name"], is_public=0)

		frappe.set_user(OTHER_USER)
		with self.assertRaises(frappe.PermissionError):
			api.get_recording(created["share_id"])
		with self.assertRaises(frappe.PermissionError):
			api.update_recording(created["name"], title="Hijacked")
		self.assertNotIn(created["name"], [r.name for r in api.get_recordings()])

	def test_private_recording_media_is_not_publicly_served(self):
		created = self.record()
		api.finalize_recording(created["name"], thumbnail=THUMBNAIL)
		doc = frappe.get_doc("Screen Recording", created["name"])
		public_video = api.get_video_path(doc)

		# each step is its own request in real use; committing keeps the test's final
		# rollback from replaying both file moves
		frappe.db.commit()
		api.update_recording(created["name"], is_public=0)
		frappe.db.commit()
		doc.reload()
		self.assertTrue(doc.video_file.startswith("/private/files/"))
		self.assertTrue(doc.thumbnail.startswith("/private/files/"))
		self.assertFalse(os.path.exists(public_video))
		with open(api.get_video_path(doc), "rb") as f:
			self.assertEqual(f.read(), b"first-second")
		# the owner still gets a playable URL
		self.assertEqual(api.get_recording(created["share_id"])["video_url"], doc.video_file)

		api.update_recording(created["name"], is_public=1)
		frappe.db.commit()
		doc.reload()
		self.assertTrue(doc.video_file.startswith("/files/"))
		self.assertTrue(os.path.exists(api.get_video_path(doc)))

	def test_recordings_from_before_share_links_get_one(self):
		from frappe_recorder.patches.v0_1.backfill_share_ids import execute

		old = api.create_recording(title="Old")["name"]
		frappe.db.set_value(
			"Screen Recording",
			old,
			{"share_id": None, "status": "Processing", "google_drive_status": "Pending"},
		)
		execute()
		share_id, status, drive_status = frappe.db.get_value(
			"Screen Recording", old, ["share_id", "status", "google_drive_status"]
		)
		self.assertTrue(share_id)
		self.assertEqual(status, "Failed")
		self.assertEqual(drive_status, "Not Synced")

	def test_cancelled_recording_is_discarded_with_its_file(self):
		created = self.record()
		doc = frappe.get_doc("Screen Recording", created["name"])
		path = frappe.get_site_path("public", "files", f"recording-{doc.share_id}.webm")
		self.assertTrue(os.path.exists(path))
		api.discard_recording(created["name"])
		self.assertFalse(frappe.db.exists("Screen Recording", created["name"]))
		self.assertFalse(os.path.exists(path))

	def test_folders(self):
		folder = api.create_folder("Demos")
		created = self.record()
		api.finalize_recording(created["name"])
		api.update_recording(created["name"], folder=folder["name"])
		self.assertEqual([r.name for r in api.get_recordings(folder=folder["name"])], [created["name"]])
		api.delete_folder(folder["name"])
		self.assertIsNone(frappe.db.get_value("Screen Recording", created["name"], "folder"))


class TestDriveFolderLinks(FrappeTestCase):
	def test_parse_folder_id(self):
		folder_id = "1AbCdEfGhIjKlMnOpQrStUvWxYz012345"
		for link in (
			f"https://drive.google.com/drive/folders/{folder_id}",
			f"https://drive.google.com/drive/u/1/folders/{folder_id}?usp=sharing",
			f"https://drive.google.com/open?id={folder_id}",
			folder_id,
		):
			self.assertEqual(parse_folder_id(link), folder_id)
		self.assertIsNone(parse_folder_id("https://example.com/not-a-folder"))
