// Copyright (c) 2026, Sathwik Guduguntla  and contributors
// For license information, please see license.txt

frappe.ui.form.on("Google Drive Settings", {
	refresh(frm) {
		frm.set_intro(
			__(
				"Create an OAuth client (type: Web application) in Google Cloud Console, enable the Google Drive API, and add the redirect URI below. Users then connect their own Drive from the Recorder settings page."
			)
		);
	},
});
