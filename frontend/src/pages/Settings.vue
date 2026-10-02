<template>
  <div class="mx-auto max-w-2xl px-4 py-8 sm:px-6">
    <h1 class="text-2xl font-semibold text-ink-gray-9">Settings</h1>

    <div v-if="loading" class="flex justify-center py-24">
      <LoadingIndicator class="size-6 text-ink-gray-5" />
    </div>

    <form v-else class="mt-6 rounded-xl border border-outline-gray-2 bg-surface-base" @submit.prevent="save">
      <div class="border-b border-outline-gray-1 p-5">
        <div class="flex items-start justify-between gap-4">
          <div>
            <h2 class="text-lg font-semibold text-ink-gray-9">Google Drive storage</h2>
            <p class="mt-1 text-base text-ink-gray-6">
              Every finished recording is copied into one Drive folder. The share link keeps working either way.
            </p>
          </div>
          <Switch v-if="settings.connected" v-model="form.enabled" aria-label="Store recordings in Google Drive" />
        </div>
        <p v-if="status" role="status" class="mt-4 rounded-md px-3 py-2 text-base" :class="status.tone">{{ status.text }}</p>
      </div>

      <section class="border-b border-outline-gray-1 p-5">
        <label for="folder" class="block text-base font-semibold text-ink-gray-9">Drive folder link</label>
        <p class="mt-1 text-sm text-ink-gray-5">
          In Google Drive, open the folder’s <strong>Share</strong> dialog, set General access to
          <strong>Anyone with the link</strong> with the role <strong>Editor</strong>, and copy the link.
        </p>
        <input
          id="folder"
          v-model="form.folder_link"
          type="url"
          placeholder="https://drive.google.com/drive/folders/…"
          class="form-input mt-3 w-full rounded-md border-outline-gray-2 bg-surface-gray-2 py-1.5 text-base placeholder:text-ink-gray-4"
        />
        <p v-if="settings.folder_name && !dirty" class="mt-1.5 text-sm text-ink-gray-5">
          Saving to “{{ settings.folder_name }}”.
        </p>
      </section>

      <section class="border-b border-outline-gray-1 p-5">
        <div class="flex items-center justify-between gap-4">
          <div>
            <p class="text-base text-ink-gray-8">Keep a copy on this site</p>
            <p class="text-sm text-ink-gray-5">Turn off to free up site storage. Videos then play straight from Drive.</p>
          </div>
          <Switch v-model="form.keep_local_copy" aria-label="Keep a copy on this site" />
        </div>
      </section>

      <!-- Done once per site, so it stays folded away once it works. -->
      <section class="border-b border-outline-gray-1 p-5">
        <button
          type="button"
          class="flex w-full items-center justify-between gap-4 text-left"
          :aria-expanded="showUploader"
          @click="showUploader = !showUploader"
        >
          <span>
            <span class="block text-base font-semibold text-ink-gray-9">Uploader</span>
            <span class="mt-1 block text-sm text-ink-gray-5">{{ uploaderSummary }}</span>
          </span>
          <span
            class="size-4 shrink-0 text-ink-gray-5"
            :class="showUploader ? 'lucide-chevron-up' : 'lucide-chevron-down'"
            aria-hidden="true"
          />
        </button>

        <div v-if="showUploader" class="mt-4">
          <p class="text-sm text-ink-gray-5">
            Google only accepts uploads made by a Google account, even into a public folder. This small script lets
            the recorder upload as your account. No Google Cloud project or client ID is needed.
          </p>
          <ol class="mt-3 list-decimal space-y-2 pl-5 text-sm text-ink-gray-7">
            <li>
              Open
              <a class="underline" href="https://script.google.com/create" target="_blank" rel="noopener">a new Apps Script project</a>
              with the Google account that should own the uploaded videos.
            </li>
            <li>
              Replace the code in the editor with this script and save. It already contains this site’s secret, so
              keep it private.
              <div class="mt-2 flex items-start gap-2">
                <pre
                  class="max-h-40 min-w-0 flex-1 overflow-auto rounded-md bg-surface-gray-2 p-2 font-mono text-xs text-ink-gray-7"
                >{{ settings.uploader_script }}</pre>
                <Button icon-left="lucide-copy" label="Copy" @click="copyScript" />
              </div>
            </li>
            <li>
              Click <strong>Deploy → New deployment</strong>, choose the type <strong>Web app</strong>, set
              <strong>Execute as: Me</strong> and <strong>Who has access: Anyone</strong>, then <strong>Deploy</strong>.
              Allow access when Google asks. If it says the app isn’t verified, choose
              <strong>Advanced → Go to (project name)</strong>; it is your own script.
            </li>
            <li>Paste the <strong>Web app URL</strong> here.</li>
          </ol>
          <input
            v-model="form.uploader_url"
            type="url"
            aria-label="Web app URL"
            placeholder="https://script.google.com/macros/s/…/exec"
            class="form-input mt-3 w-full rounded-md border-outline-gray-2 bg-surface-gray-2 py-1.5 font-mono text-sm placeholder:text-ink-gray-4"
          />
        </div>
      </section>

      <div class="flex items-center justify-end gap-3 p-5">
        <p v-if="saveError" role="alert" class="mr-auto text-base text-ink-red-7">{{ saveError }}</p>
        <Button type="submit" variant="solid" label="Save" :loading="saving" :disabled="!dirty" />
      </div>
    </form>

    <AiSettingsCard v-if="!loading" />
  </div>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { Button, LoadingIndicator, Switch, toast } from 'frappe-ui'
import { api, copyText, errorMessage, loadSession } from '@/api'
import AiSettingsCard from '@/components/AiSettingsCard.vue'

const loading = ref(true)
const saving = ref(false)
const saveError = ref('')
const showUploader = ref(false)
const settings = ref({})
const form = reactive({ enabled: false, folder_link: '', keep_local_copy: true, uploader_url: '' })

function apply(data) {
  settings.value = data
  form.enabled = !!data.enabled
  form.folder_link = data.folder_link || ''
  form.keep_local_copy = !!data.keep_local_copy
  form.uploader_url = data.uploader_url || ''
}

const uploaderSummary = computed(() =>
  settings.value.connected
    ? `Set up. Uploading as ${settings.value.connected_email || 'your Google account'}.`
    : 'One-time setup: a small Google Apps Script that uploads the videos for you.',
)

const status = computed(() => {
  const s = settings.value
  if (!s.connected || !s.folder_id) return null
  if (!s.enabled) return { text: 'Google Drive storage is off.', tone: 'bg-surface-gray-2 text-ink-gray-7' }
  return {
    text: `New recordings are uploaded to “${s.folder_name || 'your folder'}”.`,
    tone: 'bg-surface-green-2 text-ink-green-8',
  }
})

const dirty = computed(() => {
  const s = settings.value
  return (
    form.enabled !== !!s.enabled ||
    form.folder_link !== (s.folder_link || '') ||
    form.keep_local_copy !== !!s.keep_local_copy ||
    form.uploader_url !== (s.uploader_url || '')
  )
})

async function save() {
  saving.value = true
  saveError.value = ''
  // Adding the uploader and a folder for the first time is the whole setup: switch storage on.
  const firstSetup = !settings.value.connected && form.uploader_url.trim() && form.folder_link.trim()
  try {
    apply(
      await api.saveDriveSettings({
        enabled: form.enabled || firstSetup ? 1 : 0,
        folder_link: form.folder_link,
        keep_local_copy: form.keep_local_copy ? 1 : 0,
        uploader_url: form.uploader_url,
      }),
    )
    if (settings.value.connected) showUploader.value = false
    toast.success('Settings saved')
    loadSession(true)
  } catch (e) {
    saveError.value = errorMessage(e)
  } finally {
    saving.value = false
  }
}

async function copyScript() {
  if (await copyText(settings.value.uploader_script)) toast.success('Script copied')
}

api
  .getDriveSettings()
  .then((data) => {
    apply(data)
    showUploader.value = !data.connected
  })
  .catch((e) => (saveError.value = errorMessage(e)))
  .finally(() => (loading.value = false))
</script>
