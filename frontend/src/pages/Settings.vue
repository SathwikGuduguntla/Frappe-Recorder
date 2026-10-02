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
        <p v-if="notice" role="status" class="mt-4 rounded-md px-3 py-2 text-base" :class="notice.tone">{{ notice.text }}</p>
      </div>

      <section class="border-b border-outline-gray-1 p-5">
        <label for="folder" class="block text-base font-semibold text-ink-gray-9">Drive folder link</label>
        <input
          id="folder"
          v-model="form.folder_link"
          type="url"
          placeholder="https://drive.google.com/drive/folders/…"
          class="form-input mt-3 w-full rounded-md border-outline-gray-2 bg-surface-gray-2 py-1.5 text-base placeholder:text-ink-gray-4"
        />
        <p class="mt-1.5 text-sm text-ink-gray-5">
          <template v-if="settings.folder_name && !dirty">Saving to “{{ settings.folder_name }}”.</template>
          <template v-else>Open the folder in Google Drive and paste its address here. The Google account you connect needs edit access to it.</template>
        </p>

        <div class="mt-4 flex items-center justify-between gap-4">
          <p class="text-base" :class="settings.connected ? 'text-ink-green-8' : 'text-ink-gray-6'">
            <template v-if="settings.connected">Connected as {{ settings.connected_email || 'a Google account' }}</template>
            <template v-else>Not connected yet.</template>
          </p>
          <Button v-if="settings.connected" label="Disconnect" :loading="connecting" @click="disconnect" />
          <Button v-else variant="solid" label="Connect Google Drive" :disabled="!form.folder_link.trim()" :loading="connecting" @click="connect" />
        </div>
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

      <!-- Only needed once per site, so it stays folded away once a client exists. -->
      <section class="border-b border-outline-gray-1 p-5">
        <button type="button" class="flex w-full items-center justify-between gap-4 text-left" :aria-expanded="showClient" @click="showClient = !showClient">
          <span>
            <span class="block text-base font-semibold text-ink-gray-9">Google OAuth client</span>
            <span class="mt-1 block text-sm text-ink-gray-5">{{ clientSummary }}</span>
          </span>
          <span class="size-4 shrink-0 text-ink-gray-5" :class="showClient ? 'lucide-chevron-up' : 'lucide-chevron-down'" aria-hidden="true" />
        </button>

        <div v-if="showClient" class="mt-4">
          <p class="text-sm text-ink-gray-5">
            Create an OAuth client of type “Web application” in Google Cloud Console with the Drive API enabled, and add
            this redirect URI to it.
          </p>
          <div class="mt-3 flex gap-2">
            <input
              :value="settings.redirect_uri"
              readonly
              aria-label="Redirect URI"
              class="form-input min-w-0 flex-1 rounded-md border-outline-gray-2 bg-surface-gray-2 py-1.5 font-mono text-sm text-ink-gray-7"
              @focus="$event.target.select()"
            />
            <Button icon-left="lucide-copy" label="Copy" @click="copyRedirect" />
          </div>

          <div class="mt-4 grid gap-4 sm:grid-cols-2">
            <div>
              <label for="client-id" class="block text-sm font-medium text-ink-gray-7">Client ID</label>
              <input
                id="client-id"
                v-model="form.client_id"
                type="text"
                autocomplete="off"
                class="form-input mt-1.5 w-full rounded-md border-outline-gray-2 bg-surface-gray-2 py-1.5 text-base"
              />
            </div>
            <div>
              <label for="client-secret" class="block text-sm font-medium text-ink-gray-7">Client secret</label>
              <input
                id="client-secret"
                v-model="form.client_secret"
                type="password"
                autocomplete="new-password"
                :placeholder="settings.has_client_secret ? 'Saved. Type to replace.' : ''"
                class="form-input mt-1.5 w-full rounded-md border-outline-gray-2 bg-surface-gray-2 py-1.5 text-base placeholder:text-ink-gray-4"
              />
            </div>
          </div>
        </div>
      </section>

      <div class="flex items-center justify-end gap-3 p-5">
        <p v-if="saveError" role="alert" class="mr-auto text-base text-ink-red-7">{{ saveError }}</p>
        <Button type="submit" variant="solid" label="Save" :loading="saving" :disabled="!dirty" />
      </div>
    </form>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Button, LoadingIndicator, Switch, toast } from 'frappe-ui'
import { api, copyText, errorMessage, loadSession } from '@/api'

const route = useRoute()
const router = useRouter()

const loading = ref(true)
const saving = ref(false)
const connecting = ref(false)
const saveError = ref('')
const showClient = ref(false)
const settings = ref({})
const form = reactive({ enabled: false, folder_link: '', keep_local_copy: true, client_id: '', client_secret: '' })

// Result of the round trip to Google, passed back in the URL.
const notices = {
  connected: { text: 'Google Drive is connected.', tone: 'bg-surface-green-2 text-ink-green-8' },
  denied: { text: 'Google Drive was not connected: access was not granted.', tone: 'bg-surface-red-2 text-ink-red-7' },
  failed: { text: 'Google Drive was not connected. Check the client ID, secret and redirect URI.', tone: 'bg-surface-red-2 text-ink-red-7' },
  folder: { text: 'Connected, but that Google account cannot add files to this folder. Check the link, or share the folder with that account.', tone: 'bg-surface-amber-2 text-ink-amber-8' },
}
const notice = ref(notices[route.query.drive] || null)
if (route.query.drive) router.replace({ name: 'Settings' })

function apply(data) {
  settings.value = data
  form.enabled = !!data.enabled
  form.folder_link = data.folder_link || ''
  form.keep_local_copy = !!data.keep_local_copy
  form.client_id = data.client_id || ''
  form.client_secret = ''
}

const clientSummary = computed(() => {
  if (!settings.value.has_client) return 'One-time setup: Google needs a client ID and secret before an account can be connected.'
  return settings.value.client_id ? 'Set up.' : 'Using the client from this site’s Google Settings.'
})

const dirty = computed(() => {
  const s = settings.value
  return (
    form.enabled !== !!s.enabled ||
    form.folder_link !== (s.folder_link || '') ||
    form.keep_local_copy !== !!s.keep_local_copy ||
    form.client_id !== (s.client_id || '') ||
    form.client_secret !== ''
  )
})

async function submit(enabled) {
  apply(
    await api.saveDriveSettings({
      enabled: enabled ? 1 : 0,
      folder_link: form.folder_link,
      keep_local_copy: form.keep_local_copy ? 1 : 0,
      client_id: form.client_id,
      client_secret: form.client_secret,
    }),
  )
}

async function save() {
  saving.value = true
  saveError.value = ''
  try {
    await submit(form.enabled)
    notice.value = null
    toast.success('Settings saved')
    loadSession(true)
  } catch (e) {
    saveError.value = errorMessage(e)
  } finally {
    saving.value = false
  }
}

async function connect() {
  connecting.value = true
  saveError.value = ''
  try {
    // Connecting is the whole setup: store the link, switch Drive storage on, go to Google.
    await submit(true)
    if (!settings.value.has_client) {
      showClient.value = true
      throw new Error('Add a Google OAuth client ID and secret first.')
    }
    const { url } = await api.getDriveAuthUrl()
    window.location.href = url
  } catch (e) {
    connecting.value = false
    saveError.value = errorMessage(e)
  }
}

async function disconnect() {
  connecting.value = true
  try {
    apply(await api.disconnectDrive())
    notice.value = null
    loadSession(true)
  } catch (e) {
    toast.error(errorMessage(e))
  } finally {
    connecting.value = false
  }
}

async function copyRedirect() {
  if (await copyText(settings.value.redirect_uri)) toast.success('Redirect URI copied')
}

api
  .getDriveSettings()
  .then((data) => {
    apply(data)
    showClient.value = !data.has_client
  })
  .catch((e) => (saveError.value = errorMessage(e)))
  .finally(() => (loading.value = false))
</script>
