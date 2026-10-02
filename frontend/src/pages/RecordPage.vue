<template>
	<div class="min-h-screen bg-surface-gray-1">
		<AppHeader :show-record-button="false" />

		<main class="mx-auto grid max-w-6xl gap-6 px-4 py-6 lg:grid-cols-[1fr_340px]">
			<!-- Stage -->
			<section>
				<div
					class="relative aspect-video overflow-hidden rounded-6 bg-surface-gray-9 shadow-sm"
				>
					<VideoStream
						v-if="recorder.screenStream.value"
						:stream="recorder.screenStream.value"
						class="size-full object-contain"
					/>
					<VideoStream
						v-else-if="
							recorder.settings.mode === 'Camera' && recorder.cameraStream.value
						"
						:stream="recorder.cameraStream.value"
						mirror
						class="size-full object-cover"
					/>
					<div
						v-else-if="!['finishing', 'error'].includes(recorder.phase.value)"
						class="flex size-full flex-col items-center justify-center gap-3 text-center text-ink-gray-4"
					>
						<span
							:class="
								recorder.settings.mode === 'Camera'
									? 'lucide-video-off'
									: 'lucide-monitor'
							"
							class="size-10"
						/>
						<p class="max-w-xs text-sm">
							{{
								recorder.settings.mode === 'Camera'
									? 'Allow camera access to see yourself here.'
									: 'You will pick a screen, window or tab to share when you start recording.'
							}}
						</p>
					</div>

					<!-- camera bubble over the screen preview -->
					<div
						v-if="
							recorder.settings.mode === 'Screen + Camera' &&
							recorder.cameraStream.value
						"
						class="absolute bottom-4 left-4 aspect-square w-[22%] min-w-24 overflow-hidden rounded-full border-4 border-white/80 shadow-xl"
					>
						<VideoStream
							:stream="recorder.cameraStream.value"
							mirror
							class="size-full object-cover"
						/>
					</div>

					<div
						v-if="recorder.phase.value === 'countdown'"
						class="absolute inset-0 flex cursor-pointer flex-col items-center justify-center gap-2 bg-black/60 text-white"
						@click="recorder.skipCountdown()"
					>
						<span class="text-8xl font-semibold tabular-nums">{{
							recorder.countdownValue.value
						}}</span>
						<span class="text-sm text-white/70">Click to skip</span>
					</div>

					<div
						v-if="recorder.phase.value === 'finishing'"
						class="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-surface-gray-9 text-white"
					>
						<LoadingIndicator class="size-8" />
						<p class="text-sm">Finishing up… {{ uploadPercent }}%</p>
					</div>

					<div
						v-if="recorder.phase.value === 'error'"
						class="absolute inset-0 flex flex-col items-center justify-center gap-4 bg-surface-gray-9 p-6 text-center text-white"
					>
						<span class="lucide-cloud-off size-10 text-ink-red-3" />
						<div>
							<p class="font-medium">We couldn't finish uploading your recording.</p>
							<p class="mt-1 text-sm text-white/70">{{ recorder.error.value }}</p>
						</div>
						<div class="flex flex-wrap justify-center gap-2">
							<Button
								variant="solid"
								label="Try again"
								icon-left="lucide-rotate-cw"
								@click="retry"
							/>
							<Button
								label="Download a copy"
								icon-left="lucide-download"
								@click="recorder.downloadLocalCopy()"
							/>
						</div>
					</div>

					<div
						v-if="recorder.isActive.value && recorder.phase.value !== 'countdown'"
						class="absolute left-4 top-4 flex items-center gap-2 rounded-full bg-black/60 px-3 py-1 text-sm font-medium tabular-nums text-white"
					>
						<span
							class="size-2 rounded-full"
							:class="
								recorder.phase.value === 'recording'
									? 'animate-pulse bg-surface-red-6'
									: 'bg-surface-gray-5'
							"
						/>
						{{ recorder.phase.value === 'paused' ? 'Paused · ' : ''
						}}{{ formatDuration(recorder.elapsedMs.value / 1000) }}
					</div>
				</div>

				<ErrorMessage
					v-if="recorder.error.value && recorder.phase.value !== 'error'"
					class="mt-3"
					:message="recorder.error.value"
				/>
				<p v-if="!supported" class="mt-3 text-sm text-ink-red-4">
					<template v-if="!secure">
						Recording needs a secure connection. Open this site over https:// to
						record.
					</template>
					<template v-else>
						This browser can't record the screen. Please use a recent version of
						Chrome, Edge, Firefox or Safari on a computer.
					</template>
				</p>
			</section>

			<!-- Controls -->
			<aside class="flex flex-col gap-4">
				<!-- Set-up -->
				<div
					v-if="!recorder.isBusy.value && recorder.phase.value !== 'error'"
					class="rounded-6 border border-outline-gray-2 bg-surface-base p-4"
				>
					<h1 class="text-lg font-semibold text-ink-gray-9">New recording</h1>

					<TextInput
						v-model="title"
						class="mt-4"
						label="Title"
						placeholder="Untitled recording"
					/>

					<div class="mt-4">
						<span class="mb-1.5 block text-xs text-ink-gray-5">Record</span>
						<div class="grid grid-cols-3 gap-1 rounded-4 bg-surface-gray-2 p-1">
							<button
								v-for="mode in MODES"
								:key="mode.value"
								class="flex flex-col items-center gap-1 rounded-3 px-1 py-2 text-xs font-medium transition-colors"
								:class="
									recorder.settings.mode === mode.value
										? 'bg-surface-base text-ink-gray-9 shadow-sm'
										: 'text-ink-gray-6 hover:text-ink-gray-8'
								"
								@click="recorder.settings.mode = mode.value"
							>
								<span :class="mode.icon" class="size-4" />
								{{ mode.label }}
							</button>
						</div>
					</div>

					<label v-if="recorder.usesCamera.value" class="mt-4 block">
						<span class="mb-1.5 block text-xs text-ink-gray-5">Camera</span>
						<select v-model="recorder.settings.cameraId" class="device-select">
							<option value="">Default camera</option>
							<option
								v-for="(device, i) in recorder.cameras.value"
								:key="device.deviceId"
								:value="device.deviceId"
							>
								{{ device.label || `Camera ${i + 1}` }}
							</option>
						</select>
					</label>

					<div class="mt-4">
						<div class="mb-1.5 flex items-center justify-between">
							<span class="text-xs text-ink-gray-5">Microphone</span>
							<AudioLevel
								v-if="recorder.settings.micEnabled"
								:stream="recorder.micStream.value"
							/>
						</div>
						<div class="flex items-center gap-2">
							<select
								v-model="recorder.settings.micId"
								class="device-select"
								:disabled="!recorder.settings.micEnabled"
							>
								<option value="">Default microphone</option>
								<option
									v-for="(device, i) in recorder.microphones.value"
									:key="device.deviceId"
									:value="device.deviceId"
								>
									{{ device.label || `Microphone ${i + 1}` }}
								</option>
							</select>
							<Button
								:icon="
									recorder.settings.micEnabled ? 'lucide-mic' : 'lucide-mic-off'
								"
								:tooltip="
									recorder.settings.micEnabled
										? 'Turn microphone off'
										: 'Turn microphone on'
								"
								:aria-label="
									recorder.settings.micEnabled
										? 'Turn microphone off'
										: 'Turn microphone on'
								"
								@click="
									recorder.settings.micEnabled = !recorder.settings.micEnabled
								"
							/>
						</div>
					</div>

					<div class="mt-4 flex flex-col gap-1">
						<Switch
							v-if="recorder.usesScreen.value"
							v-model="recorder.settings.systemAudio"
							label="Record computer audio"
							description="Sound from the tab or screen you share"
						/>
						<Switch v-model="recorder.settings.countdown" label="3-second countdown" />
					</div>

					<Button
						class="mt-5 w-full"
						size="lg"
						theme="red"
						variant="solid"
						icon-left="lucide-circle-dot"
						label="Start recording"
						:disabled="!supported"
						@click="startRecording"
					/>

					<p class="mt-3 text-center text-xs text-ink-gray-5">
						<template
							v-if="drive?.connected && drive?.folder_id && drive?.auto_upload"
						>
							<span class="lucide-hard-drive inline-block size-3 align-[-1px]" />
							Saving to Google Drive · {{ drive.folder_name }}
						</template>
						<template v-else-if="drive?.configured && !drive?.visitor">
							<router-link :to="{ name: 'Settings' }" class="underline"
								>Connect Google Drive</router-link
							>
							to keep a copy of every recording in your Drive.
						</template>
					</p>
					<p v-if="session.isGuest" class="mt-2 text-center text-xs text-ink-gray-5">
						No account needed. You can manage your recordings from this browser;
						<button class="underline" @click="redirectToLogin()">log in</button>
						to keep them with your account.
					</p>
				</div>

				<!-- While recording -->
				<div
					v-else-if="recorder.phase.value !== 'error'"
					class="rounded-6 border border-outline-gray-2 bg-surface-base p-4"
				>
					<p class="text-sm font-medium text-ink-gray-9">
						{{
							recorder.phase.value === 'starting'
								? 'Getting ready…'
								: recorder.phase.value === 'finishing'
								? 'Finishing up…'
								: 'Recording'
						}}
					</p>

					<div
						v-if="recorder.recording.value"
						class="mt-3 rounded-4 bg-surface-gray-2 p-3"
					>
						<p class="text-xs text-ink-gray-6">
							Your link is ready. Share it now; it plays as soon as you stop.
						</p>
						<div class="mt-2 flex items-center gap-2">
							<code class="min-w-0 flex-1 truncate text-xs text-ink-gray-8">{{
								recorder.recording.value.share_url
							}}</code>
							<Button
								size="sm"
								icon="lucide-copy"
								tooltip="Copy link"
								aria-label="Copy link"
								@click="copyLink"
							/>
						</div>
					</div>

					<div v-if="recorder.isActive.value" class="mt-4 grid grid-cols-4 gap-2">
						<Button
							v-if="recorder.phase.value === 'paused'"
							icon="lucide-play"
							tooltip="Resume"
							aria-label="Resume"
							size="lg"
							@click="recorder.resume()"
						/>
						<Button
							v-else
							icon="lucide-pause"
							tooltip="Pause"
							aria-label="Pause"
							size="lg"
							:disabled="recorder.phase.value !== 'recording'"
							@click="recorder.pause()"
						/>
						<Button
							:icon="recorder.micMuted.value ? 'lucide-mic-off' : 'lucide-mic'"
							:tooltip="recorder.micMuted.value ? 'Unmute' : 'Mute'"
							:aria-label="recorder.micMuted.value ? 'Unmute' : 'Mute'"
							size="lg"
							:disabled="!recorder.settings.micEnabled"
							@click="recorder.toggleMute()"
						/>
						<Button
							icon="lucide-rotate-ccw"
							tooltip="Start over"
							aria-label="Start over"
							size="lg"
							@click="restartRecording"
						/>
						<Button
							icon="lucide-trash-2"
							tooltip="Cancel recording"
							aria-label="Cancel recording"
							size="lg"
							@click="cancelRecording"
						/>
					</div>

					<Button
						v-if="recorder.isActive.value"
						class="mt-3 w-full"
						size="lg"
						theme="red"
						variant="solid"
						icon-left="lucide-square"
						label="Stop and share"
						@click="stopRecording"
					/>

					<Button
						v-if="canPopOut"
						class="mt-2 w-full"
						variant="ghost"
						icon-left="lucide-picture-in-picture-2"
						label="Show floating controls"
						@click="recorder.openFloatingControls()"
					/>
				</div>
			</aside>
		</main>

		<Teleport v-if="recorder.pipWindow.value" :to="recorder.pipWindow.value.document.body">
			<FloatingControls
				:phase="recorder.phase.value"
				:countdown-value="recorder.countdownValue.value"
				:elapsed-ms="recorder.elapsedMs.value"
				:mic-muted="recorder.micMuted.value"
				@stop="stopRecording"
				@pause="recorder.pause()"
				@resume="recorder.resume()"
				@mute="recorder.toggleMute()"
			/>
		</Teleport>
	</div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter, onBeforeRouteLeave } from 'vue-router'
import { Button, ErrorMessage, LoadingIndicator, Switch, TextInput, call, toast } from 'frappe-ui'

import AppHeader from '@/components/AppHeader.vue'
import AudioLevel from '@/components/AudioLevel.vue'
import FloatingControls from '@/components/FloatingControls.vue'
import VideoStream from '@/components/VideoStream.vue'
import { MODES, isRecordingSupported, useRecorder } from '@/composables/useRecorder'
import { copyToClipboard, formatDuration } from '@/utils/format'
import { redirectToLogin, session } from '@/session'

const route = useRoute()
const router = useRouter()
const recorder = useRecorder()
const supported = isRecordingSupported()
const secure = window.isSecureContext

const title = ref('')
const drive = ref(null)

const uploadPercent = computed(() => {
	const { sentBytes, totalBytes } = recorder.upload
	return totalBytes ? Math.min(100, Math.round((sentBytes / totalBytes) * 100)) : 0
})

const canPopOut = computed(
	() =>
		'documentPictureInPicture' in window &&
		recorder.usesScreen.value &&
		recorder.isActive.value &&
		!recorder.pipWindow.value
)

function defaultTitle() {
	const now = new Date()
	return `Recording · ${now.toLocaleDateString(undefined, {
		month: 'short',
		day: 'numeric',
	})}, ${now.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })}`
}

async function startRecording() {
	await recorder.start(title.value.trim() || defaultTitle(), route.query.folder || null)
}

async function stopRecording() {
	await recorder.stop()
}

async function retry() {
	await recorder.retryUpload()
}

async function restartRecording() {
	await recorder.restart(title.value.trim() || defaultTitle(), route.query.folder || null)
}

async function cancelRecording() {
	await recorder.cancel()
	toast.info('Recording discarded')
}

async function copyLink() {
	await copyToClipboard(recorder.recording.value.share_url)
	toast.success('Link copied')
}

// When the recording is finished (from the page, the floating controls or the
// browser's "Stop sharing" bar) take the person to the share page.
watch(recorder.phase, async (phase) => {
	if (phase !== 'done' || !recorder.recording.value) return
	const { share_id, share_url } = recorder.recording.value
	if (recorder.notice.value) toast.warning(recorder.notice.value, { duration: 10_000 })
	copyToClipboard(share_url)
		.then(() => toast.success('Recording ready. Link copied to clipboard'))
		.catch(() => {})
	router.push({ name: 'Watch', params: { shareId: share_id } })
})

function warnBeforeUnload(event) {
	if (recorder.isBusy.value || recorder.phase.value === 'error') {
		event.preventDefault()
		event.returnValue = ''
	}
}

onBeforeRouteLeave(() => {
	if (recorder.isBusy.value && recorder.phase.value !== 'done') {
		if (!window.confirm('Leave this page? Your recording will be lost.')) return false
		recorder.cancel()
	}
})

onMounted(async () => {
	window.addEventListener('beforeunload', warnBeforeUnload)
	if (supported) recorder.preparePreview()
	drive.value = await call('frappe_recorder.api.drive.get_status').catch(() => null)
})

onBeforeUnmount(() => {
	window.removeEventListener('beforeunload', warnBeforeUnload)
	recorder.dispose()
})
</script>

<style scoped>
.device-select {
	@apply h-7 w-full min-w-0 rounded-1 border-0 bg-surface-gray-2 py-0 pl-2 pr-7 text-base text-ink-gray-8 focus:ring-2 focus:ring-outline-gray-3 disabled:opacity-60;
}
</style>
