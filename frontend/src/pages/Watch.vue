<template>
  <div class="mx-auto max-w-5xl px-4 py-6 sm:px-6 sm:py-8">
    <div v-if="loading" class="flex justify-center py-24">
      <LoadingIndicator class="size-6 text-ink-gray-5" />
    </div>

    <div v-else-if="loadError" class="mx-auto max-w-md py-20 text-center">
      <p class="text-xl font-semibold text-ink-gray-9">This video is not available</p>
      <p class="mt-2 text-base text-ink-gray-6">{{ loadError }}</p>
      <Button class="mt-6" variant="solid" label="Record your own video" :route="{ name: 'Record' }" />
    </div>

    <template v-else>
      <div
        v-if="isNew"
        class="mb-4 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg bg-surface-green-2 px-4 py-3 text-base text-ink-green-8"
        role="status"
      >
        <span class="lucide-circle-check size-4" aria-hidden="true" />
        <span class="font-medium">Your recording is ready.</span>
        <span>{{ copied ? 'The link is on your clipboard.' : 'Copy the link to share it.' }}</span>
      </div>

      <div v-if="recording.status !== 'Ready'" class="flex aspect-video flex-col items-center justify-center rounded-xl bg-surface-gray-10 text-center">
        <p class="text-lg font-medium text-white">
          {{ recording.status === 'Failed' ? 'This recording failed to save' : 'This video is still being recorded' }}
        </p>
        <p v-if="recording.status !== 'Failed'" class="mt-1 text-base text-ink-gray-4">Check back in a moment.</p>
      </div>
      <VideoPlayer
        v-else
        ref="player"
        :src="recording.stream_url"
        :poster="recording.thumbnail"
        @play="countView"
        @timeupdate="(t) => (currentTime = t)"
      />

      <div class="mt-5 flex flex-col gap-6 lg:flex-row lg:items-start">
        <div class="min-w-0 flex-1">
          <input
            v-if="recording.is_owner"
            v-model="title"
            aria-label="Title"
            maxlength="140"
            class="-mx-2 w-full rounded-md border-0 bg-transparent px-2 py-1 text-2xl font-semibold text-ink-gray-9 hover:bg-surface-gray-2 focus:bg-surface-base focus:ring-2 focus:ring-outline-gray-3"
            @keydown.enter="$event.target.blur()"
            @blur="saveTitle"
          />
          <h1 v-else class="text-2xl font-semibold text-ink-gray-9">{{ recording.title }}</h1>

          <p class="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-base text-ink-gray-5">
            <span>{{ formatDate(recording.creation) }}</span>
            <span aria-hidden="true">·</span>
            <span>{{ formatDuration(recording.duration_seconds) }}</span>
            <span aria-hidden="true">·</span>
            <span>{{ recording.view_count }} {{ recording.view_count === 1 ? 'view' : 'views' }}</span>
            <template v-if="recording.is_owner && recording.file_size">
              <span aria-hidden="true">·</span>
              <span>{{ formatSize(recording.file_size) }}</span>
            </template>
          </p>

          <AiPanel :recording="recording" :current-time="currentTime" @seek="(t) => player?.seek(t)" />
        </div>

        <!-- Owner tools -->
        <aside v-if="recording.is_owner" class="w-full shrink-0 rounded-xl border border-outline-gray-2 bg-surface-base p-4 lg:w-96">
          <label for="share-link" class="text-sm font-medium text-ink-gray-7">Share link</label>
          <div class="mt-1.5 flex gap-2">
            <input
              id="share-link"
              :value="recording.share_url"
              readonly
              class="form-input min-w-0 flex-1 rounded-md border-outline-gray-2 bg-surface-gray-2 py-1.5 text-base text-ink-gray-8"
              @focus="$event.target.select()"
            />
            <Button variant="solid" :icon-left="copied ? 'lucide-check' : 'lucide-copy'" :label="copied ? 'Copied' : 'Copy'" @click="copyLink" />
          </div>

          <div class="mt-4 flex items-center justify-between gap-3">
            <div>
              <p class="text-base text-ink-gray-8">Anyone with the link can view</p>
              <p class="text-sm text-ink-gray-5">{{ recording.is_public ? 'No sign-in needed.' : 'Only you can open this video.' }}</p>
            </div>
            <Switch :model-value="!!recording.is_public" aria-label="Anyone with the link can view" @update:model-value="setPublic" />
          </div>

          <div class="mt-4 flex gap-2 border-t border-outline-gray-1 pt-4">
            <Button class="flex-1" icon-left="lucide-download" label="Download" :href="recording.stream_url + '&download=1'" />
            <Button class="flex-1" theme="red" icon-left="lucide-trash-2" label="Delete" @click="confirmDelete" />
          </div>
        </aside>

        <Button v-else variant="subtle" icon-left="lucide-video" label="Record your own video" :route="{ name: 'Record' }" />
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Button, LoadingIndicator, Switch, dialog, toast } from 'frappe-ui'
import { api, copyText, errorMessage, formatDate, formatDuration, formatSize } from '@/api'
import AiPanel from '@/components/AiPanel.vue'
import VideoPlayer from '@/components/VideoPlayer.vue'

const route = useRoute()
const router = useRouter()
const token = route.params.token
const isNew = !!route.query.new

const loading = ref(true)
const loadError = ref('')
const recording = ref(null)
const title = ref('')
const copied = ref(false)
const player = ref(null)
const currentTime = ref(0)

let viewCounted = false

async function load() {
  try {
    recording.value = await api.getRecording(token)
    title.value = recording.value.title
    document.title = `${recording.value.title} · Recorder`
    if (isNew && recording.value.is_owner) {
      // Works when the click that stopped the recording is still "fresh" for the browser.
      copied.value = await copyText(recording.value.share_url)
      router.replace({ name: 'Watch', params: { token } })
    }
  } catch (e) {
    loadError.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}

async function countView() {
  if (viewCounted || recording.value.is_owner) return
  viewCounted = true
  try {
    const result = await api.registerView(token)
    recording.value.view_count = result.view_count
  } catch (e) {
    /* a missed view count is not worth interrupting playback */
  }
}

async function copyLink() {
  copied.value = await copyText(recording.value.share_url)
  if (copied.value) setTimeout(() => (copied.value = false), 2500)
  else toast.error('Could not copy. Select the link and copy it manually.')
}

async function saveTitle() {
  const next = title.value.trim()
  if (!next) {
    title.value = recording.value.title
    return
  }
  if (next === recording.value.title) return
  try {
    Object.assign(recording.value, await api.updateRecording(token, { title: next }))
    document.title = `${recording.value.title} · Recorder`
  } catch (e) {
    title.value = recording.value.title
    toast.error(errorMessage(e))
  }
}

async function setPublic(value) {
  try {
    Object.assign(recording.value, await api.updateRecording(token, { is_public: value ? 1 : 0 }))
  } catch (e) {
    toast.error(errorMessage(e))
  }
}

function confirmDelete() {
  dialog.danger({
    title: 'Delete this recording?',
    message: 'The share link will stop working and the video cannot be recovered.',
    onConfirm: async () => {
      await api.deleteRecording(token)
      router.push({ name: 'Library' })
    },
  })
}

load()
</script>
