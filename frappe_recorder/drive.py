# Copyright (c) 2026, Sathwik Guduguntla  and contributors
# For license information, please see license.txt

"""Google Drive storage for recordings.

A System Manager connects the Google account that should own the videos and pastes
the link of a Drive folder that account can add to. Every finished recording is then
uploaded to that folder in a background job, and videos already sitting in the folder
can be imported into the library.

Google only accepts uploads made as a Google account, so the site needs that account's
access tokens. There are two ways to get them; both end in `_access_token()`:

- Google sign-in ("Connect Google Drive"). Uses Frappe's own Google integration: the
  OAuth client lives in the core `Google Settings` single, the consent screen comes back
  through `frappe.integrations.google_oauth.callback`, and the refresh token is stored here.
- The uploader, for sites without an OAuth client: a small Google Apps Script the admin
  deploys once as a web app. It hands this server a short-lived access token of the admin's
  account. Its source, with this site's secret written in, is shown on the settings page.

Drive calls use only `requests`, so the app has no extra Python dependencies.
"""

import os
import re
from urllib.parse import parse_qs, quote, urlencode, urlparse

import frappe
import requests
from frappe import _
from frappe.utils import cint, get_request_site_address, get_url

SETTINGS = "Google Drive Settings"
GOOGLE_SETTINGS = "Google Settings"
DOCTYPE = "Screen Recording"

FILES_URL = "https://www.googleapis.com/drive/v3/files"
UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files"
ABOUT_URL = "https://www.googleapis.com/drive/v3/about"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
CALLBACK_PATH = "/api/method/frappe.integrations.google_oauth.callback"
SCOPE = "https://www.googleapis.com/auth/drive"
SETTINGS_PAGE = "/recorder/settings"
UPLOADER_URL_PATTERN = re.compile(
	r"^https://script\.google\.com/(a/macros/[^/]+|macros)/s/[A-Za-z0-9_-]+/exec$"
)

ACCESS_TOKEN_CACHE_KEY = "frappe_recorder:drive_access_token"
# Apps Script tokens last about an hour but the script can't say how much is left
# of the one it returns, so they are only reused for a few minutes.
UPLOADER_TOKEN_TTL = 10 * 60
UPLOAD_CHUNK_SIZE = 16 * 1024 * 1024  # must be a multiple of 256 KiB
TIMEOUT = 60

UPLOADER_SCRIPT = """/**
 * Frappe Recorder: Google Drive uploader.
 *
 * Lends the recorder at {site} a short-lived access token of the Google
 * account that deploys this script, so it can upload recordings into the
 * Drive folder set in the recorder. Keep this code private: the secret
 * below is what lets only that site use it.
 */
var SECRET = '{secret}';

// Opening the web app URL in a browser shows this, so you can check that the
// deployment is reachable without signing in.
function doGet() {{
  return reply({{ ok: true, uploader: 'Frappe Recorder', message: 'The uploader is running.' }});
}}

function doPost(e) {{
  var body = {{}};
  try {{
    body = JSON.parse(e.postData.contents);
  }} catch (err) {{}}
  if (body.secret !== SECRET) {{
    return reply({{ ok: false, error: 'Wrong secret' }});
  }}
  return reply({{
    ok: true,
    access_token: ScriptApp.getOAuthToken(),
    email: Session.getEffectiveUser().getEmail(),
  }});
}}

// Never called. It is here so Apps Script asks for Google Drive access when
// the script is deployed.
function requestDriveAccess() {{
  DriveApp.getRootFolder();
}}

function reply(data) {{
  return ContentService.createTextOutput(JSON.stringify(data)).setMimeType(
    ContentService.MimeType.JSON
  );
}}
"""


# ---------------------------------------------------------------- settings


def _settings():
	return frappe.get_single(SETTINGS)


def _refresh_token() -> str | None:
	return _settings().get_password("refresh_token", raise_exception=False)


def _uploader_secret() -> str:
	"""The secret written into the uploader script; created the first time it is needed."""
	settings = _settings()
	secret = settings.get_password("uploader_secret", raise_exception=False)
	if not secret:
		secret = frappe.generate_hash(length=40)
		settings.uploader_secret = secret
		settings.save(ignore_permissions=True)
	return secret


def google_client_ready() -> bool:
	"""True when Frappe's Google Settings hold an OAuth client to sign in with."""
	google = frappe.get_single(GOOGLE_SETTINGS)
	return bool(
		google.enable and google.client_id and google.get_password("client_secret", raise_exception=False)
	)


def connection_method() -> str | None:
	""""google" (signed in), "uploader" (Apps Script) or None."""
	if _refresh_token():
		return "google"
	if _settings().uploader_url:
		return "uploader"
	return None


def is_connected() -> bool:
	return bool(connection_method())


def is_active() -> bool:
	"""True when finished recordings should be uploaded to Drive."""
	settings = _settings()
	return bool(settings.enabled and settings.folder_id and is_connected())


def redirect_uri() -> str:
	"""What the admin adds to the OAuth client's "Authorized redirect URIs". Built the
	way Frappe's `GoogleOAuth.authorize` builds it, so the two always match."""
	site = get_request_site_address(True) if getattr(frappe.local, "request", None) else get_url()
	return site + CALLBACK_PATH


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


def parse_resource_key(link: str | None) -> str | None:
	"""Folders shared before 2021 carry a `resourcekey` in their link, which Drive
	asks for when the folder is opened by someone it was only shared with by link."""
	values = parse_qs(urlparse((link or "").strip()).query).get("resourcekey")
	return values[0] if values else None


def _only_manager():
	frappe.only_for("System Manager")


# ---------------------------------------------------------------- settings API


@frappe.whitelist()
def get_settings():
	_only_manager()
	settings = _settings()
	google = frappe.get_single(GOOGLE_SETTINGS)
	return {
		"enabled": cint(settings.enabled),
		"folder_link": settings.folder_link,
		"folder_id": settings.folder_id,
		"folder_name": settings.folder_name,
		"keep_local_copy": cint(settings.keep_local_copy),
		"google_client_ready": google_client_ready(),
		"client_id": google.client_id,
		"redirect_uri": redirect_uri(),
		"uploader_url": settings.uploader_url,
		"uploader_script": UPLOADER_SCRIPT.format(site=frappe.local.site, secret=_uploader_secret()),
		"method": connection_method(),
		"connected": is_connected(),
		"connected_email": settings.connected_email,
	}


@frappe.whitelist(methods=["POST"])
def save_settings(enabled: int = 0, folder_link: str | None = None, keep_local_copy: int = 1):
	_only_manager()
	settings = _settings()

	folder_link = (folder_link or "").strip()
	folder_id = parse_folder_id(folder_link)
	if folder_link and not folder_id:
		frappe.throw(_("That does not look like a Google Drive folder link."))

	settings.keep_local_copy = cint(keep_local_copy)
	settings.folder_link = folder_link
	settings.folder_resource_key = parse_resource_key(folder_link)
	if folder_id != settings.folder_id:
		settings.folder_id = folder_id
		settings.folder_name = None
	settings.enabled = cint(enabled)
	settings.save()

	# Check the folder straight away, so a mistake is reported now rather than by a
	# failed upload later.
	if folder_id and is_connected():
		settings.db_set("folder_name", _get_folder(folder_id).get("name"))

	return get_settings()


@frappe.whitelist(methods=["POST"])
def save_google_client(client_id: str, client_secret: str | None = None):
	"""Stores the OAuth client in Frappe's Google Settings, so the admin can do the
	whole setup from the recorder's settings page."""
	_only_manager()
	client_id = (client_id or "").strip()
	if not re.fullmatch(r"[\w.-]+\.apps\.googleusercontent\.com", client_id):
		frappe.throw(_("The Client ID ends with .apps.googleusercontent.com."))
	google = frappe.get_single(GOOGLE_SETTINGS)
	google.enable = 1
	google.client_id = client_id
	client_secret = (client_secret or "").strip()
	if client_secret:
		google.client_secret = client_secret
	elif not google.get_password("client_secret", raise_exception=False):
		frappe.throw(_("Add the Client secret too."))
	google.save()
	return get_settings()


@frappe.whitelist(methods=["POST"])
def save_uploader(uploader_url: str):
	"""Connects through the Apps Script uploader instead of Google sign-in."""
	_only_manager()
	uploader_url = (uploader_url or "").strip()
	if not UPLOADER_URL_PATTERN.match(uploader_url):
		frappe.throw(
			_(
				"That does not look like an Apps Script web app URL. It starts with "
				"https://script.google.com/macros/s/ and ends with /exec."
			)
		)
	settings = _settings()
	settings.update({"uploader_url": uploader_url, "refresh_token": None, "connected_email": None})
	settings.save()
	frappe.cache().delete_value(ACCESS_TOKEN_CACHE_KEY)

	# Check the uploader and the folder straight away, so a mistake is reported now
	# rather than by a failed upload later.
	_access_token()
	if settings.folder_id:
		settings.db_set("folder_name", _get_folder(settings.folder_id).get("name"))
		# Connecting with a folder already chosen is the whole setup: switch storage on.
		settings.db_set("enabled", 1)
	return get_settings()


@frappe.whitelist(methods=["POST"])
def connect():
	"""The Google sign-in URL. Google sends the admin back through Frappe's callback,
	which calls `authorize_access` and then returns to the settings page."""
	_only_manager()
	if not google_client_ready():
		frappe.throw(_("Add the Google OAuth client first."))
	from frappe.integrations.google_oauth import create_google_oauth_state

	state = create_google_oauth_state(
		{
			"callback_method": "frappe_recorder.drive.authorize_access",
			"redirect": SETTINGS_PAGE,
			"success_query_param": "drive=connected",
			"failure_query_param": "drive=denied",
		}
	)
	params = {
		"client_id": frappe.get_single(GOOGLE_SETTINGS).client_id,
		"redirect_uri": redirect_uri(),
		"response_type": "code",
		"scope": SCOPE,
		"access_type": "offline",
		# Always ask, so Google always hands back a refresh token.
		"prompt": "consent",
		"include_granted_scopes": "true",
		"state": state,
	}
	return {"url": f"{AUTH_URL}?{urlencode(params, quote_via=quote)}"}


def authorize_access(code: str | None = None, **kwargs):
	"""Called by `frappe.integrations.google_oauth.callback` with the code from Google."""
	_only_manager()
	from frappe.integrations.google_oauth import GoogleOAuth

	tokens = GoogleOAuth("drive").authorize(code)
	if not tokens.get("refresh_token"):
		frappe.throw(_("Google did not grant offline access to Drive. Try connecting again."))

	settings = _settings()
	settings.update({"refresh_token": tokens["refresh_token"], "uploader_url": None, "connected_email": None})
	settings.save()
	_cache_access_token(tokens)

	try:
		about = requests.get(
			ABOUT_URL, params={"fields": "user(emailAddress)"}, headers=_auth_headers(), timeout=TIMEOUT
		)
		settings.db_set("connected_email", (about.json().get("user") or {}).get("emailAddress"))
		if settings.folder_id:
			settings.db_set("folder_name", _get_folder(settings.folder_id).get("name"))
			# Signing in with a folder already chosen is the whole setup: switch storage on.
			settings.db_set("enabled", 1)
	except Exception:
		# The settings page shows the folder problem when the admin saves it again.
		frappe.log_error(title="Recorder: checking the Drive folder after sign-in failed")


@frappe.whitelist(methods=["POST"])
def disconnect():
	_only_manager()
	token = _refresh_token()
	if token:
		try:
			requests.post(REVOKE_URL, params={"token": token}, timeout=TIMEOUT)
		except requests.RequestException:
			pass
	settings = _settings()
	settings.update({"refresh_token": None, "uploader_url": None, "connected_email": None, "enabled": 0})
	settings.save()
	frappe.cache().delete_value(ACCESS_TOKEN_CACHE_KEY)
	return get_settings()


# ---------------------------------------------------------------- Drive calls


def _cache_access_token(tokens: dict):
	# Reused until a minute before Google says it expires.
	ttl = max(cint(tokens.get("expires_in")) - 60, 60)
	frappe.cache().set_value(ACCESS_TOKEN_CACHE_KEY, tokens["access_token"], expires_in_sec=ttl)


def _access_token() -> str:
	token = frappe.cache().get_value(ACCESS_TOKEN_CACHE_KEY, expires=True)
	if token:
		return token

	refresh_token = _refresh_token()
	if not refresh_token:
		if _settings().uploader_url:
			return _uploader_access_token()
		frappe.throw(_("Google Drive is not connected. Connect it in the recorder settings."))

	from frappe.integrations.google_oauth import GoogleOAuth

	try:
		tokens = GoogleOAuth("drive").refresh_access_token(refresh_token)
	except Exception:
		frappe.throw(
			_(
				"Google Drive access has expired or was removed. Connect Google Drive again in the "
				"recorder settings."
			)
		)
	_cache_access_token(tokens)
	return tokens["access_token"]


def _uploader_access_token() -> str:
	settings = _settings()
	try:
		response = requests.post(settings.uploader_url, json={"secret": _uploader_secret()}, timeout=TIMEOUT)
	except requests.RequestException as e:
		frappe.throw(_("Could not reach the Drive uploader: {0}").format(e))
	try:
		data = response.json()
		if not isinstance(data, dict):
			raise ValueError
	except ValueError:
		frappe.throw(_uploader_problem(response))
	if not data.get("ok") or not data.get("access_token"):
		frappe.throw(
			_(
				"The Drive uploader refused the request ({0}). Copy the script from the settings page again."
			).format(data.get("error") or response.status_code)
		)

	if data.get("email") and data["email"] != settings.connected_email:
		settings.db_set("connected_email", data["email"])
	frappe.cache().set_value(ACCESS_TOKEN_CACHE_KEY, data["access_token"], expires_in_sec=UPLOADER_TOKEN_TTL)
	return data["access_token"]


def _uploader_problem(response) -> str:
	"""Explains a reply from the uploader URL that isn't the script's JSON. Google answers
	with an HTML page instead when the deployment is set up wrong; say which mistake it is."""
	text = response.text or ""
	final_url = str(getattr(response, "url", "") or "")
	title = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
	title = re.sub(r"\s+", " ", title.group(1)).strip() if title else ""

	if "accounts.google.com" in final_url or "ServiceLogin" in text or title.startswith("Sign in"):
		return _(
			"Google asked for a sign-in instead of running the uploader, so the web app is not open to "
			"“Anyone”. In Apps Script, open Deploy → Manage deployments → Edit (pencil), set “Who has "
			"access” to “Anyone” (not “Anyone with Google account”), choose Version: New version and "
			"Deploy. If “Anyone” is missing, your Google Workspace admin has turned it off; deploy the "
			"script from a personal Gmail account instead."
		)
	if "Script function not found" in text:
		return _(
			"The deployed script has no doPost function. Paste the whole script from this page into the "
			"Apps Script editor, save it, then Deploy → Manage deployments → Edit → Version: New version "
			"→ Deploy. Deployments keep the code they were made with, so saving alone is not enough."
		)
	if "Authorization is required" in text or "authorization" in title.lower():
		return _(
			"The uploader has not been given access to Google Drive. In the Apps Script editor pick the "
			"function requestDriveAccess, press Run and allow access, then try again."
		)
	if response.status_code == 404 or "unable to open the file" in text:
		return _(
			"Google could not find that web app. Copy the Web app URL again from Deploy → Manage "
			"deployments; it ends with /exec."
		)
	return _(
		"The Drive uploader answered with a web page instead of the script's reply (HTTP {0}{1}). Open "
		"the uploader URL in a private browser window: it should show “The uploader is running.” If it "
		"does not, redeploy the script with “Execute as: Me”, “Who has access: Anyone” and Version: New "
		"version."
	).format(response.status_code, f", “{title}”" if title else "")


def _auth_headers() -> dict:
	headers = {"Authorization": f"Bearer {_access_token()}"}
	settings = _settings()
	if settings.folder_id and settings.folder_resource_key:
		headers["X-Goog-Drive-Resource-Keys"] = f"{settings.folder_id}/{settings.folder_resource_key}"
	return headers


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
			_(
				"Drive could not open that folder. Check that the connected Google account owns it or "
				"that it is shared with that account as Editor."
			)
		)
	if not response.ok:
		frappe.throw(_("Google Drive error: {0}").format(_error_text(response)))

	folder = response.json()
	if folder.get("mimeType") != "application/vnd.google-apps.folder":
		frappe.throw(_("That Drive link points to a file, not a folder."))
	if not (folder.get("capabilities") or {}).get("canAddChildren"):
		frappe.throw(
			_(
				"The connected Google account can only view that folder. Share it with that account as "
				"Editor."
			)
		)
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
		frappe.throw(_("Connect Google Drive and add a folder link first."))

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
