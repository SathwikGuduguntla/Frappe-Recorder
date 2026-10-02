<template>
	<div class="min-h-screen bg-surface-gray-1">
		<AppHeader />

		<main class="mx-auto max-w-2xl px-4 py-6">
			<h1 class="text-xl font-semibold text-ink-gray-9">Settings</h1>

			<section class="mt-6 rounded-6 border border-outline-gray-2 bg-surface-base">
				<div class="flex items-start gap-3 border-b border-outline-gray-1 p-4">
					<span class="lucide-hard-drive mt-0.5 size-5 text-ink-gray-6" />
					<div>
						<h2 class="font-medium text-ink-gray-9">Google Drive storage</h2>
						<p class="mt-0.5 text-sm text-ink-gray-6">
							Save every recording to a folder in your Google Drive. Shared links
							keep working, and play from Drive if the copy on this site is removed.
						</p>
					</div>
				</div>

				<div v-if="!status" class="flex justify-center p-8">
					<LoadingIndicator class="size-5 text-ink-gray-5" />
				</div>

				<!-- Not set up by an administrator yet -->
				<div v-else-if="!status.configured" class="p-4 text-sm text-ink-gray-7">
					<p>Google Drive isn't set up on this site yet.</p>
					<template v-if="status.can_configure">
						<ol class="mt-3 list-decimal space-y-1.5 pl-5">
							<li>
								In
								<a
									class="underline"
									href="https://console.cloud.google.com/apis/credentials"
									target="_blank"
									>Google Cloud Console</a
								>, enable the Google Drive API and create an OAuth client of type
								<em>Web application</em>.
							</li>
							<li>
								Add this as an authorized redirect URI:
								<div class="mt-1 flex items-center gap-2">
									<code
										class="min-w-0 flex-1 truncate rounded-1 bg-surface-gray-2 px-2 py-1 text-xs"
										>{{ status.redirect_uri }}</code
									>
									<Button
										size="sm"
										icon="lucide-copy"
										tooltip="Copy"
										aria-label="Copy"
										@click="copy(status.redirect_uri)"
									/>
								</div>
							</li>
							<li>
								Paste the client ID and secret into Google Drive Settings and tick
								<em>Enable</em>.
							</li>
						</ol>
						<Button
							class="mt-4"
							label="Open Google Drive Settings"
							icon-right="lucide-arrow-up-right"
							href="/app/google-drive-settings"
						/>
					</template>
					<p v-else class="mt-1 text-ink-gray-5">
						Ask your administrator to fill in Google Drive Settings.
					</p>
				</div>

				<!-- Configured, not connected -->
				<div v-else-if="!status.connected" class="flex flex-wrap items-center gap-3 p-4">
					<p class="flex-1 text-sm text-ink-gray-7">
						Connect your Google account to choose where recordings go.
					</p>
					<Button
						variant="solid"
						label="Connect Google Drive"
						icon-left="lucide-plug"
						:loading="connecting"
						@click="connect"
					/>
				</div>

				<!-- Connected -->
				<div v-else class="divide-y divide-outline-gray-1">
					<div class="flex flex-wrap items-center gap-3 p-4">
						<span class="size-2 rounded-full bg-surface-green-6" />
						<p class="flex-1 text-sm text-ink-gray-7">
							Connected as
							<span class="font-medium text-ink-gray-9">{{
								status.google_email || 'your Google account'
							}}</span>
						</p>
						<Button
							label="Disconnect"
							variant="ghost"
							theme="red"
							@click="disconnect"
						/>
					</div>

					<form class="p-4" @submit.prevent="saveFolder">
						<TextInput
							v-model="folderLink"
							label="Drive folder link"
							placeholder="https://drive.google.com/drive/folders/…"
							description="Open the folder in Google Drive and paste its link from the address bar or the Share dialog."
						/>
						<div class="mt-3 flex flex-wrap items-center gap-3">
							<p
								v-if="status.folder_id"
								class="flex min-w-0 flex-1 items-center gap-1.5 text-sm text-ink-gray-7"
							>
								<span class="lucide-folder-check size-4 text-ink-green-4" />
								Saving to
								<a
									class="truncate font-medium text-ink-gray-9 underline"
									:href="`https://drive.google.com/drive/folders/${status.folder_id}`"
									target="_blank"
								>
									{{ status.folder_name }}
								</a>
							</p>
							<p v-else class="flex-1 text-sm text-ink-amber-4">
								No folder chosen yet.
							</p>
							<Button
								type="submit"
								variant="solid"
								label="Save folder"
								:loading="savingFolder"
								:disabled="folderLink.trim() === (status.folder_link || '')"
							/>
						</div>
						<ErrorMessage class="mt-2" :message="folderError" />
					</form>

					<div class="flex flex-col gap-1 p-4">
						<Switch
							:model-value="Boolean(status.auto_upload)"
							label="Upload new recordings automatically"
							description="Each recording is copied to your Drive folder as soon as it finishes."
							@update:model-value="(v) => savePreference('auto_upload', v)"
						/>
						<Switch
							:model-value="Boolean(status.share_on_drive)"
							label="Let anyone with the link watch the Drive copy"
							description="Needed for viewers to play videos from Drive. Turn off if your organisation forbids public links."
							@update:model-value="(v) => savePreference('share_on_drive', v)"
						/>
						<Switch
							:model-value="Boolean(status.keep_local_copy)"
							label="Also keep a copy on this site"
							description="When off, the video is removed from this site after it is safely in Drive, and played from Drive."
							@update:model-value="(v) => savePreference('keep_local_copy', v)"
						/>
					</div>
				</div>
			</section>
		</main>
	</div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
	Button,
	ErrorMessage,
	LoadingIndicator,
	Switch,
	TextInput,
	call,
	dialog,
	toast,
} from 'frappe-ui'

import AppHeader from '@/components/AppHeader.vue'
import { copyToClipboard, errorMessage } from '@/utils/format'

const DRIVE = 'frappe_recorder.api.drive'

const route = useRoute()
const router = useRouter()
const status = ref(null)
const folderLink = ref('')
const folderError = ref('')
const savingFolder = ref(false)
const connecting = ref(false)

function setStatus(data) {
	status.value = data
	folderLink.value = data.folder_link || ''
}

onMounted(async () => {
	setStatus(await call(`${DRIVE}.get_status`))
	if (route.query.drive === 'connected')
		toast.success('Google Drive connected. Now paste a folder link.')
	if (route.query.drive === 'error')
		toast.error('Could not connect Google Drive. Please try again.')
	if (route.query.drive) router.replace({ query: {} })
})

async function connect() {
	connecting.value = true
	try {
		window.location.href = await call(`${DRIVE}.get_authorize_url`)
	} catch (e) {
		toast.error(errorMessage(e))
		connecting.value = false
	}
}

function disconnect() {
	dialog.confirm({
		title: 'Disconnect Google Drive?',
		message:
			'New recordings will no longer be saved to Drive. Videos already in Drive stay there.',
		confirmLabel: 'Disconnect',
		theme: 'red',
		onConfirm: async () => setStatus(await call(`${DRIVE}.disconnect`)),
	})
}

async function saveFolder() {
	savingFolder.value = true
	folderError.value = ''
	try {
		setStatus(await call(`${DRIVE}.save_folder`, { folder_link: folderLink.value }))
		toast.success(
			status.value.folder_id
				? `Recordings will be saved to ${status.value.folder_name}`
				: 'Folder removed'
		)
	} catch (e) {
		folderError.value = errorMessage(e)
	} finally {
		savingFolder.value = false
	}
}

async function savePreference(field, value) {
	status.value[field] = value ? 1 : 0
	try {
		setStatus(await call(`${DRIVE}.update_preferences`, { [field]: value ? 1 : 0 }))
	} catch (e) {
		toast.error(errorMessage(e))
	}
}

async function copy(text) {
	await copyToClipboard(text)
	toast.success('Copied')
}
</script>
