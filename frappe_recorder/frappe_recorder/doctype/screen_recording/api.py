# Copyright (c) 2026, Administrator and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe import _

class ScreenRecording(Document):
	pass

# Whitelisted methods placed outside the class block act as specialized module endpoints

@frappe.whitelist()
def create_recording(title, folder=None):
	"""
	Step 1: Creates an initial recording entry placeholder in the database
	before the frontend browser starts uploading the video binary chunks.
	"""
	doc = frappe.get_doc({
		"doctype": "Screen Recording",
		"title": title,
		"folder": folder,
		"status": "Processing",
		"view_count": 0,
		"is_public": 1,
		"google_drive_status": "Pending"
	})
	doc.insert()
	return doc.name

@frappe.whitelist()
def finalize_recording(recording_name, file_url, duration_seconds=0):
	"""
	Step 2: Attaches the uploaded webm video file URL path to the record,
	marks the status as 'Ready', and stamps its public routing slug.
	"""
	doc = frappe.get_doc("Screen Recording", recording_name)
	
	doc.video_file = file_url
	doc.duration_seconds = int(duration_seconds)
	doc.status = "Ready"
	doc.route = f"r-{doc.name}" # Creates a clean URL identifier like r-REC-00001
	
	doc.save()
	
	return {
		"name": doc.name,
		"route": doc.route,
		"share_url": f"{frappe.utils.get_url()}/{doc.route}",
	}

@frappe.whitelist(allow_guest=True)
def get_shared_recording(route):
	"""
	Step 3: Used by the public Share.vue page viewer. Allow guest profiles 
	to access the record and increments the view counter on every hit.
	"""
	doc = frappe.get_doc("Screen Recording", {"route": route})
	
	if not doc.is_public:
		frappe.throw(_("This recording is private."), frappe.PermissionError)

	# Increment the atomic database value safely
	frappe.db.set_value("Screen Recording", doc.name, "view_count", (doc.view_count or 0) + 1)
	frappe.db.commit()

	return {
		"title": doc.title,
		"video_file": doc.video_file,
		"thumbnail": doc.thumbnail,
		"duration_seconds": doc.duration_seconds,
		"view_count": doc.view_count + 1,
		"creation": doc.creation
	}