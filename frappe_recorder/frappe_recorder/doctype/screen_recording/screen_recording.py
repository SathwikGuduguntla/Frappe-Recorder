# Copyright (c) 2026, Sathwik Guduguntla  and contributors
# For license information, please see license.txt

import os
import secrets

import frappe
from frappe.model.document import Document


class ScreenRecording(Document):
	def before_insert(self):
		if not self.share_id:
			self.share_id = generate_share_id()

	def on_trash(self):
		frappe.db.delete("Recording Comment", {"recording": self.name})
		# a recording that never finished has a partial file but no File doc
		path = get_partial_video_path(self)
		if path and os.path.exists(path) and not self.video_file:
			os.remove(path)

	@property
	def share_url(self):
		return get_share_url(self.share_id)


def generate_share_id():
	while True:
		share_id = secrets.token_urlsafe(9).replace("-", "a").replace("_", "b")
		if not frappe.db.exists("Screen Recording", {"share_id": share_id}):
			return share_id


def get_share_url(share_id):
	return frappe.utils.get_url(f"/r/{share_id}")


def get_video_file_name(doc):
	extension = "mp4" if (doc.mime_type or "").startswith("video/mp4") else "webm"
	return f"recording-{doc.share_id}.{extension}"


def get_partial_video_path(doc):
	if not doc.share_id:
		return None
	return frappe.get_site_path("public", "files", get_video_file_name(doc))
