<template>
  <div class="mx-auto max-w-3xl px-4 py-8 sm:px-6 sm:py-12">
    <!-- Not supported -->
    <div v-if="!supported" class="rounded-xl border border-outline-gray-2 bg-surface-base p-8 text-center">
      <p class="text-lg font-semibold text-ink-gray-9">This browser cannot record video</p>
      <p class="mt-2 text-base text-ink-gray-6">Open this page in a recent version of Chrome, Edge or Firefox on a computer.</p>
    </div>

    <!-- Setup -->
    <template v-else-if="phase === 'idle' || phase === 'countdown'">
      <div class="text-center">
        <h1 class="text-[28px] font-semibold leading-tight tracking-tight text-ink-gray-9">Record a video</h1>
        <p class="mt-2 text-base text-ink-gray-6">
          Capture your screen, your camera, or both. You get a link to share the moment you stop.
        </p>
      </div>

      <div class="mt-8 rounded-xl border border-outline-gray-2 bg-surface-base p-5 shadow-sm sm:p-6">
        <div class="grid grid-cols-3 gap-2" role="radiogroup" aria-label="What to record">
          <button
            v-for="mode in modes"
            :key="mode.value"
            type="button"
            role="radio"
            :aria-checked="options.mode === mode.value"
            :disabled="mode.screen && !screenSupported"
            class="flex flex-col items-center gap-2 rounded-lg border px-2 py-4 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-40"
            :class="
              options.mode === mode.value
                ? 'border-outline-gray-5 bg-surface-gray-2 text-ink-gray-9'
                : 'border-outline-gray-2 text-ink-gray-6 hover:bg-surface-gray-1'
            "
            @click="options.mode = mode.value"
          >
            <span :class="mode.icon" class="size-5" aria-hidden="true" />
            {{ mode.label }}
          </button>
        </div>

        <!-- Camera preview -->
        <div
          v-if="currentMode.camera"
          class="relative mt-5 flex aspect-video items-center justify-center overflow-hidden rounded-lg bg-surface-gray-10"
        >
          <video
            v-show="cameraStream"
            ref="previewEl"
            autoplay
            muted
            playsinline
            class="h-full w-full -scale-x-100 object-cover"
            :class="{ '!h-40 !w-40 rounded-full ring-2 ring-white/90': currentMode.screen }"
          />
          <p v-if="!cameraStream" class="px-6 text-center text-sm text-ink-gray-4">
            Allow camera access to see yourself here.
          </p>
          <p
            v-else-if="currentMode.screen"
            class="absolute bottom-3 left-0 right-0 text-center text-sm text-ink-gray-4"
          >
            Your camera appears as a bubble in the corner of the recording.
          </p>
        </div>

        <div class="mt-5 space-y-3">
          <div v-if="currentMode.camera" class="flex items-center gap-3">
            <span class="lucide-video size-4 shrink-0 text-ink-gray-5" aria-hidden="true" />
            <label for="camera" class="w-28 shrink-0 text-base text-ink-gray-8">Camera</label>
            <select id="camera" v-model="options.cameraId" class="form-select min-w-0 flex-1 rounded-md border-outline-gray-2 bg-surface-gray-2 py-1.5 text-base">
              <option value="">Default camera</option>
              <option v-for="(d, i) in devices.cameras" :key="d.deviceId" :value="d.deviceId">
                {{ d.label || `Camera ${i + 1}` }}
              </option>
            </select>
          </div>

          <div class="flex items-center gap-3">
            <span class="lucide-mic size-4 shrink-0 text-ink-gray-5" aria-hidden="true" />
            <label for="mic" class="w-28 shrink-0 text-base text-ink-gray-8">Microphone</label>
            <select
              id="mic"
              v-model="options.micId"
              :disabled="!options.micEnabled"
              class="form-select min-w-0 flex-1 rounded-md border-outline-gray-2 bg-surface-gray-2 py-1.5 text-base disabled:opacity-50"
            >
              <option value="">Default microphone</option>
              <option v-for="(d, i) in devices.mics" :key="d.deviceId" :value="d.deviceId">
                {{ d.label || `Microphone ${i + 1}` }}
              </option>
            </select>
            <Switch v-model="options.micEnabled" aria-label="Record microphone" />
          </div>

          <div v-if="currentMode.screen" class="flex items-center gap-3">
            <span class="lucide-volume-2 size-4 shrink-0 text-ink-gray-5" aria-hidden="true" />
            <div class="min-w-0 flex-1">
              <p class="text-base text-ink-gray-8">System audio</p>
              <p class="text-sm text-ink-gray-5">Tick “Share audio” in the browser’s screen picker to include it.</p>
            </div>
            <Switch v-model="options.systemAudio" aria-label="Record system audio" />
          </div>

          <div class="flex items-center gap-3">
            <span class="lucide-type size-4 shrink-0 text-ink-gray-5" aria-hidden="true" />
            <label for="title" class="w-28 shrink-0 text-base text-ink-gray-8">Title</label>
            <input
              id="title"
              v-model="title"
              type="text"
              maxlength="140"
              placeholder="Optional. You can name it later."
              class="form-input min-w-0 flex-1 rounded-md border-outline-gray-2 bg-surface-gray-2 py-1.5 text-base placeholder:text-ink-gray-4"
            />
          </div>
        </div>

        <p v-if="error" role="alert" class="mt-4 rounded-md bg-surface-red-2 px-3 py-2 text-base text-ink-red-7">
          {{ error }}
        </p>

        <button
          type="button"
          class="mt-6 flex w-full items-center justify-center gap-2.5 rounded-lg bg-surface-red-6 px-4 py-3 text-lg font-medium text-white transition hover:bg-surface-red-7 disabled:opacity-60"
          :disabled="phase !== 'idle'"
          @click="start(title)"
        >
          <span class="size-3 rounded-full bg-white" aria-hidden="true" />
          Start recording
        </button>
        <p v-if="session.drive_active" class="mt-3 flex items-center justify-center gap-1.5 text-sm text-ink-gray-5">
          <span class="lucide-cloud-upload size-3.5" aria-hidden="true" />
          Recordings are also saved to Google Drive.
        </p>
      </div>
    </template>

    <!-- Recording -->
    <div
      v-else-if="phase === 'recording' || phase === 'paused'"
      class="rounded-xl border border-outline-gray-2 bg-surface-base p-6 text-center shadow-sm sm:p-10"
    >
      <div class="flex items-center justify-center gap-2.5 text-base font-medium" :class="phase === 'paused' ? 'text-ink-amber-7' : 'text-ink-red-7'">
        <span class="size-2.5 rounded-full bg-current" :class="{ 'animate-pulse': phase === 'recording' }" />
        {{ phase === 'paused' ? 'Paused' : 'Recording' }}
      </div>
      <p class="mt-3 text-[64px] font-semibold leading-none tabular-nums tracking-tight text-ink-gray-9" role="timer">
        {{ formatDuration(elapsed) }}
      </p>
      <p class="mt-3 text-base text-ink-gray-6">
        {{ currentMode.screen ? 'Switch to the window you want to show. Come back here to stop.' : 'You are on camera.' }}
      </p>

      <video
        v-if="currentMode.camera"
        ref="previewEl"
        autoplay
        muted
        playsinline
        class="mx-auto mt-6 -scale-x-100 bg-surface-gray-10 object-cover"
        :class="currentMode.screen ? 'size-32 rounded-full' : 'aspect-video w-full max-w-md rounded-lg'"
      />

      <div class="mt-8 flex flex-wrap items-center justify-center gap-2">
        <Button
          size="lg"
          :icon-left="phase === 'paused' ? 'lucide-play' : 'lucide-pause'"
          :label="phase === 'paused' ? 'Resume' : 'Pause'"
          @click="phase === 'paused' ? resume() : pause()"
        />
        <Button
          v-if="options.micEnabled"
          size="lg"
          :icon-left="micMuted ? 'lucide-mic-off' : 'lucide-mic'"
          :label="micMuted ? 'Unmute' : 'Mute'"
          @click="toggleMic"
        />
        <Button size="lg" variant="solid" theme="red" icon-left="lucide-square" label="Stop and share" @click="finish" />
        <Button size="lg" variant="ghost" label="Discard" @click="confirmDiscard" />
      </div>
    </div>

    <!-- Saving -->
    <div v-else-if="phase === 'finishing'" class="rounded-xl border border-outline-gray-2 bg-surface-base p-10 text-center shadow-sm">
      <LoadingIndicator class="mx-auto size-6 text-ink-gray-6" />
      <p class="mt-4 text-lg font-medium text-ink-gray-9">Saving your recording</p>
      <p class="mt-1 text-base text-ink-gray-6">
        {{ uploadPending > 0 ? `${formatSize(uploadPending)} left to upload. Keep this tab open.` : 'Creating your share link.' }}
      </p>
    </div>

    <!-- Upload failed -->
    <div v-else-if="phase === 'failed'" class="rounded-xl border border-outline-gray-2 bg-surface-base p-8 text-center shadow-sm">
      <p class="text-lg font-semibold text-ink-gray-9">The recording could not be uploaded</p>
      <p role="alert" class="mx-auto mt-2 max-w-md text-base text-ink-gray-6">{{ error }}</p>
      <div class="mt-6 flex justify-center gap-2">
        <Button size="lg" variant="solid" icon-left="lucide-download" label="Download recording" @click="downloadLocal" />
        <Button size="lg" label="Discard" @click="confirmDiscard" />
      </div>
    </div>

    <!-- Countdown -->
    <div v-if="phase === 'countdown'" class="fixed inset-0 z-50 flex flex-col items-center justify-center bg-black/70">
      <p class="text-[10rem] font-semibold leading-none text-white tabular-nums" aria-live="assertive">{{ countdown }}</p>
      <p class="mt-4 text-lg text-white/80">Recording starts in a moment</p>
      <button type="button" class="mt-8 rounded-lg bg-white/15 px-4 py-2 text-base font-medium text-white hover:bg-white/25" @click="discard">
        Cancel
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRouter } from 'vue-router'
import { Button, LoadingIndicator, Switch, dialog, toast } from 'frappe-ui'
import { formatDuration, formatSize, session } from '@/api'
import { MODES, isRecordingSupported, isScreenCaptureSupported, useRecorder } from '@/composables/useRecorder'

const router = useRouter()
const supported = isRecordingSupported()
const screenSupported = isScreenCaptureSupported()
const modes = MODES
const title = ref('')
const previewEl = ref(null)

const {
  phase,
  error,
  elapsed,
  countdown,
  uploadPending,
  options,
  devices,
  cameraStream,
  micMuted,
  start,
  stop,
  pause,
  resume,
  toggleMic,
  discard,
  localBlob,
  onAutoFinish,
} = useRecorder()

const currentMode = computed(() => modes.find((m) => m.value === options.mode))

// The preview <video> is re-created when the layout switches between phases.
watch(
  [cameraStream, previewEl],
  async () => {
    await nextTick()
    if (previewEl.value) previewEl.value.srcObject = cameraStream.value
  },
  { immediate: true },
)

function openRecording(recording) {
  router.push({ name: 'Watch', params: { token: recording.token }, query: { new: 1 } })
}

async function finish() {
  const recording = await stop()
  if (recording) openRecording(recording)
}

// The browser's own "Stop sharing" button ends the recording too.
onAutoFinish(openRecording)

function confirmDiscard() {
  dialog.danger({
    title: 'Discard this recording?',
    message: 'The video will be deleted and cannot be recovered.',
    confirmLabel: 'Discard',
    onConfirm: () => discard(),
  })
}

// Leaving through a link in the app unmounts the recorder, which deletes the
// recording. The browser's own warning only covers closing or reloading the tab.
onBeforeRouteLeave(() => {
  if (phase.value === 'finishing') {
    toast.error('Your recording is still being saved. Stay on this page until it is done.')
    return false
  }
  if (!['recording', 'paused', 'failed'].includes(phase.value)) return true
  return new Promise((resolve) => {
    dialog.danger({
      title: 'Leave and discard this recording?',
      message: 'The video will be deleted and cannot be recovered.',
      confirmLabel: 'Discard and leave',
      onConfirm: async () => {
        await discard()
        resolve(true)
      },
      onCancel: () => resolve(false),
    })
  })
})

function downloadLocal() {
  const blob = localBlob()
  if (!blob) return
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = `${title.value || 'recording'}.${blob.type.includes('mp4') ? 'mp4' : 'webm'}`
  link.click()
  setTimeout(() => URL.revokeObjectURL(link.href), 10000)
}
</script>
