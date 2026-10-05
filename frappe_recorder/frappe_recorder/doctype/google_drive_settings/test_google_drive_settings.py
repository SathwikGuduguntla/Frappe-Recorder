# Copyright (c) 2026, Sathwik Guduguntla  and Contributors
# See license.txt

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from frappe_recorder import drive

FOLDER_LINK = "https://drive.google.com/drive/folders/1ugelp0xHEjC-VTsvphwSai4aUfYEQ0HT?usp=sharing"
FOLDER_ID = "1ugelp0xHEjC-VTsvphwSai4aUfYEQ0HT"
UPLOADER_URL = "https://script.google.com/macros/s/AKfycbTestDeployment_123/exec"


def response(status_code=200, json=None, headers=None):
	res = MagicMock()
	res.status_code = status_code
	res.ok = 200 <= status_code < 300
	res.json.return_value = json if json is not None else {}
	res.headers = headers or {}
	res.text = str(json)
	return res


def folder_response(can_add=True):
	return response(
		json={
			"id": FOLDER_ID,
			"name": "Recordings",
			"mimeType": "application/vnd.google-apps.folder",
			"capabilities": {"canAddChildren": can_add},
		}
	)


class TestGoogleDriveSettings(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.cache().delete_value(drive.ACCESS_TOKEN_CACHE_KEY)
		settings = frappe.get_single(drive.SETTINGS)
		settings.update(
			{"enabled": 0, "folder_link": None, "folder_id": None, "folder_name": None, "uploader_url": None}
		)
		settings.save()

	def tearDown(self):
		frappe.cache().delete_value(drive.ACCESS_TOKEN_CACHE_KEY)

	def test_folder_links(self):
		self.assertEqual(drive.parse_folder_id(FOLDER_LINK), FOLDER_ID)
		self.assertIsNone(drive.parse_resource_key(FOLDER_LINK))
		self.assertEqual(
			drive.parse_resource_key(f"https://drive.google.com/drive/folders/{FOLDER_ID}?resourcekey=0-abc"),
			"0-abc",
		)

	def test_uploader_script_carries_this_sites_secret(self):
		settings = drive.get_settings()
		secret = frappe.get_single(drive.SETTINGS).get_password("uploader_secret")
		self.assertEqual(len(secret), 40)
		self.assertIn(f"var SECRET = '{secret}';", settings["uploader_script"])
		self.assertFalse(settings["connected"])
		# the secret stays the same between visits, or a deployed script would stop working
		self.assertEqual(drive.get_settings()["uploader_script"], settings["uploader_script"])

	@patch("frappe_recorder.drive.requests")
	def test_saving_the_uploader_and_folder_checks_both(self, requests):
		requests.post.return_value = response(
			json={"ok": True, "access_token": "token", "email": "me@gmail.com"}
		)
		requests.get.return_value = folder_response()

		settings = drive.save_settings(enabled=1, folder_link=FOLDER_LINK, uploader_url=UPLOADER_URL)

		self.assertTrue(settings["connected"])
		self.assertEqual(settings["folder_id"], FOLDER_ID)
		self.assertEqual(settings["folder_name"], "Recordings")
		self.assertEqual(settings["connected_email"], "me@gmail.com")
		self.assertTrue(drive.is_active())
		secret = frappe.get_single(drive.SETTINGS).get_password("uploader_secret")
		self.assertEqual(requests.post.call_args.kwargs["json"], {"secret": secret})
		self.assertEqual(requests.get.call_args.kwargs["headers"]["Authorization"], "Bearer token")

	@patch("frappe_recorder.drive.requests")
	def test_view_only_folder_is_rejected(self, requests):
		requests.post.return_value = response(json={"ok": True, "access_token": "token"})
		requests.get.return_value = folder_response(can_add=False)
		with self.assertRaises(frappe.ValidationError):
			drive.save_settings(enabled=1, folder_link=FOLDER_LINK, uploader_url=UPLOADER_URL)

	@patch("frappe_recorder.drive.requests")
	def test_wrong_secret_is_reported(self, requests):
		requests.post.return_value = response(json={"ok": False, "error": "Wrong secret"})
		with self.assertRaises(frappe.ValidationError):
			drive.save_settings(enabled=1, folder_link=FOLDER_LINK, uploader_url=UPLOADER_URL)

	def test_only_apps_script_urls_are_accepted(self):
		with self.assertRaises(frappe.ValidationError):
			drive.save_settings(uploader_url="https://example.com/steal-tokens")

	@patch("frappe_recorder.drive.requests")
	def test_access_token_is_reused(self, requests):
		frappe.get_single(drive.SETTINGS).db_set("uploader_url", UPLOADER_URL)
		requests.post.return_value = response(json={"ok": True, "access_token": "token"})
		self.assertEqual(drive._access_token(), "token")
		self.assertEqual(drive._access_token(), "token")
		self.assertEqual(requests.post.call_count, 1)

	@patch("frappe_recorder.drive.requests")
	def test_uploader_web_pages_are_explained(self, requests):
		def html_page(text, status_code=200, url=UPLOADER_URL):
			res = response(status_code=status_code)
			res.json.side_effect = ValueError("Expecting value")
			res.text = text
			res.url = url
			return res

		cases = [
			(
				html_page(
					"<title>Sign in - Google Accounts</title>", url="https://accounts.google.com/v3/signin"
				),
				"Who has access",
			),
			(html_page("<div>Script function not found: doPost</div>"), "New version"),
			(html_page("<title>Error</title>Authorization is required to perform that action."), "Run"),
			(
				html_page("Sorry, unable to open the file at this time.", status_code=404),
				"Manage deployments",
			),
			(html_page("<title>Something else</title>", status_code=500), "HTTP 500"),
		]
		for page, expected in cases:
			frappe.cache().delete_value(drive.ACCESS_TOKEN_CACHE_KEY)
			requests.post.return_value = page
			with self.assertRaises(frappe.ValidationError) as error:
				drive.save_settings(enabled=1, uploader_url=UPLOADER_URL)
			self.assertIn(expected, str(error.exception))

	def test_uploader_script_can_be_checked_in_a_browser(self):
		self.assertIn("function doGet()", drive.get_settings()["uploader_script"])
