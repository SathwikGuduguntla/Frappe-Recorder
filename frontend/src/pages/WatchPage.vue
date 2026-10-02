<template>
	<div class="min-h-screen bg-surface-gray-1">
		<AppHeader />

		<div v-if="loading && !rec" class="flex justify-center py-24">
			<LoadingIndicator class="size-6 text-ink-gray-5" />
		</div>

		<div
			v-else-if="loadError"
			class="mx-auto flex max-w-md flex-col items-center gap-3 px-4 py-24 text-center"
		>
			<span class="lucide-video-off size-10 text-ink-gray-4" />
			<p class="font-medium text-ink-gray-8">{{ loadError }}</p>
			<Button v-if="session.isGuest" label="Log in to view" @click="redirectToLogin()" />
		</div>

		<main
			v-else-if="rec"
			class="mx-auto grid max-w-6xl gap-6 px-4 py-6 lg:grid-cols-[1fr_340px]"
		>
			<section class="min-w-0">
				<div
					v-if="rec.status === 'Recording' || rec.status === 'Processing'"
					class="flex aspect-video flex-col items-center justify-center gap-3 rounded-6 bg-surface-gray-9 text-center text-white"
				>
					<span class="relative flex size-3">
						<span
							class="absolute inline-flex size-full animate-ping rounded-full bg-surface-red-5 opacity-75"
						/>
						<span class="relative inline-flex size-3 rounded-full bg-surface-red-6" />
					</span>
					<p class="font-medium">This video is still being recorded</p>
					<p class="text-sm text-white/70">
						It will start playing here as soon as {{ rec.owner_name }} finishes.
					</p>
				</div>
				<VideoPlayer
					v-else
					ref="player"
					:src="rec.video_url"
					:poster="rec.thumbnail"
					:drive-file-id="rec.drive_file_id"
					:placeholder="
						rec.status === 'Failed'
							? 'This recording failed to upload'
							: 'Video is not available'
					"
					@timeupdate="(t) => (currentTime = t)"
				/>

				<!-- Title & meta -->
				<div class="mt-4 flex flex-wrap items-start gap-3">
					<div class="min-w-0 flex-1">
						<input
							v-if="rec.is_owner"
							v-model="title"
							class="-mx-1 w-full rounded-1 border-0 bg-transparent px-1 py-0.5 text-xl font-semibold text-ink-gray-9 hover:bg-surface-gray-2 focus:bg-surface-base focus:ring-2 focus:ring-outline-gray-3"
							aria-label="Title"
							@blur="saveTitle"
							@keydown.enter="$event.target.blur()"
						/>
						<h1 v-else class="text-xl font-semibold text-ink-gray-9">
							{{ rec.title }}
						</h1>
						<div
							class="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-ink-gray-5"
						>
							<span class="flex items-center gap-2 text-ink-gray-8">
								<Avatar
									:image="rec.owner_image"
									:label="rec.owner_name"
									size="sm"
								/>
								{{ rec.owner_name }}
							</span>
							<span>{{ timeAgo(rec.creation) }}</span>
							<span v-if="rec.duration_seconds">{{
								formatDuration(rec.duration_seconds)
							}}</span>
							<span
								>{{ rec.view_count || 0 }}
								{{ rec.view_count === 1 ? 'view' : 'views' }}</span
							>
							<span v-if="!rec.is_public" class="flex items-center gap-1"
								><span class="lucide-lock size-3.5" />Only you</span
							>
						</div>
					</div>

					<div class="flex items-center gap-2">
						<Button
							variant="solid"
							icon-left="lucide-link"
							label="Copy link"
							@click="copyLink"
						/>
						<Button
							v-if="rec.allow_download && rec.video_url"
							icon="lucide-download"
							tooltip="Download"
							aria-label="Download"
							@click="download"
						/>
						<Button
							v-if="rec.drive_web_link"
							icon="lucide-hard-drive"
							tooltip="Open in Google Drive"
							aria-label="Open in Google Drive"
							:href="rec.drive_web_link"
						/>
						<Dropdown v-if="rec.is_owner" :options="ownerMenu" align="end">
							<Button icon="lucide-more-horizontal" aria-label="More options" />
						</Dropdown>
					</div>
				</div>

				<!-- Description -->
				<div class="mt-4">
					<textarea
						v-if="rec.is_owner"
						v-model="description"
						rows="2"
						placeholder="Add a description…"
						class="w-full resize-y rounded-4 border-0 bg-transparent px-2 py-1.5 text-sm text-ink-gray-7 placeholder:text-ink-gray-4 hover:bg-surface-gray-2 focus:bg-surface-base focus:ring-2 focus:ring-outline-gray-3"
						@blur="saveDescription"
					/>
					<p
						v-else-if="rec.description"
						class="whitespace-pre-line text-sm text-ink-gray-7"
					>
						{{ rec.description }}
					</p>
				</div>

				<!-- Reactions -->
				<div
					v-if="rec.allow_comments && rec.status === 'Ready'"
					class="mt-4 flex flex-wrap items-center gap-1.5"
				>
					<button
						v-for="emoji in REACTIONS"
						:key="emoji"
						class="flex h-8 items-center gap-1 rounded-full border border-outline-gray-2 bg-surface-base px-2.5 text-base transition-transform hover:scale-105 active:scale-95"
						:title="`React at ${formatDuration(currentTime)}`"
						@click="react(emoji)"
					>
						{{ emoji }}
						<span v-if="reactionCounts[emoji]" class="text-xs text-ink-gray-6">{{
							reactionCounts[emoji]
						}}</span>
					</button>
				</div>

				<!-- Drive status for the owner -->
				<div
					v-if="rec.is_owner && driveStatus"
					class="mt-6 flex flex-wrap items-center gap-3 rounded-6 border border-outline-gray-2 bg-surface-base p-4"
				>
					<span class="lucide-hard-drive size-5 text-ink-gray-6" />
					<div class="min-w-0 flex-1">
						<p class="text-sm font-medium text-ink-gray-9">Google Drive</p>
						<p class="text-sm text-ink-gray-6">
							<template v-if="rec.google_drive_status === 'Synced'"
								>Saved in your Drive folder.</template
							>
							<template v-else-if="rec.google_drive_status === 'Queued'"
								>Waiting to upload…</template
							>
							<template v-else-if="rec.google_drive_status === 'Uploading'"
								>Uploading to your Drive…</template
							>
							<template v-else-if="rec.google_drive_status === 'Failed'">
								Upload failed: {{ rec.drive_error || 'unknown error' }}
							</template>
							<template v-else-if="!driveStatus.connected"
								>Connect Google Drive to keep a copy there.</template
							>
							<template v-else-if="!driveStatus.folder_id"
								>Choose a Drive folder in Settings to upload this video.</template
							>
							<template v-else
								>Not uploaded to {{ driveStatus.folder_name }} yet.</template
							>
						</p>
					</div>
					<Button
						v-if="rec.google_drive_status === 'Synced'"
						label="Open in Drive"
						icon-right="lucide-arrow-up-right"
						:href="rec.drive_web_link"
					/>
					<Button
						v-else-if="!driveStatus.connected || !driveStatus.folder_id"
						label="Settings"
						:route="{ name: 'Settings' }"
					/>
					<Button
						v-else-if="
							['Not Synced', 'Failed'].includes(rec.google_drive_status) &&
							rec.video_url
						"
						:label="
							rec.google_drive_status === 'Failed'
								? 'Retry upload'
								: 'Upload to Drive'
						"
						icon-left="lucide-upload-cloud"
						:loading="syncing"
						@click="syncToDrive"
					/>
				</div>
			</section>

			<!-- Comments -->
			<aside
				class="flex min-h-0 flex-col rounded-6 border border-outline-gray-2 bg-surface-base lg:sticky lg:top-20 lg:max-h-[calc(100vh-6rem)]"
			>
				<div class="border-b border-outline-gray-1 px-4 py-3">
					<h2 class="font-medium text-ink-gray-9">
						Comments <span class="text-ink-gray-5">{{ comments.length || '' }}</span>
					</h2>
				</div>

				<div class="min-h-24 flex-1 overflow-y-auto px-4 py-2">
					<p v-if="!comments.length" class="py-8 text-center text-sm text-ink-gray-5">
						{{
							rec.allow_comments
								? 'No comments yet. Start the conversation.'
								: 'Comments are turned off.'
						}}
					</p>
					<div v-for="c in comments" :key="c.name" class="group flex gap-2.5 py-2.5">
						<Avatar :label="c.commenter_name" size="md" />
						<div class="min-w-0 flex-1">
							<div class="flex items-center gap-2 text-xs">
								<span class="font-medium text-ink-gray-8">{{
									c.commenter_name
								}}</span>
								<span class="text-ink-gray-5">{{ timeAgo(c.creation) }}</span>
								<button
									v-if="canDelete(c)"
									class="ml-auto hidden text-ink-gray-5 hover:text-ink-red-4 group-hover:block"
									aria-label="Delete comment"
									@click="deleteComment(c)"
								>
									<span class="lucide-trash-2 size-3.5" />
								</button>
							</div>
							<p
								class="mt-0.5 whitespace-pre-line break-words text-sm text-ink-gray-8"
							>
								<button
									v-if="c.timestamp_seconds != null"
									class="mr-1 rounded-1 bg-surface-blue-1 px-1 text-xs font-medium tabular-nums text-ink-blue-5 hover:bg-surface-blue-2"
									@click="player?.seek(c.timestamp_seconds)"
								>
									{{ formatDuration(c.timestamp_seconds) }}
								</button>
								{{ c.content }}
							</p>
						</div>
					</div>
				</div>

				<form
					v-if="rec.allow_comments"
					class="border-t border-outline-gray-1 p-3"
					@submit.prevent="addComment"
				>
					<TextInput
						v-if="session.isGuest"
						v-model="guestName"
						class="mb-2"
						placeholder="Your name"
					/>
					<Textarea
						v-model="newComment"
						:rows="2"
						placeholder="Write a comment…"
						@keydown.meta.enter="addComment"
						@keydown.ctrl.enter="addComment"
					/>
					<div class="mt-2 flex items-center gap-2">
						<Checkbox
							v-if="rec.status === 'Ready'"
							v-model="atTimestamp"
							:label="`At ${formatDuration(currentTime)}`"
							size="sm"
						/>
						<Button
							class="ml-auto"
							type="submit"
							variant="solid"
							label="Comment"
							:loading="posting"
							:disabled="!newComment.trim()"
						/>
					</div>
				</form>
			</aside>
		</main>
	</div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
	Avatar,
	Button,
	Checkbox,
	Dropdown,
	LoadingIndicator,
	Textarea,
	TextInput,
	call,
	dialog,
	toast,
} from 'frappe-ui'

import AppHeader from '@/components/AppHeader.vue'
import VideoPlayer from '@/components/VideoPlayer.vue'
import { redirectToLogin, session } from '@/session'
import { copyToClipboard, errorMessage, formatDuration, timeAgo } from '@/utils/format'

const API = 'frappe_recorder.api.recording'
const REACTIONS = ['👍', '❤️', '😂', '🎉', '😮', '🔥', '👏', '🤔']
const GUEST_NAME_KEY = 'frappe_recorder_guest_name'

const props = defineProps({ shareId: { type: String, required: true } })
const router = useRouter()

const rec = ref(null)
const loading = ref(false)
const loadError = ref('')
const player = ref(null)
const currentTime = ref(0)
const title = ref('')
const description = ref('')
const driveStatus = ref(null)
const syncing = ref(false)

const newComment = ref('')
const atTimestamp = ref(true)
const posting = ref(false)
const guestName = ref(readGuestName())

let pollTimer = null
let viewRegistered = false

const comments = computed(() =>
	(rec.value?.comments || []).filter((c) => c.comment_type === 'Comment')
)
const reactionCounts = computed(() => {
	const counts = {}
	for (const c of rec.value?.comments || []) {
		if (c.comment_type === 'Reaction') counts[c.content] = (counts[c.content] || 0) + 1
	}
	return counts
})

async function load({ quiet = false } = {}) {
	if (!quiet) loading.value = true
	try {
		const data = await call(`${API}.get_recording`, { share_id: props.shareId })
		rec.value = data
		title.value = data.title
		description.value = data.description || ''
		loadError.value = ''
		document.title = data.title
		if (data.status === 'Ready' && !viewRegistered) {
			viewRegistered = true
			call(`${API}.register_view`, { share_id: props.shareId })
				.then((count) => (rec.value.view_count = count))
				.catch(() => {})
		}
		if (data.is_owner && !driveStatus.value) {
			driveStatus.value = await call('frappe_recorder.api.drive.get_status').catch(
				() => null
			)
		}
		schedulePoll()
	} catch (e) {
		if (!quiet) loadError.value = errorMessage(e, 'This recording could not be loaded.')
	} finally {
		loading.value = false
	}
}

// Keep the page fresh while the recording is still being made or uploaded to Drive.
function schedulePoll() {
	clearTimeout(pollTimer)
	const r = rec.value
	const waiting =
		r &&
		(['Recording', 'Processing'].includes(r.status) ||
			['Queued', 'Uploading'].includes(r.google_drive_status))
	if (waiting) pollTimer = setTimeout(() => load({ quiet: true }), 5000)
}

watch(
	() => props.shareId,
	() => {
		viewRegistered = false
		load()
	},
	{ immediate: true }
)
onBeforeUnmount(() => clearTimeout(pollTimer))

async function update(fields) {
	try {
		const data = await call(`${API}.update_recording`, {
			recording: rec.value.name,
			...fields,
		})
		rec.value = { ...rec.value, ...data }
	} catch (e) {
		toast.error(errorMessage(e))
	}
}

function saveTitle() {
	const value = title.value.trim()
	if (!value) title.value = rec.value.title
	else if (value !== rec.value.title) update({ title: value })
}

function saveDescription() {
	if (description.value !== (rec.value.description || ''))
		update({ description: description.value })
}

async function copyLink() {
	await copyToClipboard(rec.value.share_url)
	toast.success('Link copied')
}

function download() {
	const link = document.createElement('a')
	link.href = rec.value.video_url
	link.download = `${rec.value.title}.${rec.value.video_url.split('.').pop()}`
	link.click()
}

const ownerMenu = computed(() => [
	{
		label: 'Anyone with the link can view',
		switch: true,
		switchValue: Boolean(rec.value.is_public),
		onClick: (value) => update({ is_public: value ? 1 : 0 }),
	},
	{
		label: 'Allow comments',
		switch: true,
		switchValue: Boolean(rec.value.allow_comments),
		onClick: (value) => update({ allow_comments: value ? 1 : 0 }),
	},
	{
		label: 'Allow viewers to download',
		switch: true,
		switchValue: Boolean(rec.value.allow_download),
		onClick: (value) => update({ allow_download: value ? 1 : 0 }),
	},
	{ label: 'Delete recording', icon: 'lucide-trash-2', theme: 'red', onClick: remove },
])

function remove() {
	dialog.prompt({
		title: 'Delete recording?',
		message: "People with the link won't be able to watch it any more.",
		theme: 'red',
		fields: rec.value.drive_file_id
			? [
					{
						name: 'delete_from_drive',
						type: 'checkbox',
						label: 'Also delete the copy in Google Drive',
					},
			  ]
			: [],
		confirmLabel: 'Delete',
		onConfirm: async ({ values }) => {
			await call(`${API}.delete_recording`, {
				recording: rec.value.name,
				delete_from_drive: values.delete_from_drive ? 1 : 0,
			})
			toast.success('Recording deleted')
			router.push({ name: 'Library' })
		},
	})
}

async function syncToDrive() {
	syncing.value = true
	try {
		rec.value.google_drive_status = await call('frappe_recorder.api.drive.sync_recording', {
			recording: rec.value.name,
		})
		schedulePoll()
	} catch (e) {
		toast.error(errorMessage(e))
	} finally {
		syncing.value = false
	}
}

async function addComment() {
	const content = newComment.value.trim()
	if (!content || posting.value) return
	posting.value = true
	try {
		const comment = await call(`${API}.add_comment`, {
			share_id: props.shareId,
			content,
			timestamp_seconds:
				atTimestamp.value && rec.value.status === 'Ready' ? currentTime.value : null,
			commenter_name: guestName.value,
		})
		rec.value.comments.push(comment)
		newComment.value = ''
		saveGuestName()
	} catch (e) {
		toast.error(errorMessage(e))
	} finally {
		posting.value = false
	}
}

async function react(emoji) {
	try {
		const reaction = await call(`${API}.add_comment`, {
			share_id: props.shareId,
			content: emoji,
			comment_type: 'Reaction',
			timestamp_seconds: currentTime.value,
			commenter_name: guestName.value,
		})
		rec.value.comments.push(reaction)
	} catch (e) {
		toast.error(errorMessage(e))
	}
}

function canDelete(comment) {
	return rec.value.is_owner || (!session.isGuest && comment.commenter === session.user)
}

async function deleteComment(comment) {
	try {
		await call(`${API}.delete_comment`, { comment: comment.name })
		rec.value.comments = rec.value.comments.filter((c) => c.name !== comment.name)
	} catch (e) {
		toast.error(errorMessage(e))
	}
}

function readGuestName() {
	try {
		return localStorage.getItem(GUEST_NAME_KEY) || ''
	} catch {
		return ''
	}
}

function saveGuestName() {
	try {
		if (guestName.value) localStorage.setItem(GUEST_NAME_KEY, guestName.value)
	} catch {
		// storage can be unavailable (private mode); the name is just not remembered
	}
}
</script>
