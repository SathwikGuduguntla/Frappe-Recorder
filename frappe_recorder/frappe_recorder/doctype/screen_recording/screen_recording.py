# Copyright (c) 2026, Sathwik Guduguntla  and contributors
# For license information, please see license.txt

import os

import frappe
from frappe.model.document import Document

TOKEN_LENGTH = 12


class ScreenRecording(Document):
	def before_insert(self):
		if not self.token:
			self.token = new_token()

	def on_trash(self):
		# The Google Drive copy (if any) is deliberately left alone.
		remove_if_exists(self.local_video_path())
		remove_if_exists(self.local_thumbnail_path())

	def local_video_path(self) -> str | None:
		if not self.video_file:
			return None
		return os.path.join(video_dir(), os.path.basename(self.video_file))

	def local_thumbnail_path(self) -> str | None:
		if not self.thumbnail or not self.thumbnail.startswith("/files/recorder/"):
			return None
		return os.path.join(thumbnail_dir(), os.path.basename(self.thumbnail))

	def has_local_video(self) -> bool:
		path = self.local_video_path()
		return bool(path and os.path.isfile(path))


def new_token() -> str:
	while True:
		token = frappe.generate_hash(length=TOKEN_LENGTH)
		if not frappe.db.exists("Screen Recording", {"token": token}):
			return token


def video_dir() -> str:
	"""Videos are private files; they are only ever served through `api.stream`."""
	path = frappe.get_site_path("private", "files", "recorder")
	os.makedirs(path, exist_ok=True)
	return path


def thumbnail_dir() -> str:
	path = frappe.get_site_path("public", "files", "recorder")
	os.makedirs(path, exist_ok=True)
	return path


def remove_if_exists(path: str | None):
	if path and os.path.isfile(path):
		os.remove(path)
