<template>
  <div class="mx-auto max-w-6xl px-4 py-8 sm:px-6">
    <div class="flex flex-wrap items-center gap-3">
      <h1 class="mr-auto text-2xl font-semibold text-ink-gray-9">Library</h1>
      <input
        v-model="search"
        type="search"
        placeholder="Search recordings"
        aria-label="Search recordings"
        class="form-input w-56 rounded-md border-outline-gray-2 bg-surface-base py-1.5 text-base placeholder:text-ink-gray-4"
      />
      <Button variant="solid" icon-left="lucide-plus" label="New recording" :route="{ name: 'Record' }" />
    </div>

    <div v-if="loading" class="flex justify-center py-24">
      <LoadingIndicator class="size-6 text-ink-gray-5" />
    </div>

    <p v-else-if="loadError" role="alert" class="mt-8 rounded-md bg-surface-red-2 px-3 py-2 text-base text-ink-red-7">
      {{ loadError }}
    </p>

    <div v-else-if="!recordings.length" class="mt-8 rounded-xl border border-dashed border-outline-gray-3 px-6 py-20 text-center">
      <p class="text-lg font-medium text-ink-gray-9">{{ search ? 'No recordings match your search' : 'No recordings yet' }}</p>
      <p v-if="!search" class="mt-1 text-base text-ink-gray-6">Videos you record show up here with their share links.</p>
      <Button v-if="!search" class="mt-5" variant="solid" label="Record your first video" :route="{ name: 'Record' }" />
    </div>

    <ul v-else class="mt-6 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
      <li
        v-for="item in recordings"
        :key="item.token"
        class="group overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base transition hover:shadow-md"
      >
        <router-link :to="{ name: 'Watch', params: { token: item.token } }" class="relative block aspect-video bg-surface-gray-10">
          <img v-if="item.thumbnail" :src="item.thumbnail" alt="" loading="lazy" class="h-full w-full object-cover" />
          <span v-else class="absolute inset-0 flex items-center justify-center">
            <span class="lucide-film size-8 text-ink-gray-5" aria-hidden="true" />
          </span>
          <span v-if="item.duration_seconds" class="absolute bottom-2 right-2 rounded bg-black/75 px-1.5 py-0.5 text-xs font-medium tabular-nums text-white">
            {{ formatDuration(item.duration_seconds) }}
          </span>
          <span v-if="!item.is_public" class="absolute left-2 top-2 flex items-center gap-1 rounded bg-black/75 px-1.5 py-0.5 text-xs font-medium text-white">
            <span class="lucide-lock size-3" aria-hidden="true" /> Private
          </span>
        </router-link>

        <div class="p-3.5">
          <router-link :to="{ name: 'Watch', params: { token: item.token } }" class="block truncate text-base font-medium text-ink-gray-9 hover:underline">
            {{ item.title }}
          </router-link>
          <p class="mt-1 text-sm text-ink-gray-5">
            {{ formatDate(item.creation) }} · {{ item.view_count }} {{ item.view_count === 1 ? 'view' : 'views' }}
          </p>
          <div class="mt-3 flex items-center gap-1">
            <span class="ml-auto" />
            <Button variant="ghost" icon="lucide-link" tooltip="Copy link" aria-label="Copy link" @click="copyLink(item)" />
            <Button variant="ghost" icon="lucide-trash-2" tooltip="Delete" aria-label="Delete" @click="confirmDelete(item)" />
          </div>
        </div>
      </li>
    </ul>
  </div>
</template>

<script setup>
import { onBeforeUnmount, ref, watch } from 'vue'
import { Button, LoadingIndicator, dialog, toast } from 'frappe-ui'
import { api, copyText, errorMessage, formatDate, formatDuration } from '@/api'

const recordings = ref([])
const loading = ref(true)
const loadError = ref('')
const search = ref('')

let requestId = 0
async function load() {
  const id = ++requestId
  try {
    const data = await api.listRecordings(search.value.trim())
    if (id !== requestId) return // a newer search already replaced this one
    recordings.value = data
    loadError.value = ''
  } catch (e) {
    if (id === requestId) loadError.value = errorMessage(e)
  } finally {
    if (id === requestId) loading.value = false
  }
}

let searchTimer = null
watch(search, () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(load, 250)
})
onBeforeUnmount(() => clearTimeout(searchTimer))

async function copyLink(item) {
  if (await copyText(item.share_url)) toast.success('Link copied')
  else toast.error('Could not copy the link')
}

function confirmDelete(item) {
  dialog.danger({
    title: `Delete “${item.title}”?`,
    message: 'The share link will stop working and the video cannot be recovered.',
    onConfirm: async () => {
      await api.deleteRecording(item.token)
      recordings.value = recordings.value.filter((r) => r.token !== item.token)
    },
  })
}

load()
</script>
