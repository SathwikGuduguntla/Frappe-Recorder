// Copyright (c) 2026, Sathwik Guduguntla  and contributors
// For license information, please see license.txt

frappe.ui.form.on("Screen Recording", {
	refresh(frm) {
		if (frm.doc.share_id) {
			frm.add_custom_button(__("Open Share Page"), () => {
				window.open(`/r/${frm.doc.share_id}`, "_blank");
			});
		}
	},
});
