<template>
  <form class="mt-6 rounded-xl border border-outline-gray-2 bg-surface-base" @submit.prevent="save">
    <div class="border-b border-outline-gray-1 p-5">
      <div class="flex items-start justify-between gap-4">
        <div>
          <h2 class="text-lg font-semibold text-ink-gray-9">Transcripts and AI notes</h2>
          <p class="mt-1 text-base text-ink-gray-6">
            Transcripts, summaries, highlights and SOPs are made with free open-source models that run in the recording
            owner’s browser. No API key, nothing to install, and no load on this server.
          </p>
        </div>
        <Switch v-model="form.enabled" aria-label="Turn on transcripts and AI notes" />
      </div>
    </div>

    <div v-if="loading" class="flex justify-center p-8"><LoadingIndicator class="size-5 text-ink-gray-5" /></div>

    <template v-else>
      <section class="grid gap-4 border-b border-outline-gray-1 p-5 sm:grid-cols-2">
        <div>
          <label for="whisper-model" class="block text-sm font-medium text-ink-gray-7">Speech model</label>
          <select id="whisper-model" v-model="form.whisper_model" class="form-select mt-1.5 w-full rounded-md border-outline-gray-2 bg-surface-gray-2 py-1.5 text-base">
            <option v-for="m in settings.whisper_models" :key="m" :value="m">{{ whisperLabels[m] || m }}</option>
          </select>
          <p class="mt-1.5 text-sm text-ink-gray-5">Downloaded once by each browser that transcribes.</p>
        </div>
        <div>
          <label for="llm-model" class="block text-sm font-medium text-ink-gray-7">Writing model</label>
          <select id="llm-model" v-model="form.llm_model" class="form-select mt-1.5 w-full rounded-md border-outline-gray-2 bg-surface-gray-2 py-1.5 text-base">
            <option v-for="m in settings.llm_models" :key="m" :value="m">{{ llmLabels[m] || m }}</option>
          </select>
          <p class="mt-1.5 text-sm text-ink-gray-5">Needs Chrome or Edge with WebGPU. Bigger writes better but needs a stronger graphics card.</p>
        </div>
      </section>

      <div class="flex items-center justify-end gap-3 p-5">
        <p v-if="saveError" role="alert" class="mr-auto text-base text-ink-red-7">{{ saveError }}</p>
        <Button type="submit" variant="solid" label="Save" :loading="saving" :disabled="!dirty" />
      </div>
    </template>
  </form>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { Button, LoadingIndicator, Switch, toast } from 'frappe-ui'
import { api, errorMessage } from '@/api'

const whisperLabels = {
  'onnx-community/whisper-tiny': 'Whisper tiny · ~75 MB · fastest',
  'onnx-community/whisper-base': 'Whisper base · ~145 MB · recommended',
  'onnx-community/whisper-small': 'Whisper small · ~480 MB · most accurate',
}
const llmLabels = {
  'Qwen2.5-0.5B-Instruct-q4f16_1-MLC': 'Qwen2.5 0.5B · ~0.4 GB · basic',
  'Qwen2.5-1.5B-Instruct-q4f16_1-MLC': 'Qwen2.5 1.5B · ~1 GB · recommended',
  'Qwen2.5-3B-Instruct-q4f16_1-MLC': 'Qwen2.5 3B · ~2 GB · better',
  'Llama-3.2-3B-Instruct-q4f16_1-MLC': 'Llama 3.2 3B · ~2 GB · better',
}

const loading = ref(true)
const saving = ref(false)
const saveError = ref('')
const settings = ref({ whisper_models: [], llm_models: [] })
const form = reactive({ enabled: true, whisper_model: '', llm_model: '' })

function apply(data) {
  settings.value = data
  Object.assign(form, {
    enabled: !!data.enabled,
    whisper_model: data.whisper_model || '',
    llm_model: data.llm_model || '',
  })
}

const dirty = computed(() => {
  const s = settings.value
  return (
    form.enabled !== !!s.enabled ||
    form.whisper_model !== (s.whisper_model || '') ||
    form.llm_model !== (s.llm_model || '')
  )
})

async function save() {
  saving.value = true
  saveError.value = ''
  try {
    apply(await api.saveAiSettings({ ...form, enabled: form.enabled ? 1 : 0 }))
    toast.success('Settings saved')
  } catch (e) {
    saveError.value = errorMessage(e)
  } finally {
    saving.value = false
  }
}

api
  .getAiSettings()
  .then(apply)
  .catch((e) => (saveError.value = errorMessage(e)))
  .finally(() => (loading.value = false))
</script>
