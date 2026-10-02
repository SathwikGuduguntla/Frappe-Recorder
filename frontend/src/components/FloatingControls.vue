<template>
	<!-- Rendered inside the Document Picture-in-Picture window (see useRecorder) -->
	<div
		class="flex h-screen w-screen flex-col items-center justify-center gap-3 bg-surface-base p-3"
	>
		<div
			v-if="cameraStream"
			class="relative aspect-square w-full max-w-[200px] overflow-hidden rounded-full border-4 border-outline-gray-2 bg-surface-gray-9 shadow-lg"
		>
			<VideoStream :stream="cameraStream" mirror class="size-full object-cover" />
			<div
				v-if="phase === 'countdown'"
				class="absolute inset-0 flex items-center justify-center bg-black/50 text-5xl font-semibold text-white"
			>
				{{ countdownValue }}
			</div>
		</div>

		<div class="flex w-full items-center justify-center gap-2">
			<span
				v-if="!cameraStream && phase === 'countdown'"
				class="text-2xl font-semibold tabular-nums text-ink-gray-9"
			>
				{{ countdownValue }}
			</span>
			<template v-else>
				<span
					class="flex items-center gap-1.5 text-sm font-medium tabular-nums text-ink-gray-8"
				>
					<span
						class="size-2 rounded-full"
						:class="
							phase === 'recording'
								? 'animate-pulse bg-surface-red-6'
								: 'bg-surface-gray-5'
						"
					/>
					{{ formatDuration(elapsedMs / 1000) }}
				</span>
			</template>
			<Button
				:icon="micMuted ? 'lucide-mic-off' : 'lucide-mic'"
				:tooltip="micMuted ? 'Unmute' : 'Mute'"
				:aria-label="micMuted ? 'Unmute' : 'Mute'"
				variant="subtle"
				@click="$emit('mute')"
			/>
			<Button
				v-if="phase === 'paused'"
				icon="lucide-play"
				tooltip="Resume"
				aria-label="Resume"
				variant="subtle"
				@click="$emit('resume')"
			/>
			<Button
				v-else
				icon="lucide-pause"
				tooltip="Pause"
				aria-label="Pause"
				variant="subtle"
				:disabled="phase !== 'recording'"
				@click="$emit('pause')"
			/>
			<Button
				icon="lucide-square"
				tooltip="Stop and share"
				aria-label="Stop and share"
				theme="red"
				variant="solid"
				@click="$emit('stop')"
			/>
		</div>
	</div>
</template>

<script setup>
import { Button } from 'frappe-ui'
import VideoStream from './VideoStream.vue'
import { formatDuration } from '@/utils/format'

defineProps({
	cameraStream: { type: Object, default: null },
	phase: { type: String, required: true },
	countdownValue: { type: Number, default: 0 },
	elapsedMs: { type: Number, default: 0 },
	micMuted: { type: Boolean, default: false },
})
defineEmits(['stop', 'pause', 'resume', 'mute'])
</script>
