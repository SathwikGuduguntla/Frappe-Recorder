# Copyright (c) 2026, Sathwik Guduguntla  and contributors
# For license information, please see license.txt

import os

import frappe
from frappe.utils import add_to_date, now_datetime


def close_abandoned_recordings():
	"""A recording whose browser tab was closed or crashed never gets finalized.
	Keep whatever was uploaded so the footage is not lost; drop the empty ones."""
	stale = frappe.get_all(
		"Screen Recording",
		filters={"status": "Recording", "modified": ["<", add_to_date(now_datetime(), hours=-12)]},
		pluck="name",
	)
	for name in stale:
		doc = frappe.get_doc("Screen Recording", name)
		if doc.has_local_video() and os.path.getsize(doc.local_video_path()) > 0:
			doc.status = "Ready"
			doc.file_size = os.path.getsize(doc.local_video_path())
			doc.save(ignore_permissions=True)
		else:
			frappe.delete_doc("Screen Recording", name, ignore_permissions=True)
