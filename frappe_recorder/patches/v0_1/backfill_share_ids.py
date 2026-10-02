import frappe

from frappe_recorder.frappe_recorder.doctype.screen_recording.screen_recording import generate_share_id


def execute():
	"""Recordings made before share links existed: give them a share ID and map the
	old status values onto the new ones, so they show up and play in the new app."""
	recordings = frappe.get_all(
		"Screen Recording",
		filters={"share_id": ["is", "not set"]},
		fields=["name", "status", "video_file", "google_drive_status"],
	)
	for recording in recordings:
		values = {"share_id": generate_share_id()}
		if recording.status not in ("Ready", "Failed"):
			# the old flow left "Processing" behind when the upload never finished
			values["status"] = "Ready" if recording.video_file else "Failed"
		if recording.google_drive_status not in ("Not Synced", "Queued", "Uploading", "Synced", "Failed"):
			values["google_drive_status"] = "Not Synced"
		frappe.db.set_value("Screen Recording", recording.name, values, update_modified=False)
