# Copyright (c) 2026, Sathwik Guduguntla  and Contributors
# See license.txt

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from frappe_recorder import drive

FOLDER_LINK = "https://drive.google.com/drive/folders/1ugelp0xHEjC-VTsvphwSai4aUfYEQ0HT?usp=sharing"
FOLDER_ID = "1ugelp0xHEjC-VTsvphwSai4aUfYEQ0HT"
CLIENT_ID = "1234-abc.apps.googleusercontent.com"


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


def connect(refresh_token="refresh-token"):
	google = frappe.get_single(drive.GOOGLE_SETTINGS)
	google.update({"enable": 1, "client_id": CLIENT_ID, "client_secret": "secret"})
	google.save()
	frappe.get_single(drive.SETTINGS).update({"refresh_token": refresh_token}).save()


class TestGoogleDriveSettings(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.cache().delete_value(drive.ACCESS_TOKEN_CACHE_KEY)
		settings = frappe.get_single(drive.SETTINGS)
		settings.update(
			{
				"enabled": 0,
				"folder_link": None,
				"folder_id": None,
				"folder_name": None,
				"refresh_token": None,
				"connected_email": None,
			}
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

	def test_google_client_is_saved_in_frappe_google_settings(self):
		with self.assertRaises(frappe.ValidationError):
			drive.save_google_client("not-a-client-id", "secret")
		settings = drive.save_google_client(CLIENT_ID, "secret")
		self.assertTrue(settings["google_client_ready"])
		self.assertTrue(settings["redirect_uri"].endswith(drive.CALLBACK_PATH))
		self.assertEqual(frappe.get_single(drive.GOOGLE_SETTINGS).get_password("client_secret"), "secret")
		# the secret can be left empty later to keep the stored one
		self.assertTrue(drive.save_google_client(CLIENT_ID)["google_client_ready"])

	def test_connect_returns_google_sign_in_with_offline_drive_access(self):
		connect(refresh_token=None)
		url = drive.connect()["url"]
		self.assertTrue(url.startswith(drive.AUTH_URL))
		params = {k: v[0] for k, v in drive.parse_qs(drive.urlparse(url).query).items()}
		self.assertEqual(params["client_id"], CLIENT_ID)
		self.assertEqual(params["scope"], drive.SCOPE)
		self.assertEqual(params["access_type"], "offline")
		from frappe.integrations.google_oauth import consume_google_oauth_state

		state = consume_google_oauth_state(params["state"])
		self.assertEqual(state["callback_method"], "frappe_recorder.drive.authorize_access")
		self.assertEqual(state["redirect"], drive.SETTINGS_PAGE)

	@patch("frappe_recorder.drive.requests")
	@patch("frappe.integrations.google_oauth.GoogleOAuth")
	def test_signing_in_stores_the_account_and_turns_storage_on(self, oauth, requests):
		connect(refresh_token=None)
		frappe.get_single(drive.SETTINGS).update({"folder_link": FOLDER_LINK, "folder_id": FOLDER_ID}).save()
		oauth.return_value.authorize.return_value = {
			"access_token": "token",
			"refresh_token": "refresh-token",
			"expires_in": 3599,
		}
		requests.get.side_effect = [response(json={"user": {"emailAddress": "me@gmail.com"}}), folder_response()]

		drive.authorize_access(code="code")

		settings = drive.get_settings()
		self.assertTrue(settings["connected"])
		self.assertEqual(settings["connected_email"], "me@gmail.com")
		self.assertEqual(settings["folder_name"], "Recordings")
		self.assertTrue(drive.is_active())
		self.assertEqual(requests.get.call_args.kwargs["headers"]["Authorization"], "Bearer token")

	@patch("frappe_recorder.drive.requests")
	def test_saving_the_folder_checks_it(self, requests):
		connect()
		frappe.cache().set_value(drive.ACCESS_TOKEN_CACHE_KEY, "token")
		requests.get.return_value = folder_response()
		settings = drive.save_settings(enabled=1, folder_link=FOLDER_LINK)
		self.assertEqual(settings["folder_id"], FOLDER_ID)
		self.assertEqual(settings["folder_name"], "Recordings")
		self.assertTrue(drive.is_active())

	@patch("frappe_recorder.drive.requests")
	def test_view_only_folder_is_rejected(self, requests):
		connect()
		frappe.cache().set_value(drive.ACCESS_TOKEN_CACHE_KEY, "token")
		requests.get.return_value = folder_response(can_add=False)
		with self.assertRaises(frappe.ValidationError):
			drive.save_settings(enabled=1, folder_link=FOLDER_LINK)

	@patch("frappe.integrations.google_oauth.GoogleOAuth")
	def test_access_token_is_refreshed_once_and_reused(self, oauth):
		connect()
		oauth.return_value.refresh_access_token.return_value = {"access_token": "token", "expires_in": 3599}
		self.assertEqual(drive._access_token(), "token")
		self.assertEqual(drive._access_token(), "token")
		oauth.return_value.refresh_access_token.assert_called_once_with("refresh-token")

	@patch("frappe.integrations.google_oauth.GoogleOAuth")
	def test_revoked_access_asks_to_reconnect(self, oauth):
		connect()
		oauth.return_value.refresh_access_token.side_effect = Exception("invalid_grant")
		with self.assertRaises(frappe.ValidationError):
			drive._access_token()

	@patch("frappe_recorder.drive.requests")
	def test_disconnect(self, requests):
		connect()
		drive.save_settings(enabled=1)
		settings = drive.disconnect()
		self.assertFalse(settings["connected"])
		self.assertFalse(settings["enabled"])
		self.assertIsNone(frappe.get_single(drive.SETTINGS).get_password("refresh_token", raise_exception=False))
