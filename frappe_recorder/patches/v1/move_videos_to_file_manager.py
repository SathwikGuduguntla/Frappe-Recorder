import os

import frappe

from frappe_recorder.frappe_recorder.doctype.screen_recording.screen_recording import (
	video_dir,
	video_file_name,
)


def execute():
	"""Google Drive storage was removed. Videos move from private/files/recorder into
	private/files and become File documents, so they show up in the File Manager."""
	frappe.delete_doc("DocType", "Google Drive Settings", ignore_missing=True, force=True)

	old_dir = frappe.get_site_path("private", "files", "recorder")
	for name in frappe.get_all("Screen Recording", filters={"video_file": ["is", "set"]}, pluck="name"):
		doc = frappe.get_doc("Screen Recording", name)
		old_path = os.path.join(old_dir, os.path.basename(doc.video_file))
		if os.path.isfile(old_path):
			token, extension = os.path.splitext(os.path.basename(doc.video_file))
			doc.video_file = video_file_name(token, extension.lstrip("."))
			os.rename(old_path, os.path.join(video_dir(), doc.video_file))
			doc.db_set("video_file", doc.video_file, update_modified=False)
		if doc.status == "Ready" and not doc.file and doc.has_local_video():
			doc.add_to_file_manager()
			doc.db_set("file", doc.file, update_modified=False)
