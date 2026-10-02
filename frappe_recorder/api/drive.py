# Copyright (c) 2026, Sathwik Guduguntla  and contributors
# For license information, please see license.txt

"""Google Drive storage for recordings.

A System Manager stores an OAuth client in *Google Drive Settings*. Each user then
connects their own Google account from the recorder's settings page and pastes the
link of the Drive folder their recordings should go to. Finished recordings are
uploaded to that folder in a background job, and the share page can play them back
from Drive.
"""

import os
import re
import secrets
from urllib.parse import urlencode

import frappe
import requests
from frappe import _
from frappe.utils import cint, now_datetime

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
FILES_URL = "https://www.googleapis.com/drive/v3/files"
UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files"

# `drive` (not `drive.file`) is needed to upload into a folder the user picked by link:
# `drive.file` only sees files and folders this app created itself.
SCOPES = ("openid", "email", "https://www.googleapis.com/auth/drive")
FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
UPLOAD_CHUNK_SIZE = 32 * 256 * 1024  # 8 MiB; Drive wants multiples of 256 KiB
REQUEST_TIMEOUT = 60


def get_redirect_uri():
	return frappe.utils.get_url("/api/method/frappe_recorder.api.drive.oauth_callback")


def get_settings():
	settings = frappe.get_cached_doc("Google Drive Settings")
	if not settings.enabled or not settings.client_id:
		return None
	return settings


def get_account(user=None):
	user = user or frappe.session.user
	if frappe.db.exists("Recorder Drive Account", user):
		return frappe.get_doc("Recorder Drive Account", user)
	return None


@frappe.whitelist()
def get_status():
	settings = get_settings()
	account = get_account() if settings else None
	status = {
		"configured": bool(settings),
		"connected": bool(account and account.get_password("refresh_token", raise_exception=False)),
		"redirect_uri": get_redirect_uri(),
		"can_configure": "System Manager" in frappe.get_roles(),
	}
	if account:
		status.update(
			{
				"google_email": account.google_email,
				"folder_link": account.folder_link,
				"folder_id": account.folder_id,
				"folder_name": account.folder_name,
				"auto_upload": cint(account.auto_upload),
				"keep_local_copy": cint(account.keep_local_copy),
				"share_on_drive": cint(account.share_on_drive),
			}
		)
	return status


@frappe.whitelist()
def get_authorize_url():
	ensure_user()
	settings = get_settings()
	if not settings:
		frappe.throw(
			_(
				"Google Drive is not set up on this site yet. Ask an administrator to fill in Google Drive Settings."
			)
		)

	state = secrets.token_urlsafe(24)
	frappe.cache.set_value(f"frappe_recorder:oauth_state:{state}", frappe.session.user, expires_in_sec=600)
	params = {
		"client_id": settings.client_id,
		"redirect_uri": get_redirect_uri(),
		"response_type": "code",
		"scope": " ".join(SCOPES),
		"access_type": "offline",
		"prompt": "consent",
		"include_granted_scopes": "true",
		"state": state,
	}
	return f"{AUTH_URL}?{urlencode(params)}"


@frappe.whitelist(methods=["GET"])
def oauth_callback(state=None, code=None, error=None, **kwargs):
	user = frappe.cache.get_value(f"frappe_recorder:oauth_state:{state}", expires=True) if state else None
	if state:
		frappe.cache.delete_value(f"frappe_recorder:oauth_state:{state}")

	if error or not code or not user or user != frappe.session.user:
		return redirect_to_settings("error")

	settings = get_settings()
	if not settings:
		return redirect_to_settings("error")
	response = requests.post(
		TOKEN_URL,
		data={
			"code": code,
			"client_id": settings.client_id,
			"client_secret": settings.get_password("client_secret"),
			"redirect_uri": get_redirect_uri(),
			"grant_type": "authorization_code",
		},
		timeout=REQUEST_TIMEOUT,
	)
	if not response.ok:
		frappe.log_error(f"Google token exchange failed: {response.text}", "Recorder Drive Connect")
		return redirect_to_settings("error")
	tokens = response.json()

	email = None
	userinfo = requests.get(
		USERINFO_URL,
		headers={"Authorization": f"Bearer {tokens['access_token']}"},
		timeout=REQUEST_TIMEOUT,
	)
	if userinfo.ok:
		email = userinfo.json().get("email")

	account = get_account(user) or frappe.get_doc({"doctype": "Recorder Drive Account", "user": user})
	account.google_email = email
	account.connected_on = now_datetime()
	if tokens.get("refresh_token"):
		account.refresh_token = tokens["refresh_token"]
	account.save(ignore_permissions=True)
	cache_access_token(user, tokens)
	frappe.db.commit()
	return redirect_to_settings("connected")


def redirect_to_settings(result):
	frappe.local.response["type"] = "redirect"
	frappe.local.response["location"] = f"/recorder/settings?drive={result}"


@frappe.whitelist(methods=["POST"])
def save_folder(folder_link):
	account = get_connected_account()
	folder_link = (folder_link or "").strip()
	if not folder_link:
		account.folder_link = account.folder_id = account.folder_name = None
		account.save(ignore_permissions=True)
		return get_status()

	folder_id = parse_folder_id(folder_link)
	if not folder_id:
		frappe.throw(_("That doesn't look like a Google Drive folder link."))

	response = drive_request(
		account.user,
		"GET",
		f"{FILES_URL}/{folder_id}",
		params={"fields": "id,name,mimeType,capabilities(canAddChildren)", "supportsAllDrives": "true"},
	)
	if response.status_code == 404:
		frappe.throw(_("Folder not found. Make sure the connected Google account can open it."))
	raise_for_drive_error(response)
	folder = response.json()
	if folder.get("mimeType") != FOLDER_MIME_TYPE:
		frappe.throw(_("The link points to a file, not a folder."))
	if not folder.get("capabilities", {}).get("canAddChildren"):
		frappe.throw(_("The connected Google account can't add files to this folder."))

	account.folder_link = folder_link
	account.folder_id = folder["id"]
	account.folder_name = folder.get("name")
	account.save(ignore_permissions=True)
	return get_status()


@frappe.whitelist(methods=["POST"])
def update_preferences(auto_upload=None, keep_local_copy=None, share_on_drive=None):
	account = get_connected_account()
	for field, value in (
		("auto_upload", auto_upload),
		("keep_local_copy", keep_local_copy),
		("share_on_drive", share_on_drive),
	):
		if value is not None:
			account.set(field, cint(value))
	account.save(ignore_permissions=True)
	return get_status()


@frappe.whitelist(methods=["POST"])
def disconnect():
	account = get_account()
	if not account:
		return get_status()
	token = account.get_password("refresh_token", raise_exception=False)
	if token:
		try:
			requests.post(REVOKE_URL, data={"token": token}, timeout=REQUEST_TIMEOUT)
		except requests.RequestException:
			pass
	frappe.cache.delete_value(f"frappe_recorder:access_token:{account.user}")
	account.delete(ignore_permissions=True)
	return get_status()


@frappe.whitelist(methods=["POST"])
def sync_recording(recording):
	"""Upload (or re-upload after a failure) one recording to the owner's Drive folder."""
	from frappe_recorder.api.recording import get_owned_doc

	doc = get_owned_doc("Screen Recording", recording)
	account = get_connected_account(doc.owner)
	if not account.folder_id:
		frappe.throw(_("Choose a Google Drive folder in Settings first."))
	if not doc.video_file:
		frappe.throw(_("This recording has no video file on this site to upload."))
	if doc.google_drive_status in ("Queued", "Uploading", "Synced"):
		return doc.google_drive_status

	doc.db_set({"google_drive_status": "Queued", "drive_error": None})
	frappe.enqueue(
		"frappe_recorder.api.drive.upload_recording",
		queue="long",
		timeout=60 * 60,
		recording=doc.name,
		enqueue_after_commit=True,
	)
	return "Queued"


def should_auto_upload(user):
	if not get_settings():
		return False
	account = get_account(user)
	return bool(account and account.auto_upload and account.folder_id and account.refresh_token)


def upload_recording(recording):
	doc = frappe.get_doc("Screen Recording", recording)
	account = get_account(doc.owner)
	if not account or not account.folder_id or not doc.video_file:
		doc.db_set({"google_drive_status": "Failed", "drive_error": "Google Drive is not connected."})
		return

	path = frappe.get_site_path("public", doc.video_file.lstrip("/"))
	doc.db_set({"google_drive_status": "Uploading", "drive_error": None})
	frappe.db.commit()
	try:
		file_id = upload_file(account, path, doc)
		web_link = f"https://drive.google.com/file/d/{file_id}/view"
		if account.share_on_drive:
			share_with_anyone(account.user, file_id)
		doc.db_set({"google_drive_status": "Synced", "drive_file_id": file_id, "drive_web_link": web_link})
		frappe.db.commit()
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(f"Drive upload failed for {doc.name}", reference_doctype="Screen Recording")
		doc.db_set({"google_drive_status": "Failed", "drive_error": str(e)[:1000]})
		frappe.db.commit()
		return

	if not account.keep_local_copy:
		remove_local_video(doc)


def upload_file(account, path, doc):
	"""Resumable upload, so recordings of any length go through in fixed-size pieces."""
	from frappe_recorder.frappe_recorder.doctype.screen_recording.screen_recording import get_share_url

	size = os.path.getsize(path)
	mime_type = (doc.mime_type or "video/webm").split(";")[0]
	extension = os.path.splitext(path)[1]
	metadata = {
		"name": f"{safe_file_name(doc.title)}{extension}",
		"parents": [account.folder_id],
		"mimeType": mime_type,
		"description": _("Recorded with Frappe Recorder: {0}").format(get_share_url(doc.share_id)),
	}

	response = drive_request(
		account.user,
		"POST",
		UPLOAD_URL,
		params={"uploadType": "resumable", "supportsAllDrives": "true", "fields": "id"},
		json=metadata,
		headers={"X-Upload-Content-Type": mime_type, "X-Upload-Content-Length": str(size)},
	)
	raise_for_drive_error(response)
	session_url = response.headers["Location"]

	offset = 0
	with open(path, "rb") as f:
		while True:
			f.seek(offset)
			chunk = f.read(UPLOAD_CHUNK_SIZE)
			end = offset + len(chunk) - 1
			response = requests.put(
				session_url,
				data=chunk,
				headers={
					"Content-Length": str(len(chunk)),
					"Content-Range": f"bytes {offset}-{end}/{size}" if chunk else f"bytes */{size}",
				},
				timeout=REQUEST_TIMEOUT * 5,
			)
			if response.status_code in (200, 201):
				return response.json()["id"]
			if response.status_code != 308:
				raise_for_drive_error(response)
				raise Exception(_("Unexpected response from Google Drive: {0}").format(response.status_code))
			# 308: Drive tells us how much it has; continue from there
			uploaded = response.headers.get("Range")
			offset = int(uploaded.split("-")[1]) + 1 if uploaded else 0


def share_with_anyone(user, file_id):
	response = drive_request(
		user,
		"POST",
		f"{FILES_URL}/{file_id}/permissions",
		params={"supportsAllDrives": "true"},
		json={"role": "reader", "type": "anyone"},
	)
	if not response.ok:
		# Workspace policies may forbid public links; the upload itself still succeeded.
		frappe.log_error(f"Could not share Drive file {file_id}: {response.text}", "Recorder Drive Share")


def delete_drive_file(user, file_id):
	try:
		response = drive_request(
			user, "DELETE", f"{FILES_URL}/{file_id}", params={"supportsAllDrives": "true"}
		)
		if not response.ok and response.status_code != 404:
			frappe.log_error(
				f"Could not delete Drive file {file_id}: {response.text}", "Recorder Drive Delete"
			)
	except Exception:
		frappe.log_error(f"Could not delete Drive file {file_id}", "Recorder Drive Delete")


def remove_local_video(doc):
	for file_name in frappe.get_all(
		"File",
		filters={
			"attached_to_doctype": "Screen Recording",
			"attached_to_name": doc.name,
			"attached_to_field": "video_file",
		},
		pluck="name",
	):
		frappe.delete_doc("File", file_name, ignore_permissions=True)
	doc.db_set("video_file", None)
	frappe.db.commit()


def drive_request(user, method, url, **kwargs):
	headers = kwargs.pop("headers", {})
	for attempt in range(2):
		headers["Authorization"] = f"Bearer {get_access_token(user, force_refresh=attempt > 0)}"
		response = requests.request(method, url, headers=headers, timeout=REQUEST_TIMEOUT, **kwargs)
		if response.status_code != 401:
			break
	return response


def get_access_token(user, force_refresh=False):
	cache_key = f"frappe_recorder:access_token:{user}"
	if not force_refresh:
		token = frappe.cache.get_value(cache_key, expires=True)
		if token:
			return token

	settings = get_settings()
	account = get_account(user)
	refresh_token = account and account.get_password("refresh_token", raise_exception=False)
	if not settings or not refresh_token:
		frappe.throw(_("Google Drive is not connected."))

	response = requests.post(
		TOKEN_URL,
		data={
			"client_id": settings.client_id,
			"client_secret": settings.get_password("client_secret"),
			"refresh_token": refresh_token,
			"grant_type": "refresh_token",
		},
		timeout=REQUEST_TIMEOUT,
	)
	if not response.ok:
		frappe.throw(_("Google Drive access has expired or was revoked. Please reconnect Google Drive."))
	tokens = response.json()
	cache_access_token(user, tokens)
	return tokens["access_token"]


def cache_access_token(user, tokens):
	expires_in = max(cint(tokens.get("expires_in")) - 120, 60)
	frappe.cache.set_value(
		f"frappe_recorder:access_token:{user}", tokens["access_token"], expires_in_sec=expires_in
	)


def raise_for_drive_error(response):
	if response.ok or response.status_code == 308:
		return
	try:
		message = response.json()["error"]["message"]
	except Exception:
		message = response.text[:500]
	frappe.throw(_("Google Drive error: {0}").format(message))


def parse_folder_id(link):
	"""Accepts folder URLs (`/drive/folders/<id>`, `/drive/u/0/folders/<id>`,
	`open?id=<id>`) or a bare folder id."""
	for pattern in (r"/folders/([A-Za-z0-9_-]{10,})", r"[?&]id=([A-Za-z0-9_-]{10,})"):
		match = re.search(pattern, link)
		if match:
			return match.group(1)
	if re.fullmatch(r"[A-Za-z0-9_-]{10,}", link):
		return link
	return None


def safe_file_name(title):
	name = re.sub(r'[\\/:*?"<>|]+', " ", title or "").strip()
	return name[:120] or "Recording"


def ensure_user():
	if frappe.session.user == "Guest":
		frappe.throw(_("Please log in to continue."), frappe.AuthenticationError)


def get_connected_account(user=None):
	ensure_user()
	account = get_account(user) if get_settings() else None
	if not account or not account.get_password("refresh_token", raise_exception=False):
		frappe.throw(_("Connect your Google Drive first."))
	return account
