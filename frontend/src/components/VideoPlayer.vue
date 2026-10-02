<template>
  <video
    ref="el"
    :src="src"
    :poster="poster || undefined"
    controls
    playsinline
    preload="metadata"
    class="aspect-video w-full rounded-xl bg-black"
    @loadedmetadata="fixDuration"
    @play="$emit('play')"
    @timeupdate="$emit('timeupdate', $event.target.currentTime)"
  />
</template>

<script setup>
import { ref } from 'vue'

defineProps({ src: { type: String, required: true }, poster: { type: String, default: '' } })
defineEmits(['play', 'timeupdate'])

const el = ref(null)

/** Jumps to a moment (from the transcript, highlights or SOP) and plays from there. */
function seek(seconds) {
  const video = el.value
  if (!video) return
  video.currentTime = seconds
  video.play().catch(() => {})
  video.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
}

defineExpose({ seek })

// Browser-recorded WebM files carry no duration, so the player reports Infinity
// and the seek bar is unusable. Seeking far past the end makes the browser work
// out the real length; then we return to the start.
function fixDuration() {
  const video = el.value
  if (!video || Number.isFinite(video.duration)) return
  const restore = () => {
    if (!Number.isFinite(video.duration)) return
    video.removeEventListener('durationchange', restore)
    video.currentTime = 0
  }
  video.addEventListener('durationchange', restore)
  video.currentTime = Number.MAX_SAFE_INTEGER
}
</script>
