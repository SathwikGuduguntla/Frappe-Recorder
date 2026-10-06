import { reactive } from 'vue'
import { call } from 'frappe-ui'

const API = 'frappe_recorder.api.'
const AI = 'frappe_recorder.ai.'

export const session = reactive({ loaded: false, user: null, full_name: '', is_manager: false })

let sessionPromise = null
export function loadSession(force = false) {
  if (!sessionPromise || force) {
    sessionPromise = call(API + 'get_session').then((data) => {
      Object.assign(session, data, { loaded: true })
      return session
    })
  }
  return sessionPromise
}

export const api = {
  createRecording: (title, mimeType) => call(API + 'create_recording', { title, mime_type: mimeType }),
  finalizeRecording: (token, durationSeconds, thumbnail) =>
    call(API + 'finalize_recording', { token, duration_seconds: durationSeconds, thumbnail }),
  updateRecording: (token, values) => call(API + 'update_recording', { token, ...values }),
  deleteRecording: (token) => call(API + 'delete_recording', { token }),
  getRecording: (token) => call(API + 'get_recording', { token }),
  registerView: (token) => call(API + 'register_view', { token }),
  listRecordings: (search) => frappeGet(API + 'list_recordings', { search: search || '' }),

  getAiConfig: () => frappeGet(AI + 'get_ai_config'),
  getAi: (token) => frappeGet(AI + 'get_ai', { token }),
  saveTranscript: (token, segments, model) =>
    call(AI + 'save_transcript', { token, segments: JSON.stringify(segments), model }),
  saveInsights: (token, data, model) =>
    call(AI + 'save_insights', {
      token,
      summary: data.summary,
      highlights: JSON.stringify(data.highlights || []),
      questions: JSON.stringify(data.questions || []),
      model,
    }),
  saveSop: (token, sop, model) => call(AI + 'save_sop', { token, sop, model }),
  reportAiFailure: (token, kind, error) => call(AI + 'report_failure', { token, kind, error }),
  resetAi: (token) => call(AI + 'reset_ai', { token }),
  getAiSettings: () => frappeGet(AI + 'get_ai_settings'),
  saveAiSettings: (values) => call(AI + 'save_ai_settings', values),
}

async function frappeGet(method, params = {}) {
  const query = new URLSearchParams(params).toString()
  const response = await fetch(`/api/method/${method}${query ? '?' + query : ''}`, {
    headers: { Accept: 'application/json', 'X-Frappe-Site-Name': window.location.hostname },
  })
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(serverMessage(body) || response.statusText)
  return body.message
}

/** Uploads one piece of the video. Plain fetch, because the body is binary form data. */
export async function uploadChunk(token, index, blob) {
  const form = new FormData()
  form.append('token', token)
  form.append('index', index)
  form.append('chunk', blob, `chunk-${index}`)
  const response = await fetch(`/api/method/${API}upload_chunk`, {
    method: 'POST',
    headers: { Accept: 'application/json', 'X-Frappe-CSRF-Token': window.csrf_token || '' },
    body: form,
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    const error = new Error(serverMessage(body) || `Upload failed (${response.status})`)
    error.status = response.status
    throw error
  }
}

function serverMessage(body) {
  try {
    const messages = JSON.parse(body._server_messages || '[]')
    if (messages.length) return JSON.parse(messages[0]).message
  } catch (e) {
    /* fall through */
  }
  return body.exception || body.message || ''
}

/** Turns anything a failed call can throw into one readable line. */
export function errorMessage(error) {
  if (!error) return 'Something went wrong.'
  const messages = error.messages || error.error?.messages
  if (Array.isArray(messages) && messages.length) return stripHtml(messages[0])
  return stripHtml(error.message || String(error))
}

function stripHtml(text) {
  const div = document.createElement('div')
  div.innerHTML = text
  return div.textContent || text
}

export function formatDuration(totalSeconds) {
  const s = Math.max(0, Math.round(totalSeconds || 0))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = String(s % 60).padStart(2, '0')
  return h ? `${h}:${String(m).padStart(2, '0')}:${sec}` : `${m}:${sec}`
}

export function formatDate(value) {
  if (!value) return ''
  const date = new Date(String(value).replace(' ', 'T'))
  return date.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
}

export function formatSize(bytes) {
  if (!bytes) return ''
  const units = ['B', 'KB', 'MB', 'GB']
  let i = 0
  let n = bytes
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024
    i++
  }
  return `${n.toFixed(n >= 10 || i === 0 ? 0 : 1)} ${units[i]}`
}

export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch (e) {
    return false
  }
}
