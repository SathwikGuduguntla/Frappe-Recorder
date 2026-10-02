<template>
  <span
    v-if="label"
    class="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium"
    :class="tone"
  >
    <span :class="icon" class="size-3" aria-hidden="true" />
    {{ label }}
  </span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({ status: { type: String, default: '' } })

const config = {
  Synced: ['In Drive', 'lucide-cloud-check', 'bg-surface-green-2 text-ink-green-8'],
  Pending: ['Uploading to Drive', 'lucide-cloud-upload', 'bg-surface-blue-2 text-ink-blue-7'],
  Failed: ['Drive upload failed', 'lucide-cloud-alert', 'bg-surface-red-2 text-ink-red-7'],
}
const label = computed(() => config[props.status]?.[0])
const icon = computed(() => config[props.status]?.[1])
const tone = computed(() => config[props.status]?.[2])
</script>
