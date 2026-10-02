<template>
	<div class="relative aspect-video w-full overflow-hidden rounded-6 bg-black">
		<video
			v-if="src"
			ref="video"
			:src="src"
			:poster="poster || undefined"
			controls
			playsinline
			preload="metadata"
			class="size-full"
			@loadedmetadata="fixDuration"
			@timeupdate="onTimeUpdate"
			@play="$emit('play')"
		/>
		<iframe
			v-else-if="driveFileId"
			:src="`https://drive.google.com/file/d/${driveFileId}/preview`"
			class="size-full"
			allow="autoplay; fullscreen"
			allowfullscreen
		/>
		<div
			v-else
			class="flex size-full flex-col items-center justify-center gap-2 text-ink-gray-4"
		>
			<span class="lucide-video-off size-8" />
			<p class="text-sm">{{ placeholder }}</p>
		</div>
	</div>
</template>

<script setup>
import { ref } from 'vue'

defineProps({
	src: { type: String, default: null },
	poster: { type: String, default: null },
	driveFileId: { type: String, default: null },
	placeholder: { type: String, default: 'Video is not available' },
})
const emit = defineEmits(['timeupdate', 'play'])

const video = ref(null)
let fixingDuration = false

// Recordings straight from MediaRecorder have no duration in their header until
// the server re-muxes them. Seeking to the far end makes the browser scan the
// file and work it out, after which the scrubber works normally.
function fixDuration() {
	const el = video.value
	if (!el || Number.isFinite(el.duration)) return
	fixingDuration = true
	el.currentTime = 1e101
}

function onTimeUpdate() {
	const el = video.value
	if (fixingDuration) {
		fixingDuration = false
		el.currentTime = 0
		return
	}
	emit('timeupdate', el.currentTime)
}

function seek(seconds) {
	if (!video.value) return
	video.value.currentTime = seconds
	video.value.play()
}

function currentTime() {
	return video.value?.currentTime || 0
}

defineExpose({ seek, currentTime })
</script>
