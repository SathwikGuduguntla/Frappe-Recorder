# Copyright (c) 2026, Sathwik Guduguntla  and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class GoogleDriveSettings(Document):
	@property
	def redirect_uri(self):
		from frappe_recorder.api.drive import get_redirect_uri

		return get_redirect_uri()
