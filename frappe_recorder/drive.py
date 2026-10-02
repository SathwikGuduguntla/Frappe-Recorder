# Copyright (c) 2026, Sathwik Guduguntla  and contributors
# For license information, please see license.txt

"""Google Drive storage for recordings.

A System Manager pastes a Drive folder link and connects a Google account once
(OAuth). After that every finished recording is uploaded to that folder in a
background job, and videos already sitting in the folder can be imported into
the library.

Only `requests` is used, so the app has no extra Python dependencies.
"""

import os
import re
from urllib.parse import urlencode

import frappe
import requests
from frappe import _
from frappe.utils import cint, get_url
from frappe.utils.password import remove_encrypted_password

SETTINGS = "Google Drive Settings"
DOCTYPE = "Screen Recording"

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
FILES_URL = "https://www.googleapis.com/drive/v3/files"
UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files"

# Full Drive scope: the app has to write into (and list) a folder the user
# picked by link, which the narrower drive.file scope does not allow.
SCOPES = "https://www.googleapis.com/auth/drive https://www.googleapis.com/auth/userinfo.email"

ACCESS_TOKEN_CACHE_KEY = "frappe_recorder:drive_access_token"
UPLOAD_CHUNK_SIZE = 16 * 1024 * 1024  # must be a multiple of 256 KiB
TIMEOUT = 60


# ---------------------------------------------------------------- settings


def _settings():
	return frappe.get_single(SETTINGS)


def _client_credentials() -> tuple[str | None, str | None]:
	"""OAuth client from Recorder settings, falling back to Frappe's Google Settings."""
	settings = _settings()
	if settings.client_id:
		return settings.client_id, settings.get_password("client_secret", raise_exception=False)

	google = frappe.get_single("Google Settings")
	if google.get("client_id"):
		return google.client_id, google.get_password("client_secret", raise_exception=False)
	return None, None


def _refresh_token() -> str | None:
	return _settings().get_password("refresh_token", raise_exception=False)


def is_connected() -> bool:
	return bool(_refresh_token())


def is_active() -> bool:
	"""True when finished recordings should be uploaded to Drive."""
	settings = _settings()
	return bool(settings.enabled and settings.folder_id and is_connected())


def redirect_uri() -> str:
	return get_url("/api/method/frappe_recorder.drive.oauth_callback")


def parse_folder_id(link: str | None) -> str | None:
	"""Accepts a Drive folder URL in any of its usual shapes, or a bare folder ID."""
	link = (link or "").strip()
	if not link:
		return None
	for pattern in (r"/folders/([A-Za-z0-9_-]{10,})", r"[?&]id=([A-Za-z0-9_-]{10,})"):
		match = re.search(pattern, link)
		if match:
			return match.group(1)
	if re.fullmatch(r"[A-Za-z0-9_-]{10,}", link):
		return link
	return None


def _only_manager():
	frappe.only_for("System Manager")


# ---------------------------------------------------------------- settings API


@frappe.whitelist()
def get_settings():
	_only_manager()
	settings = _settings()
	client_id, client_secret = _client_credentials()
	return {
		"enabled": cint(settings.enabled),
		"folder_link": settings.folder_link,
		"folder_id": settings.folder_id,
		"folder_name": settings.folder_name,
		"keep_local_copy": cint(settings.keep_local_copy),
		"client_id": settings.client_id,
		"has_client_secret": bool(client_secret),
		"has_client": bool(client_id and client_secret),
		"connected": is_connected(),
		"connected_email": settings.connected_email,
		"redirect_uri": redirect_uri(),
	}


@frappe.whitelist(methods=["POST"])
def save_settings(
	enabled: int = 0,
	folder_link: str | None = None,
	keep_local_copy: int = 1,
	client_id: str | None = None,
	client_secret: str | None = None,
):
	_only_manager()
	settings = _settings()

	folder_link = (folder_link or "").strip()
	folder_id = parse_folder_id(folder_link)
	if folder_link and not folder_id:
		frappe.throw(_("That does not look like a Google Drive folder link."))

	settings.client_id = (client_id or "").strip()
	if client_secret:
		settings.client_secret = client_secret.strip()
	settings.keep_local_copy = cint(keep_local_copy)
	settings.folder_link = folder_link
	if folder_id != settings.folder_id:
		settings.folder_id = folder_id
		settings.folder_name = None
	settings.enabled = cint(enabled)
	settings.save()

	# Check the folder straight away so a wrong link is reported now rather
	# than by a failed upload later.
	if folder_id and is_connected():
		folder = _get_folder(folder_id)
		settings.db_set("folder_name", folder.get("name"))

	return get_settings()


@frappe.whitelist(methods=["POST"])
def get_auth_url():
	_only_manager()
	client_id, client_secret = _client_credentials()
	if not (client_id and client_secret):
		frappe.throw(_("Add a Google OAuth Client ID and Client Secret first."))

	state = frappe.generate_hash(length=32)
	frappe.cache().set_value(f"frappe_recorder:oauth_state:{frappe.session.user}", state, expires_in_sec=600)
	params = {
		"client_id": client_id,
		"redirect_uri": redirect_uri(),
		"response_type": "code",
		"scope": SCOPES,
		"access_type": "offline",
		"prompt": "consent",
		"state": state,
	}
	return {"url": f"{AUTH_URL}?{urlencode(params)}"}


@frappe.whitelist(methods=["GET"])
def oauth_callback(code: str | None = None, state: str | None = None, error: str | None = None):
	"""Google redirects the admin's browser here after consent."""
	_only_manager()

	def finish(result: str):
		frappe.local.response["type"] = "redirect"
		frappe.local.response["location"] = f"/recorder/settings?drive={result}"

	cache_key = f"frappe_recorder:oauth_state:{frappe.session.user}"
	expected = frappe.cache().get_value(cache_key)
	frappe.cache().delete_value(cache_key)
	if error or not code or not state or state != expected:
		return finish("denied")

	client_id, client_secret = _client_credentials()
	response = requests.post(
		TOKEN_URL,
		data={
			"code": code,
			"client_id": client_id,
			"client_secret": client_secret,
			"redirect_uri": redirect_uri(),
			"grant_type": "authorization_code",
		},
		timeout=TIMEOUT,
	)
	tokens = response.json() if response.ok else {}
	if not tokens.get("refresh_token"):
		frappe.log_error(title="Recorder: Google Drive connect failed", message=response.text)
		return finish("failed")

	email = None
	profile = requests.get(
		USERINFO_URL, headers={"Authorization": f"Bearer {tokens['access_token']}"}, timeout=TIMEOUT
	)
	if profile.ok:
		email = profile.json().get("email")

	settings = _settings()
	settings.refresh_token = tokens["refresh_token"]
	settings.connected_email = email
	settings.save()
	frappe.cache().set_value(
		ACCESS_TOKEN_CACHE_KEY,
		tokens["access_token"],
		expires_in_sec=max(cint(tokens.get("expires_in")) - 120, 60),
	)

	result = "connected"
	if settings.folder_id:
		try:
			settings.db_set("folder_name", _get_folder(settings.folder_id).get("name"))
		except Exception:
			# Connected, but this account cannot use the folder; the settings
			# page says so instead of leaving it to a failed upload later.
			frappe.clear_last_message()
			result = "folder"

	frappe.db.commit()
	return finish(result)


@frappe.whitelist(methods=["POST"])
def disconnect():
	_only_manager()
	token = _refresh_token()
	if token:
		try:
			requests.post("https://oauth2.googleapis.com/revoke", params={"token": token}, timeout=TIMEOUT)
		except requests.RequestException:
			pass
	settings = _settings()
	settings.refresh_token = None
	settings.connected_email = None
	settings.save()
	remove_encrypted_password(SETTINGS, SETTINGS, "refresh_token")
	frappe.cache().delete_value(ACCESS_TOKEN_CACHE_KEY)
	return get_settings()


# ---------------------------------------------------------------- Drive calls


def _access_token() -> str:
	token = frappe.cache().get_value(ACCESS_TOKEN_CACHE_KEY)
	if token:
		return token

	refresh_token = _refresh_token()
	client_id, client_secret = _client_credentials()
	if not (refresh_token and client_id and client_secret):
		frappe.throw(_("Google Drive is not connected."))

	response = requests.post(
		TOKEN_URL,
		data={
			"client_id": client_id,
			"client_secret": client_secret,
			"refresh_token": refresh_token,
			"grant_type": "refresh_token",
		},
		timeout=TIMEOUT,
	)
	if not response.ok:
		frappe.throw(
			_("Google rejected the saved Drive connection. Reconnect Google Drive in the recorder settings.")
			+ f" ({_error_text(response)})"
		)
	data = response.json()
	frappe.cache().set_value(
		ACCESS_TOKEN_CACHE_KEY,
		data["access_token"],
		expires_in_sec=max(cint(data.get("expires_in")) - 120, 60),
	)
	return data["access_token"]


def _auth_headers() -> dict:
	return {"Authorization": f"Bearer {_access_token()}"}


def _error_text(response) -> str:
	try:
		error = response.json().get("error")
		if isinstance(error, dict):
			return error.get("message") or response.text[:300]
		return str(response.json().get("error_description") or error or response.text[:300])
	except ValueError:
		return response.text[:300]


def _get_folder(folder_id: str) -> dict:
	response = requests.get(
		f"{FILES_URL}/{folder_id}",
		params={"fields": "id,name,mimeType,capabilities(canAddChildren)", "supportsAllDrives": "true"},
		headers=_auth_headers(),
		timeout=TIMEOUT,
	)
	if response.status_code == 404:
		frappe.throw(
			_("The connected Google account cannot see that Drive folder. Check the link and its sharing.")
		)
	if not response.ok:
		frappe.throw(_("Google Drive error: {0}").format(_error_text(response)))

	folder = response.json()
	if folder.get("mimeType") != "application/vnd.google-apps.folder":
		frappe.throw(_("That Drive link points to a file, not a folder."))
	if not (folder.get("capabilities") or {}).get("canAddChildren"):
		frappe.throw(_("The connected Google account cannot add files to that Drive folder."))
	return folder


def upload_file(path: str, name: str, mime_type: str, folder_id: str) -> dict:
	"""Resumable upload, sent in pieces so large recordings never sit in memory."""
	size = os.path.getsize(path)
	start = requests.post(
		UPLOAD_URL,
		params={"uploadType": "resumable", "supportsAllDrives": "true", "fields": "id,webViewLink"},
		headers={**_auth_headers(), "X-Upload-Content-Type": mime_type, "X-Upload-Content-Length": str(size)},
		json={"name": name, "parents": [folder_id]},
		timeout=TIMEOUT,
	)
	if not start.ok:
		frappe.throw(_("Google Drive error: {0}").format(_error_text(start)))
	session_url = start.headers["Location"]

	with open(path, "rb") as f:
		offset = 0
		while offset < size:
			data = f.read(UPLOAD_CHUNK_SIZE)
			response = requests.put(
				session_url,
				data=data,
				headers={
					"Content-Type": mime_type,
					"Content-Range": f"bytes {offset}-{offset + len(data) - 1}/{size}",
				},
				timeout=600,
			)
			offset += len(data)
			if response.status_code in (200, 201):
				return response.json()
			if response.status_code != 308:
				frappe.throw(_("Google Drive error: {0}").format(_error_text(response)))

	frappe.throw(_("Google Drive did not confirm the upload."))


def open_file_stream(file_id: str, range_header: str | None = None):
	"""Streaming GET of a Drive file's bytes, used to play videos without a local copy."""
	headers = _auth_headers()
	if range_header:
		headers["Range"] = range_header
	response = requests.get(
		f"{FILES_URL}/{file_id}",
		params={"alt": "media", "supportsAllDrives": "true"},
		headers=headers,
		stream=True,
		timeout=TIMEOUT,
	)
	if not response.ok:
		frappe.throw(_("Could not load this video from Google Drive: {0}").format(_error_text(response)))
	return response


# ---------------------------------------------------------------- sync jobs


def enqueue_upload(name: str):
	# One job per recording: a second upload of the same video would leave a
	# duplicate file in Drive.
	frappe.enqueue(
		"frappe_recorder.drive.upload_recording",
		queue="long",
		timeout=3600,
		enqueue_after_commit=True,
		job_id=f"frappe_recorder:drive_upload:{name}",
		deduplicate=True,
		recording=name,
	)


def upload_recording(recording: str):
	"""Background job: copy one finished recording into the configured Drive folder."""
	name = recording
	doc = frappe.get_doc(DOCTYPE, name)
	if doc.drive_file_id or doc.status != "Ready" or not doc.has_local_video():
		return

	settings = _settings()
	if not is_active():
		return

	try:
		extension = os.path.splitext(doc.video_file)[1]
		file = upload_file(
			doc.local_video_path(),
			f"{doc.title}{extension}",
			doc.mime_type or "video/webm",
			settings.folder_id,
		)
	except Exception as e:
		frappe.db.rollback()
		frappe.db.set_value(
			DOCTYPE,
			name,
			{"google_drive_status": "Failed", "drive_error": str(e)[:500]},
			update_modified=False,
		)
		frappe.log_error(title="Recorder: Google Drive upload failed")
		frappe.db.commit()
		return

	values = {
		"google_drive_status": "Synced",
		"drive_file_id": file["id"],
		"drive_link": file.get("webViewLink") or f"https://drive.google.com/file/d/{file['id']}/view",
		"drive_error": None,
	}
	frappe.db.set_value(DOCTYPE, name, values, update_modified=False)
	frappe.db.commit()

	# The local file goes only once the Drive copy is on record, so a failure
	# here cannot leave the recording with nothing to play.
	if not settings.keep_local_copy:
		os.remove(doc.local_video_path())
		frappe.db.set_value(DOCTYPE, name, "video_file", None, update_modified=False)
		frappe.db.commit()


def retry_pending_uploads():
	"""Hourly: pick up uploads that failed or were never attempted (e.g. Drive was down).
	Each one is queued as its own job; uploading here would hit this job's timeout."""
	if not is_active():
		return
	names = frappe.get_all(
		DOCTYPE,
		filters={
			"status": "Ready",
			"google_drive_status": ["in", ["Pending", "Failed"]],
			"video_file": ["is", "set"],
		},
		order_by="creation asc",
		limit_page_length=25,
		pluck="name",
	)
	for name in names:
		enqueue_upload(name)


@frappe.whitelist(methods=["POST"])
def retry_upload(token: str):
	"""Lets the owner retry a failed Drive upload from the video page."""
	from frappe_recorder import api

	doc = api._get_owned_doc(token)
	if not is_active():
		frappe.throw(_("Google Drive storage is not set up."))
	if doc.status == "Ready" and not doc.drive_file_id and doc.has_local_video():
		doc.db_set({"google_drive_status": "Pending", "drive_error": None}, update_modified=False)
		enqueue_upload(doc.name)
	return api._serialize(doc, is_owner=True)


@frappe.whitelist(methods=["POST"])
def import_from_drive():
	"""Adds videos that are in the Drive folder but not yet in the library.
	They are streamed from Drive when played."""
	_only_manager()
	settings = _settings()
	if not (settings.folder_id and is_connected()):
		frappe.throw(_("Connect Google Drive and set a folder link first."))

	known = set(frappe.get_all(DOCTYPE, filters={"drive_file_id": ["is", "set"]}, pluck="drive_file_id"))
	imported = 0
	page_token = None
	while True:
		params = {
			"q": f"'{settings.folder_id}' in parents and mimeType contains 'video/' and trashed = false",
			"fields": "nextPageToken,files(id,name,mimeType,size,webViewLink,videoMediaMetadata(durationMillis))",
			"pageSize": 200,
			"supportsAllDrives": "true",
			"includeItemsFromAllDrives": "true",
		}
		if page_token:
			params["pageToken"] = page_token
		response = requests.get(FILES_URL, params=params, headers=_auth_headers(), timeout=TIMEOUT)
		if not response.ok:
			frappe.throw(_("Google Drive error: {0}").format(_error_text(response)))
		data = response.json()

		for file in data.get("files", []):
			if file["id"] in known:
				continue
			duration_ms = cint((file.get("videoMediaMetadata") or {}).get("durationMillis"))
			frappe.get_doc(
				{
					"doctype": DOCTYPE,
					"title": os.path.splitext(file["name"])[0][:140] or file["name"],
					"status": "Ready",
					"is_public": 1,
					"source": "Google Drive",
					"mime_type": file.get("mimeType"),
					"file_size": cint(file.get("size")),
					"duration_seconds": round(duration_ms / 1000),
					"google_drive_status": "Synced",
					"drive_file_id": file["id"],
					"drive_link": file.get("webViewLink"),
				}
			).insert(ignore_permissions=True)
			imported += 1

		page_token = data.get("nextPageToken")
		if not page_token:
			break

	return {"imported": imported}
