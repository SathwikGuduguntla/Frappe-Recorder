<template>
	<span v-if="info" class="flex items-center gap-1" :class="info.class" :title="info.title">
		<span :class="info.icon" class="size-3" />
		{{ info.label }}
	</span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({ status: { type: String, default: '' } })

const STATES = {
	Queued: {
		label: 'Drive',
		icon: 'lucide-clock',
		class: 'text-ink-gray-5',
		title: 'Waiting to upload to Google Drive',
	},
	Uploading: {
		label: 'Uploading',
		icon: 'lucide-upload-cloud',
		class: 'text-ink-blue-4',
		title: 'Uploading to Google Drive',
	},
	Synced: {
		label: 'Drive',
		icon: 'lucide-hard-drive',
		class: 'text-ink-green-4',
		title: 'Saved in Google Drive',
	},
	Failed: {
		label: 'Drive failed',
		icon: 'lucide-alert-triangle',
		class: 'text-ink-red-4',
		title: 'Upload to Google Drive failed',
	},
}

const info = computed(() => STATES[props.status])
</script>
