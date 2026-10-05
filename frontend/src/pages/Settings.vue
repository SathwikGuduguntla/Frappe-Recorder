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

      <!-- Google account the videos are uploaded as -->
      <section class="border-b border-outline-gray-1 p-5">
        <p class="text-base font-semibold text-ink-gray-9">Google account</p>

        <div v-if="settings.connected" class="mt-2 flex flex-wrap items-center justify-between gap-3">
          <p class="text-sm text-ink-gray-7">
            Connected as <strong>{{ settings.connected_email || 'your Google account' }}</strong>. Videos are uploaded as this
            account and use its storage.
          </p>
          <Button label="Disconnect" :loading="connecting" @click="disconnect" />
        </div>

        <div v-else-if="settings.google_client_ready" class="mt-2 flex flex-col items-start gap-3">
          <p class="text-sm text-ink-gray-5">Sign in with the Google account that should own the uploaded videos.</p>
          <Button variant="solid" icon-left="lucide-log-in" label="Connect Google Drive" :loading="connecting" @click="connect" />
        </div>

        <div v-else class="mt-2">
          <p class="text-sm text-ink-gray-5">
            One-time setup, so Google can show its sign-in screen for this site. You need a Google Cloud project (free).
          </p>
          <ol class="mt-3 list-decimal space-y-2 pl-5 text-sm text-ink-gray-7">
            <li>
              In Google Cloud Console,
              <a class="underline" href="https://console.cloud.google.com/apis/library/drive.googleapis.com" target="_blank" rel="noopener">enable the Google Drive API</a>.
              If Google asks you to set up the OAuth consent screen, do so; while it is in testing, add your Google account as a test user.
            </li>
            <li>
              <a class="underline" href="https://console.cloud.google.com/apis/credentials" target="_blank" rel="noopener">Create an OAuth client ID</a>
              of the type <strong>Web application</strong>, with this <strong>Authorized redirect URI</strong>:
              <div class="mt-2 flex items-center gap-2">
                <code class="min-w-0 flex-1 truncate rounded-md bg-surface-gray-2 px-2 py-1.5 font-mono text-xs text-ink-gray-7">{{ settings.redirect_uri }}</code>
                <Button icon-left="lucide-copy" label="Copy" @click="copyRedirect" />
              </div>
            </li>
            <li>Paste the Client ID and Client secret here.</li>
          </ol>
          <div class="mt-3 grid gap-3 sm:grid-cols-2">
            <input
              v-model="client.id"
              aria-label="Client ID"
              placeholder="Client ID (….apps.googleusercontent.com)"
              autocomplete="off"
              class="form-input w-full rounded-md border-outline-gray-2 bg-surface-gray-2 py-1.5 text-sm placeholder:text-ink-gray-4"
            />
            <input
              v-model="client.secret"
              type="password"
              aria-label="Client secret"
              placeholder="Client secret"
              autocomplete="off"
              class="form-input w-full rounded-md border-outline-gray-2 bg-surface-gray-2 py-1.5 text-sm placeholder:text-ink-gray-4"
            />
          </div>
          <div class="mt-3 flex items-center gap-3">
            <Button label="Save client" :loading="savingClient" :disabled="!client.id.trim() || !client.secret.trim()" @click="saveClient" />
            <p v-if="clientError" role="alert" class="text-sm text-ink-red-7">{{ clientError }}</p>
          </div>
        </div>
      </section>

      <section class="border-b border-outline-gray-1 p-5">
        <label for="folder" class="block text-base font-semibold text-ink-gray-9">Drive folder link</label>
        <p class="mt-1 text-sm text-ink-gray-5">
          A folder the Google account above can add files to, such as one in its own Drive. Open it in Google Drive and copy
          the link from the address bar or the <strong>Share</strong> dialog.
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
import { useRoute, useRouter } from 'vue-router'
import { Button, LoadingIndicator, Switch, toast } from 'frappe-ui'
import { api, copyText, errorMessage, loadSession } from '@/api'
import AiSettingsCard from '@/components/AiSettingsCard.vue'

const route = useRoute()
const router = useRouter()
const loading = ref(true)
const saving = ref(false)
const saveError = ref('')
const connecting = ref(false)
const savingClient = ref(false)
const clientError = ref('')
const settings = ref({})
const form = reactive({ enabled: false, folder_link: '', keep_local_copy: true })
const client = reactive({ id: '', secret: '' })

function apply(data) {
  settings.value = data
  form.enabled = !!data.enabled
  form.folder_link = data.folder_link || ''
  form.keep_local_copy = !!data.keep_local_copy
  client.id = data.client_id || ''
}

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
    form.keep_local_copy !== !!s.keep_local_copy
  )
})

async function save() {
  saving.value = true
  saveError.value = ''
  // Adding the first folder to a connected account is the whole setup: switch storage on.
  const firstSetup = settings.value.connected && !settings.value.folder_id && form.folder_link.trim()
  try {
    apply(
      await api.saveDriveSettings({
        enabled: form.enabled || firstSetup ? 1 : 0,
        folder_link: form.folder_link,
        keep_local_copy: form.keep_local_copy ? 1 : 0,
      }),
    )
    toast.success('Settings saved')
    loadSession(true)
  } catch (e) {
    saveError.value = errorMessage(e)
  } finally {
    saving.value = false
  }
}

async function saveClient() {
  savingClient.value = true
  clientError.value = ''
  try {
    apply(await api.saveGoogleClient(client.id, client.secret))
    client.secret = ''
  } catch (e) {
    clientError.value = errorMessage(e)
  } finally {
    savingClient.value = false
  }
}

// Google's sign-in screen comes back to this page with ?drive=connected or ?drive=denied.
async function connect() {
  connecting.value = true
  try {
    window.location.href = (await api.connectDrive()).url
  } catch (e) {
    saveError.value = errorMessage(e)
    connecting.value = false
  }
}

async function disconnect() {
  connecting.value = true
  try {
    apply(await api.disconnectDrive())
    loadSession(true)
  } catch (e) {
    saveError.value = errorMessage(e)
  } finally {
    connecting.value = false
  }
}

async function copyRedirect() {
  if (await copyText(settings.value.redirect_uri)) toast.success('Redirect URI copied')
}

if (route.query.drive) {
  if (route.query.drive === 'connected') toast.success('Google Drive connected')
  else saveError.value = 'Google sign-in was cancelled or refused.'
  router.replace({ query: {} })
  loadSession(true)
}

api
  .getDriveSettings()
  .then(apply)
  .catch((e) => (saveError.value = errorMessage(e)))
  .finally(() => (loading.value = false))
</script>
