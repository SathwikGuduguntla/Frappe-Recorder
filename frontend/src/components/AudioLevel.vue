<template>
	<div class="flex h-4 items-end gap-0.5" aria-hidden="true">
		<span
			v-for="i in bars"
			:key="i"
			class="w-1 rounded-full transition-[height] duration-75"
			:class="level * bars >= i ? 'bg-surface-green-6' : 'bg-surface-gray-3'"
			:style="{ height: `${30 + (i / bars) * 70}%` }"
		/>
	</div>
</template>

<script setup>
import { onBeforeUnmount, ref, watch } from 'vue'

const props = defineProps({ stream: { type: Object, default: null } })
const bars = 8
const level = ref(0)

let context = null
let frame = null

function stop() {
	cancelAnimationFrame(frame)
	context?.close().catch(() => {})
	context = null
	level.value = 0
}

function start(stream) {
	stop()
	if (!stream?.getAudioTracks().length) return
	context = new AudioContext()
	const analyser = context.createAnalyser()
	analyser.fftSize = 256
	context.createMediaStreamSource(stream).connect(analyser)
	const data = new Uint8Array(analyser.frequencyBinCount)
	const loop = () => {
		analyser.getByteTimeDomainData(data)
		let peak = 0
		for (const value of data) peak = Math.max(peak, Math.abs(value - 128))
		level.value = Math.min(1, (peak / 128) * 2.5)
		frame = requestAnimationFrame(loop)
	}
	loop()
}

watch(() => props.stream, start, { immediate: true })
onBeforeUnmount(stop)
</script>
