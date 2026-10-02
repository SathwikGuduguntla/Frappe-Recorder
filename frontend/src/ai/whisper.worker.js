// Speech to text in a background thread, with Whisper through transformers.js.
// The model is downloaded once from Hugging Face and then cached by the browser.
import { env, pipeline } from '@huggingface/transformers'

env.allowLocalModels = false

// Audio is handled in blocks so progress can be reported and memory stays flat.
const BLOCK_SECONDS = 300
const SAMPLE_RATE = 16000

let transcriber = null
let loadedKey = ''

self.onmessage = async ({ data }) => {
  if (data.type !== 'transcribe') return
  try {
    await load(data.model, data.device)
    const segments = await transcribe(data.audio)
    self.postMessage({ type: 'done', segments })
  } catch (e) {
    self.postMessage({ type: 'error', message: e?.message || String(e) })
  }
}

async function load(model, device) {
  const key = `${model}|${device}`
  if (transcriber && loadedKey === key) return
  self.postMessage({ type: 'stage', stage: 'download' })
  const files = {}
  transcriber = await pipeline('automatic-speech-recognition', model, {
    device,
    // WebGPU runs the encoder at full precision and a 4-bit decoder; plain WASM uses 8-bit.
    dtype: device === 'webgpu' ? { encoder_model: 'fp32', decoder_model_merged: 'q4' } : 'q8',
    progress_callback: (p) => {
      if (p.status !== 'progress' || !p.total) return
      files[p.file] = { loaded: p.loaded, total: p.total }
      const all = Object.values(files)
      const loaded = all.reduce((sum, f) => sum + f.loaded, 0)
      const total = all.reduce((sum, f) => sum + f.total, 0)
      self.postMessage({ type: 'progress', stage: 'download', value: total ? loaded / total : 0 })
    },
  })
  loadedKey = key
}

async function transcribe(audio) {
  const blockSize = BLOCK_SECONDS * SAMPLE_RATE
  const blocks = Math.max(1, Math.ceil(audio.length / blockSize))
  const segments = []
  self.postMessage({ type: 'stage', stage: 'transcribe' })

  for (let i = 0; i < blocks; i++) {
    const offset = i * BLOCK_SECONDS
    const block = audio.subarray(i * blockSize, Math.min((i + 1) * blockSize, audio.length))
    const blockEnd = offset + block.length / SAMPLE_RATE
    const output = await transcriber(block, { return_timestamps: true, chunk_length_s: 30, stride_length_s: 5 })

    for (const chunk of output.chunks || []) {
      const text = (chunk.text || '').trim()
      if (!text) continue
      const [start, end] = chunk.timestamp || []
      segments.push({
        start: offset + (start ?? 0),
        end: Math.min(offset + (end ?? block.length / SAMPLE_RATE), blockEnd),
        text,
      })
    }
    self.postMessage({ type: 'progress', stage: 'transcribe', value: (i + 1) / blocks })
  }
  return segments
}
