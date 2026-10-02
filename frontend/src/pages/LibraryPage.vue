<template>
	<div class="min-h-screen bg-surface-gray-1">
		<AppHeader />

		<main class="mx-auto max-w-6xl px-4 py-6">
			<div class="flex flex-wrap items-center gap-3">
				<div>
					<h1 class="text-xl font-semibold text-ink-gray-9">
						{{ session.isGuest ? 'Recordings on this device' : 'My recordings' }}
					</h1>
					<p v-if="session.isGuest" class="mt-0.5 text-sm text-ink-gray-5">
						Recorded in this browser without an account.
						<button class="underline" @click="redirectToLogin()">Log in</button>
						to keep them with your account.
					</p>
				</div>
				<div class="ml-auto w-full sm:w-64">
					<TextInput v-model="search" placeholder="Search recordings" :debounce="300">
						<template #prefix
							><span class="lucide-search size-4 text-ink-gray-5"
						/></template>
					</TextInput>
				</div>
			</div>

			<!-- Folders -->
			<div v-if="!session.isGuest" class="mt-4 flex flex-wrap items-center gap-2">
				<button class="chip" :class="{ 'chip-active': !folder }" @click="folder = null">
					All
				</button>
				<div
					v-for="f in folders"
					:key="f.name"
					class="chip !px-0"
					:class="{ 'chip-active': folder === f.name }"
				>
					<button
						class="flex h-full items-center gap-1.5 pl-3"
						:class="folder === f.name ? 'pr-1' : 'pr-3'"
						@click="folder = f.name"
					>
						<span class="lucide-folder size-3.5" />
						{{ f.folder_name }}
						<span class="text-ink-gray-5">{{ f.count }}</span>
					</button>
					<Dropdown v-if="folder === f.name" :options="folderMenu(f)">
						<button class="flex h-full items-center pr-2" aria-label="Folder options">
							<span class="lucide-chevron-down size-3.5" />
						</button>
					</Dropdown>
				</div>
				<button class="chip border-dashed" @click="newFolder">
					<span class="lucide-folder-plus size-3.5" />
					New folder
				</button>
			</div>

			<div v-if="loading && !recordings.length" class="mt-16 flex justify-center">
				<LoadingIndicator class="size-6 text-ink-gray-5" />
			</div>

			<div
				v-else-if="!recordings.length"
				class="mt-8 flex flex-col items-center gap-3 rounded-6 border border-dashed border-outline-gray-3 px-6 py-16 text-center"
			>
				<span class="lucide-video size-10 text-ink-gray-4" />
				<p class="font-medium text-ink-gray-8">
					{{ search ? 'No recordings match your search' : 'No recordings yet' }}
				</p>
				<p v-if="!search" class="max-w-sm text-sm text-ink-gray-5">
					Record your screen and camera, then share the link. Anyone with the link can
					watch and comment.
				</p>
				<Button
					v-if="!search"
					variant="solid"
					icon-left="lucide-circle-dot"
					label="Record your first video"
					:route="{ name: 'Record', query: folder ? { folder } : {} }"
				/>
			</div>

			<div v-else class="mt-6 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
				<article
					v-for="item in recordings"
					:key="item.name"
					class="group overflow-hidden rounded-6 border border-outline-gray-2 bg-surface-base shadow-sm transition-shadow hover:shadow-md"
				>
					<router-link
						:to="{ name: 'Watch', params: { shareId: item.share_id } }"
						class="relative block aspect-video bg-surface-gray-9"
					>
						<img
							v-if="item.thumbnail"
							:src="item.thumbnail"
							alt=""
							class="size-full object-cover"
							loading="lazy"
						/>
						<div
							v-else
							class="flex size-full items-center justify-center text-ink-gray-4"
						>
							<span class="lucide-video size-8" />
						</div>
						<span
							v-if="item.duration_seconds"
							class="absolute bottom-2 right-2 rounded-1 bg-black/75 px-1.5 py-0.5 text-xs font-medium tabular-nums text-white"
						>
							{{ formatDuration(item.duration_seconds) }}
						</span>
						<span
							v-if="item.status !== 'Ready'"
							class="absolute left-2 top-2 rounded-1 bg-black/75 px-1.5 py-0.5 text-xs text-white"
						>
							{{ item.status }}
						</span>
					</router-link>

					<div class="flex items-start gap-2 p-3">
						<div class="min-w-0 flex-1">
							<router-link
								:to="{ name: 'Watch', params: { shareId: item.share_id } }"
								class="line-clamp-1 font-medium text-ink-gray-9 hover:underline"
							>
								{{ item.title }}
							</router-link>
							<div
								class="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-gray-5"
							>
								<span>{{ timeAgo(item.creation) }}</span>
								<span class="flex items-center gap-1"
									><span class="lucide-eye size-3" />{{
										item.view_count || 0
									}}</span
								>
								<span class="flex items-center gap-1">
									<span class="lucide-message-circle size-3" />{{
										item.comment_count
									}}
								</span>
								<DriveBadge :status="item.google_drive_status" />
								<span v-if="!item.is_public" class="flex items-center gap-1"
									><span class="lucide-lock size-3" />Private</span
								>
							</div>
						</div>
						<Button
							icon="lucide-link"
							variant="ghost"
							tooltip="Copy link"
							aria-label="Copy link"
							@click="copyLink(item)"
						/>
						<Dropdown :options="recordingMenu(item)" align="end">
							<Button
								icon="lucide-more-horizontal"
								variant="ghost"
								aria-label="More options"
							/>
						</Dropdown>
					</div>
				</article>
			</div>

			<div v-if="hasMore" class="mt-6 flex justify-center">
				<Button label="Load more" :loading="loading" @click="load(true)" />
			</div>
		</main>
	</div>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Button, Dropdown, LoadingIndicator, TextInput, call, dialog, toast } from 'frappe-ui'

import AppHeader from '@/components/AppHeader.vue'
import { redirectToLogin, session } from '@/session'
import DriveBadge from '@/components/DriveBadge.vue'
import { copyToClipboard, errorMessage, formatDuration, timeAgo } from '@/utils/format'

const API = 'frappe_recorder.api.recording'
const PAGE_LENGTH = 30

const router = useRouter()
const recordings = ref([])
const folders = ref([])
const folder = ref(null)
const search = ref('')
const loading = ref(false)
const hasMore = ref(false)

async function load(more = false) {
	loading.value = true
	try {
		const rows = await call(`${API}.get_recordings`, {
			folder: folder.value,
			search: search.value,
			start: more ? recordings.value.length : 0,
			page_length: PAGE_LENGTH,
		})
		recordings.value = more ? [...recordings.value, ...rows] : rows
		hasMore.value = rows.length === PAGE_LENGTH
	} catch (e) {
		toast.error(errorMessage(e))
	} finally {
		loading.value = false
	}
}

async function loadFolders() {
	folders.value = await call(`${API}.get_folders`)
}

watch([folder, search], () => load())
onMounted(() => Promise.all([load(), loadFolders()]))

async function copyLink(item) {
	await copyToClipboard(item.share_url)
	toast.success('Link copied')
}

function recordingMenu(item) {
	return [
		{
			label: 'Open',
			icon: 'lucide-play',
			onClick: () => router.push({ name: 'Watch', params: { shareId: item.share_id } }),
		},
		{ label: 'Copy link', icon: 'lucide-link', onClick: () => copyLink(item) },
		{ label: 'Rename', icon: 'lucide-pencil', onClick: () => rename(item) },
		!session.isGuest && {
			label: 'Move to folder',
			icon: 'lucide-folder-input',
			onClick: () => move(item),
		},
		item.video_file && {
			label: 'Download',
			icon: 'lucide-download',
			onClick: () => window.open(item.video_file, '_blank'),
		},
		item.drive_web_link && {
			label: 'Open in Google Drive',
			icon: 'lucide-hard-drive',
			onClick: () => window.open(item.drive_web_link, '_blank'),
		},
		{ label: 'Delete', icon: 'lucide-trash-2', theme: 'red', onClick: () => remove(item) },
	].filter(Boolean)
}

function rename(item) {
	dialog.prompt({
		title: 'Rename recording',
		fields: [{ name: 'title', label: 'Title', defaultValue: item.title, required: true }],
		confirmLabel: 'Save',
		onConfirm: async ({ values }) => {
			await call(`${API}.update_recording`, { recording: item.name, title: values.title })
			item.title = values.title
		},
	})
}

function move(item) {
	dialog.prompt({
		title: 'Move to folder',
		fields: [
			{
				name: 'folder',
				type: 'select',
				label: 'Folder',
				defaultValue: item.folder || '',
				options: [
					{ label: 'No folder', value: '' },
					...folders.value.map((f) => ({ label: f.folder_name, value: f.name })),
				],
			},
		],
		confirmLabel: 'Move',
		onConfirm: async ({ values }) => {
			await call(`${API}.update_recording`, {
				recording: item.name,
				folder: values.folder || null,
			})
			await Promise.all([load(), loadFolders()])
		},
	})
}

function remove(item) {
	dialog.prompt({
		title: 'Delete recording?',
		message: `"${item.title}" and its comments will be deleted. People with the link won't be able to watch it any more.`,
		theme: 'red',
		fields: item.drive_web_link
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
				recording: item.name,
				delete_from_drive: values.delete_from_drive ? 1 : 0,
			})
			recordings.value = recordings.value.filter((r) => r.name !== item.name)
			loadFolders()
			toast.success('Recording deleted')
		},
	})
}

function newFolder() {
	dialog.prompt({
		title: 'New folder',
		fields: [{ name: 'folder_name', label: 'Name', required: true }],
		confirmLabel: 'Create',
		onConfirm: async ({ values }) => {
			const created = await call(`${API}.create_folder`, { folder_name: values.folder_name })
			folders.value = [...folders.value, created].sort((a, b) =>
				a.folder_name.localeCompare(b.folder_name)
			)
			folder.value = created.name
		},
	})
}

function folderMenu(f) {
	return [
		{
			label: 'Record into this folder',
			icon: 'lucide-circle-dot',
			onClick: () => router.push({ name: 'Record', query: { folder: f.name } }),
		},
		{
			label: 'Rename folder',
			icon: 'lucide-pencil',
			onClick: () =>
				dialog.prompt({
					title: 'Rename folder',
					fields: [
						{
							name: 'folder_name',
							label: 'Name',
							defaultValue: f.folder_name,
							required: true,
						},
					],
					confirmLabel: 'Save',
					onConfirm: async ({ values }) => {
						await call(`${API}.rename_folder`, {
							folder: f.name,
							folder_name: values.folder_name,
						})
						f.folder_name = values.folder_name
					},
				}),
		},
		{
			label: 'Delete folder',
			icon: 'lucide-trash-2',
			theme: 'red',
			onClick: () =>
				dialog.danger({
					title: 'Delete folder?',
					message: 'The recordings inside are kept and moved out of the folder.',
					onConfirm: async () => {
						await call(`${API}.delete_folder`, { folder: f.name })
						folder.value = null
						await loadFolders()
					},
				}),
		},
	]
}
</script>

<style scoped>
.chip {
	@apply flex h-7 items-center gap-1.5 rounded-full border border-outline-gray-2 bg-surface-base px-3 text-sm text-ink-gray-7 transition-colors hover:bg-surface-gray-2;
}
.chip-active {
	@apply border-outline-gray-5 bg-surface-gray-2 font-medium text-ink-gray-9;
}
</style>
