<template>
	<video ref="video" autoplay muted playsinline :class="{ '-scale-x-100': mirror }" />
</template>

<script setup>
import { onMounted, ref, watch } from 'vue'

const props = defineProps({
	stream: { type: Object, default: null },
	mirror: { type: Boolean, default: false },
})

const video = ref(null)

function attach() {
	if (video.value && video.value.srcObject !== props.stream) {
		video.value.srcObject = props.stream || null
	}
}

onMounted(attach)
watch(() => props.stream, attach)

defineExpose({ video })
</script>
