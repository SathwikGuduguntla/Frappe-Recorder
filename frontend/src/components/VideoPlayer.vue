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
  />
</template>

<script setup>
import { ref } from 'vue'

defineProps({ src: { type: String, required: true }, poster: { type: String, default: '' } })
defineEmits(['play'])

const el = ref(null)

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
