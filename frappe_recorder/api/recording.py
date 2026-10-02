# Copyright (c) 2026, Sathwik Guduguntla  and contributors
# For license information, please see license.txt

"""Endpoints used by the recorder SPA (/recorder).

Lifecycle of a recording:
1. `create_recording` makes the document and hands out its share link straight away,
   so the link can be copied while the recording is still running.
2. `upload_chunk` is called every few seconds with the next MediaRecorder slice; the
   slices are appended in order to the video file.
3. `finalize_recording` attaches the finished file, stores the thumbnail and queues the
   post-processing job (duration fix-up + Google Drive upload).
"""

import base64
import hashlib
import os
from datetime import timezone
from zoneinfo import ZoneInfo

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint, flt, get_datetime, get_system_timezone

from frappe_recorder.frappe_recorder.doctype.screen_recording.screen_recording import (
	get_partial_video_path,
	get_share_url,
	get_video_file_name,
)

RECORDING_MODES = ("Screen + Camera", "Screen", "Camera")
ALLOWED_MIME_PREFIXES = ("video/webm", "video/mp4")
REACTIONS = ("👍", "❤️", "😂", "🎉", "😮", "🔥", "👏", "🤔")
MAX_CHUNK_SIZE = 50 * 1024 * 1024


@frappe.whitelist(allow_guest=True)
def get_boot():
	user = frappe.session.user
	boot = {
		"user": user,
		"is_guest": user == "Guest",
		"site_name": frappe.local.site,
		"drive_enabled": bool(frappe.db.get_single_value("Google Drive Settings", "enabled")),
	}
	if user != "Guest":
		info = frappe.db.get_value("User", user, ["full_name", "user_image"], as_dict=True) or {}
		boot.update(
			{
				"full_name": info.get("full_name") or user,
				"user_image": info.get("user_image"),
				"is_system_manager": "System Manager" in frappe.get_roles(),
			}
		)
	return boot


@frappe.whitelist(methods=["POST"])
def create_recording(title=None, recording_mode="Screen + Camera", mime_type="video/webm", folder=None):
	ensure_logged_in()
	if recording_mode not in RECORDING_MODES:
		frappe.throw(_("Invalid recording mode"))
	if not (mime_type or "").startswith(ALLOWED_MIME_PREFIXES):
		frappe.throw(_("Unsupported video format: {0}").format(mime_type))
	if folder:
		get_owned_doc("Recording Folder", folder)

	doc = frappe.get_doc(
		{
			"doctype": "Screen Recording",
			"title": (title or "").strip() or _("Untitled recording"),
			"recording_mode": recording_mode,
			"mime_type": mime_type,
			"folder": folder,
			"status": "Recording",
		}
	)
	doc.insert()
	return {"name": doc.name, "share_id": doc.share_id, "share_url": get_share_url(doc.share_id)}


@frappe.whitelist(methods=["POST"])
def upload_chunk(recording, chunk_index):
	"""Append one MediaRecorder slice to the recording's video file.

	The client uploads slices strictly in order, so a re-sent slice (a retry after a
	dropped response) is acknowledged without being written twice.
	"""
	doc = get_owned_doc("Screen Recording", recording)
	if doc.status != "Recording":
		frappe.throw(_("This recording is no longer accepting video data."))

	chunk = frappe.request.files.get("chunk")
	if not chunk:
		frappe.throw(_("No video data received."))
	data = chunk.stream.read(MAX_CHUNK_SIZE + 1)
	if len(data) > MAX_CHUNK_SIZE:
		frappe.throw(_("Video chunk is too large."))

	chunk_index = cint(chunk_index)
	expected = cint(doc.uploaded_chunks)
	if chunk_index < expected:
		return {"uploaded_chunks": expected}
	if chunk_index > expected:
		frappe.throw(_("Video chunk {0} arrived before chunk {1}.").format(chunk_index, expected))

	path = get_partial_video_path(doc)
	os.makedirs(os.path.dirname(path), exist_ok=True)
	with open(path, "wb" if chunk_index == 0 else "ab") as f:
		f.write(data)

	frappe.db.set_value(
		"Screen Recording",
		doc.name,
		{"uploaded_chunks": expected + 1, "file_size": os.path.getsize(path)},
		update_modified=False,
	)
	return {"uploaded_chunks": expected + 1}


@frappe.whitelist(methods=["POST"])
def finalize_recording(recording, duration_seconds=0, thumbnail=None):
	doc = get_owned_doc("Screen Recording", recording)
	if doc.status != "Recording":
		return get_recording_summary(doc)

	path = get_partial_video_path(doc)
	if not path or not os.path.exists(path) or not os.path.getsize(path):
		doc.status = "Failed"
		doc.save()
		frappe.throw(_("No video data was uploaded for this recording."))

	attach_video_file(doc, path)
	doc.video_file = f"/files/{get_video_file_name(doc)}"
	doc.file_size = os.path.getsize(path)
	doc.duration_seconds = max(flt(duration_seconds), 0)
	doc.status = "Ready"
	if thumbnail:
		doc.thumbnail = save_thumbnail(doc, thumbnail)

	from frappe_recorder.api.drive import should_auto_upload

	if should_auto_upload(doc.owner):
		doc.google_drive_status = "Queued"
	doc.save()
	# made private while it was still being recorded
	sync_media_privacy(doc)

	frappe.enqueue(
		"frappe_recorder.api.recording.post_process_recording",
		queue="long",
		timeout=60 * 60,
		recording=doc.name,
		enqueue_after_commit=True,
	)
	return get_recording_summary(doc)


def attach_video_file(doc, path):
	attach_file(doc, path, "video_file")


def attach_file(doc, path, fieldname):
	"""Register a file already written to public/files as a File attached to the recording.

	The File must not re-read it: for a video that would load the whole recording into
	memory and reject anything over System Settings' upload limit (10 MB by default),
	which every recording longer than a minute or so exceeds. It also keeps each
	recording's files its own: Frappe would otherwise point identical uploads at one
	shared file, which breaks when one recording's files are moved to private storage.
	"""
	file_name = os.path.basename(path)
	file_doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": file_name,
			"file_url": f"/files/{file_name}",
			"file_size": os.path.getsize(path),
			# Frappe only removes a file from disk when deleting a File that has a hash
			"content_hash": get_file_hash(path),
			"attached_to_doctype": "Screen Recording",
			"attached_to_name": doc.name,
			"attached_to_field": fieldname,
			"is_private": 0,
			"folder": "Home/Attachments",
		}
	)
	file_doc.flags.copy_from_existing_file = True
	try:
		file_doc.insert(ignore_permissions=True)
	except frappe.exceptions.MaxFileSizeReachedError:
		# Frappe versions without `copy_from_existing_file`: write the row directly
		frappe.clear_last_message()
		file_doc.set_new_name()
		file_doc.db_insert()
	return file_doc.file_url


def get_file_hash(path):
	"""md5 like frappe's `get_content_hash`, without loading the whole video into memory."""
	digest = hashlib.md5()
	with open(path, "rb") as f:
		for block in iter(lambda: f.read(1024 * 1024), b""):
			digest.update(block)
	return digest.hexdigest()


@frappe.whitelist(methods=["POST"])
def discard_recording(recording):
	"""Throw away a recording that was cancelled before it was finished."""
	doc = get_owned_doc("Screen Recording", recording)
	if doc.status == "Recording":
		doc.delete()


def post_process_recording(recording):
	doc = frappe.get_doc("Screen Recording", recording)
	fix_video_metadata(doc)
	if doc.google_drive_status == "Queued":
		from frappe_recorder.api.drive import upload_recording

		upload_recording(doc.name)


def fix_video_metadata(doc):
	"""Browsers write WebM files without a duration, which leaves them unseekable.

	A stream copy through ffmpeg (when installed) rewrites the container with proper
	cues and duration. It is optional: without ffmpeg the player falls back to the
	duration stored on the document.
	"""
	import shutil
	import subprocess

	ffmpeg = shutil.which("ffmpeg")
	path = get_video_path(doc)
	if not ffmpeg or not path or not os.path.exists(path):
		return

	base, extension = os.path.splitext(path)
	fixed = f"{base}.fixed{extension}"
	try:
		subprocess.run(
			[ffmpeg, "-y", "-loglevel", "error", "-i", path, "-c", "copy", fixed],
			check=True,
			timeout=30 * 60,
		)
		os.replace(fixed, path)
		frappe.db.set_value("Screen Recording", doc.name, "file_size", os.path.getsize(path))
		frappe.db.commit()
	except Exception:
		frappe.log_error(f"Could not fix metadata for {doc.name}", reference_doctype="Screen Recording")
		if os.path.exists(fixed):
			os.remove(fixed)


def save_thumbnail(doc, data_url):
	header, _sep, encoded = data_url.partition(",")
	if not header.startswith("data:image/"):
		return None
	content = base64.b64decode(encoded)
	if len(content) > 5 * 1024 * 1024:
		return None
	extension = "png" if "png" in header else "jpg"
	path = frappe.get_site_path("public", "files", f"thumbnail-{doc.share_id}.{extension}")
	with open(path, "wb") as f:
		f.write(content)
	return attach_file(doc, path, "thumbnail")


@frappe.whitelist()
def get_recordings(folder=None, search=None, start=0, page_length=60):
	ensure_logged_in()
	filters = {"owner": frappe.session.user, "status": ["!=", "Recording"]}
	if folder:
		filters["folder"] = folder
	or_filters = None
	if search:
		or_filters = {"title": ["like", f"%{search}%"], "description": ["like", f"%{search}%"]}

	recordings = frappe.get_all(
		"Screen Recording",
		filters=filters,
		or_filters=or_filters,
		fields=[
			"name",
			"share_id",
			"title",
			"status",
			"folder",
			"recording_mode",
			"thumbnail",
			"video_file",
			"duration_seconds",
			"view_count",
			"is_public",
			"google_drive_status",
			"drive_web_link",
			"creation",
		],
		order_by="creation desc",
		start=cint(start),
		page_length=cint(page_length),
	)
	if recordings:
		counts = frappe.get_all(
			"Recording Comment",
			filters={"recording": ["in", [r.name for r in recordings]], "comment_type": "Comment"},
			fields=["recording", "count(name) as count"],
			group_by="recording",
		)
		counts = {c.recording: c.count for c in counts}
		for r in recordings:
			r.share_url = get_share_url(r.share_id)
			r.comment_count = counts.get(r.name, 0)
			r.creation = to_utc_iso(r.creation)
	return recordings


@frappe.whitelist(allow_guest=True)
def get_recording(share_id):
	doc = get_viewable_recording(share_id)
	is_owner = can_manage(doc)
	owner = frappe.db.get_value("User", doc.owner, ["full_name", "user_image"], as_dict=True) or {}

	drive_shared = doc.drive_file_id and (
		is_owner or frappe.db.get_value("Recorder Drive Account", doc.owner, "share_on_drive")
	)
	data = {
		"name": doc.name,
		"share_id": doc.share_id,
		"share_url": get_share_url(doc.share_id),
		"title": doc.title,
		"description": doc.description,
		"status": doc.status,
		"recording_mode": doc.recording_mode,
		"creation": to_utc_iso(doc.creation),
		"duration_seconds": doc.duration_seconds,
		"view_count": doc.view_count,
		"thumbnail": doc.thumbnail,
		"video_url": doc.video_file if doc.status == "Ready" else None,
		"mime_type": doc.mime_type,
		"drive_file_id": doc.drive_file_id if drive_shared else None,
		"drive_web_link": doc.drive_web_link if drive_shared else None,
		"is_public": doc.is_public,
		"allow_comments": doc.allow_comments,
		"allow_download": doc.allow_download or is_owner,
		"owner_name": owner.get("full_name") or doc.owner,
		"owner_image": owner.get("user_image"),
		"is_owner": is_owner,
		"comments": get_comments(doc.name),
	}
	if is_owner:
		data.update(
			{
				"folder": doc.folder,
				"file_size": doc.file_size,
				"google_drive_status": doc.google_drive_status,
				"drive_error": doc.drive_error,
			}
		)
	return data


@frappe.whitelist(allow_guest=True, methods=["POST"])
def register_view(share_id):
	doc = get_viewable_recording(share_id)
	if frappe.session.user == doc.owner:
		return doc.view_count

	viewer = frappe.session.user if frappe.session.user != "Guest" else frappe.local.request_ip
	cache_key = f"frappe_recorder:view:{doc.name}:{viewer}"
	if frappe.cache.get_value(cache_key, expires=True):
		return doc.view_count
	frappe.cache.set_value(cache_key, 1, expires_in_sec=60 * 60)

	frappe.db.sql(
		"update `tabScreen Recording` set view_count = coalesce(view_count, 0) + 1 where name = %s",
		doc.name,
	)
	return cint(doc.view_count) + 1


@frappe.whitelist(methods=["POST"])
def update_recording(recording, **fields):
	doc = get_owned_doc("Screen Recording", recording)
	editable = ("title", "description", "is_public", "allow_comments", "allow_download", "folder")
	for field in editable:
		if field in fields:
			doc.set(field, fields[field])
	if doc.folder:
		get_owned_doc("Recording Folder", doc.folder)
	if not (doc.title or "").strip():
		frappe.throw(_("Title cannot be empty"))
	privacy_changed = doc.has_value_changed("is_public")
	doc.save()
	if privacy_changed:
		sync_media_privacy(doc)
	return get_recording(doc.share_id)


def sync_media_privacy(doc):
	"""Keep the video and thumbnail files as private as the recording.

	Public recordings are served as public files (fast, seekable, cacheable). A private
	recording's files are moved to private storage, where Frappe only serves them to
	people who can read the recording, so the old `/files/...` URL stops working.
	"""
	is_private = 0 if cint(doc.is_public) else 1
	for fieldname in ("video_file", "thumbnail"):
		for name in frappe.get_all(
			"File",
			filters={
				"attached_to_doctype": "Screen Recording",
				"attached_to_name": doc.name,
				"attached_to_field": fieldname,
				"is_private": 1 - is_private,
			},
			pluck="name",
		):
			file_doc = frappe.get_doc("File", name)
			file_doc.is_private = is_private
			file_doc.save(ignore_permissions=True)
			doc.db_set(fieldname, file_doc.file_url, update_modified=False)


def get_video_path(doc):
	"""Path on disk of the recording's video, whether it is stored public or private."""
	if not doc.video_file:
		return None
	if doc.video_file.startswith("/private/files/"):
		return frappe.get_site_path("private", "files", doc.video_file.rsplit("/", 1)[-1])
	return frappe.get_site_path("public", "files", doc.video_file.rsplit("/", 1)[-1])


@frappe.whitelist(methods=["POST"])
def delete_recording(recording, delete_from_drive=False):
	doc = get_owned_doc("Screen Recording", recording)
	if cint(delete_from_drive) and doc.drive_file_id:
		from frappe_recorder.api.drive import delete_drive_file

		delete_drive_file(doc.owner, doc.drive_file_id)
	doc.delete()


def get_comments(recording):
	comments = frappe.get_all(
		"Recording Comment",
		filters={"recording": recording},
		fields=[
			"name",
			"comment_type",
			"content",
			"timestamp_seconds",
			"commenter",
			"commenter_name",
			"creation",
		],
		order_by="creation asc",
	)
	for comment in comments:
		comment.creation = to_utc_iso(comment.creation)
	return comments


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=60, seconds=60 * 60)
def add_comment(share_id, content, comment_type="Comment", timestamp_seconds=None, commenter_name=None):
	doc = get_viewable_recording(share_id)
	if not doc.allow_comments:
		frappe.throw(_("Comments are turned off for this recording."))

	content = (content or "").strip()
	if comment_type == "Reaction":
		if content not in REACTIONS:
			frappe.throw(_("Unsupported reaction"))
	elif comment_type == "Comment":
		if not content:
			frappe.throw(_("Comment cannot be empty"))
		content = frappe.utils.strip_html(content)[:2000]
	else:
		frappe.throw(_("Invalid comment type"))

	user = frappe.session.user
	if user == "Guest":
		commenter_name = (frappe.utils.strip_html(commenter_name or "").strip() or _("Guest"))[:80]
	else:
		commenter_name = frappe.db.get_value("User", user, "full_name") or user

	comment = frappe.get_doc(
		{
			"doctype": "Recording Comment",
			"recording": doc.name,
			"comment_type": comment_type,
			"content": content,
			"timestamp_seconds": flt(timestamp_seconds) if timestamp_seconds not in (None, "") else None,
			"commenter": None if user == "Guest" else user,
			"commenter_name": commenter_name,
		}
	)
	comment.insert(ignore_permissions=True)
	data = comment.as_dict()
	data.creation = to_utc_iso(comment.creation)
	return data


@frappe.whitelist(methods=["POST"])
def delete_comment(comment):
	comment = frappe.get_doc("Recording Comment", comment)
	recording = frappe.get_doc("Screen Recording", comment.recording)
	if not (can_manage(recording) or (comment.commenter and comment.commenter == frappe.session.user)):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	comment.delete(ignore_permissions=True)


@frappe.whitelist()
def get_folders():
	ensure_logged_in()
	folders = frappe.get_all(
		"Recording Folder",
		filters={"owner": frappe.session.user},
		fields=["name", "folder_name"],
		order_by="folder_name asc",
	)
	counts = frappe.get_all(
		"Screen Recording",
		filters={"owner": frappe.session.user, "folder": ["is", "set"], "status": ["!=", "Recording"]},
		fields=["folder", "count(name) as count"],
		group_by="folder",
	)
	counts = {c.folder: c.count for c in counts}
	for folder in folders:
		folder.count = counts.get(folder.name, 0)
	return folders


@frappe.whitelist(methods=["POST"])
def create_folder(folder_name):
	ensure_logged_in()
	folder_name = (folder_name or "").strip()
	if not folder_name:
		frappe.throw(_("Folder name is required"))
	doc = frappe.get_doc({"doctype": "Recording Folder", "folder_name": folder_name}).insert()
	return {"name": doc.name, "folder_name": doc.folder_name, "count": 0}


@frappe.whitelist(methods=["POST"])
def rename_folder(folder, folder_name):
	doc = get_owned_doc("Recording Folder", folder)
	doc.folder_name = (folder_name or "").strip() or doc.folder_name
	doc.save()


@frappe.whitelist(methods=["POST"])
def delete_folder(folder):
	doc = get_owned_doc("Recording Folder", folder)
	frappe.db.set_value("Screen Recording", {"folder": doc.name}, "folder", None)
	doc.delete()


def get_recording_summary(doc):
	return {
		"name": doc.name,
		"share_id": doc.share_id,
		"share_url": get_share_url(doc.share_id),
		"status": doc.status,
		"google_drive_status": doc.google_drive_status,
	}


def to_utc_iso(value):
	"""Frappe stores naive datetimes in the site's time zone; browsers need an absolute time."""
	if not value:
		return value
	local = get_datetime(value).replace(tzinfo=ZoneInfo(get_system_timezone()))
	return local.astimezone(timezone.utc).isoformat()


def ensure_logged_in():
	if frappe.session.user == "Guest":
		frappe.throw(_("Please log in to continue."), frappe.AuthenticationError)


def can_manage(doc):
	user = frappe.session.user
	return user != "Guest" and (doc.owner == user or "System Manager" in frappe.get_roles(user))


def get_owned_doc(doctype, name):
	ensure_logged_in()
	doc = frappe.get_doc(doctype, name)
	if not can_manage(doc):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	return doc


def get_viewable_recording(share_id):
	name = frappe.db.get_value("Screen Recording", {"share_id": share_id or ""}, "name")
	if not name:
		frappe.throw(_("This recording does not exist or was deleted."), frappe.DoesNotExistError)
	doc = frappe.get_doc("Screen Recording", name)
	if not doc.is_public and not can_manage(doc):
		frappe.throw(_("This recording is private."), frappe.PermissionError)
	return doc
