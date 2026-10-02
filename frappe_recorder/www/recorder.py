import html
import re

import frappe

no_cache = 1


def get_context(context):
	"""Boot context for the recorder SPA.

	Every /recorder/* path is routed here (see website_route_rules in hooks.py); the
	Vite build writes www/recorder.html and Vue Router takes over in the browser.
	"""
	csrf_token = frappe.sessions.get_csrf_token()
	frappe.db.commit()

	context.no_cache = 1
	context.csrf_token = csrf_token
	context.boot = frappe._dict({"csrf_token": csrf_token, "site_name": frappe.local.site})
	context.update(get_link_preview())
	return context


def get_link_preview():
	"""Open Graph tags so shared links unfurl with the title and thumbnail in chat apps."""
	preview = {
		"og_title": "Frappe Recorder",
		"og_description": "Record your screen and camera, and share it with a link.",
		"og_image": "",
	}
	path = frappe.local.request.path if getattr(frappe.local, "request", None) else ""
	match = re.match(r"^/recorder/v/([A-Za-z0-9]+)", path or "")
	if not match:
		return preview

	recording = frappe.db.get_value(
		"Screen Recording",
		{"share_id": match.group(1), "is_public": 1},
		["title", "description", "thumbnail"],
		as_dict=True,
	)
	if recording:
		preview["og_title"] = recording.title
		preview["og_description"] = recording.description or "Watch this recording"
		if recording.thumbnail:
			preview["og_image"] = frappe.utils.get_url(recording.thumbnail)
	# recorder.html is rendered without autoescaping and these come from users
	return {key: html.escape(value or "", quote=True) for key, value in preview.items()}
