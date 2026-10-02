import { onBeforeUnmount, reactive, ref, shallowRef, watch } from 'vue'
import { api, errorMessage, uploadChunk } from '@/api'
import { createCompositor } from './compositor'

export const MODES = [
  { value: 'screen-camera', label: 'Screen + Camera', icon: 'lucide-picture-in-picture-2', screen: true, camera: true },
  { value: 'screen', label: 'Screen only', icon: 'lucide-monitor', screen: true, camera: false },
  { value: 'camera', label: 'Camera only', icon: 'lucide-video', screen: false, camera: true },
]

// First format the browser can record wins. WebM everywhere except Safari, which only does MP4.
const MIME_CANDIDATES = [
  'video/webm;codecs=vp9,opus',
  'video/webm;codecs=vp8,opus',
  'video/webm',
  'video/mp4;codecs=avc1.42E01E,mp4a.40.2',
  'video/mp4',
]

const COUNTDOWN_SECONDS = 3
const TIMESLICE_MS = 2000
const UPLOAD_RETRIES = 6
const VIDEO_BITS_PER_SECOND = 4_000_000

export function isRecordingSupported() {
  return typeof window.MediaRecorder !== 'undefined' && !!navigator.mediaDevices?.getUserMedia
}

export function isScreenCaptureSupported() {
  return !!navigator.mediaDevices?.getDisplayMedia
}

function pickMimeType() {
  return MIME_CANDIDATES.find((type) => MediaRecorder.isTypeSupported(type)) || ''
}

function stopStream(stream) {
  stream?.getTracks().forEach((track) => track.stop())
}

function describeMediaError(error, what) {
  if (error?.name === 'NotAllowedError') return `Permission to use your ${what} was denied.`
  if (error?.name === 'NotFoundError') return `No ${what} was found.`
  if (error?.name === 'NotReadableError') return `Your ${what} is in use by another app.`
  return `Could not access your ${what}: ${error?.message || error}`
}

export function useRecorder() {
  // idle -> countdown -> recording <-> paused -> finishing -> (done: back to idle)
  const phase = ref('idle')
  const error = ref('')
  const elapsed = ref(0)
  const countdown = ref(0)
  const uploadPending = ref(0) // bytes recorded but not yet on the server

  const options = reactive({
    mode: isScreenCaptureSupported() ? 'screen' : 'camera',
    micEnabled: true,
    systemAudio: true,
    micId: '',
    cameraId: '',
  })
  const devices = reactive({ cameras: [], mics: [] })

  const cameraStream = shallowRef(null) // live preview, reused for the recording
  const micMuted = ref(false)

  let screenStream = null
  let micStream = null
  let audioContext = null
  let micGain = null
  let compositor = null
  let recorder = null
  let recordedStream = null
  let monitor = null // hidden <video> used to grab the thumbnail
  let thumbnail = null
  let thumbnailTimer = null

  let token = null
  let chunkQueue = []
  let allChunks = [] // kept so the video can be saved locally if the upload fails
  let nextChunkIndex = 0
  let uploading = null
  let uploadError = null
  let mimeType = ''

  let timer = null
  let startedAt = 0
  let accumulated = 0
  let countdownTimer = null
  let cancelled = false

  const modeConfig = () => MODES.find((m) => m.value === options.mode)

  // ------------------------------------------------------------ devices

  async function refreshDevices() {
    if (!navigator.mediaDevices?.enumerateDevices) return
    const all = await navigator.mediaDevices.enumerateDevices()
    // Labels are empty until the user has granted permission once.
    devices.cameras = all.filter((d) => d.kind === 'videoinput' && d.deviceId)
    devices.mics = all.filter((d) => d.kind === 'audioinput' && d.deviceId)
  }

  async function startCameraPreview() {
    stopStream(cameraStream.value)
    cameraStream.value = null
    try {
      cameraStream.value = await navigator.mediaDevices.getUserMedia({
        video: {
          deviceId: options.cameraId ? { exact: options.cameraId } : undefined,
          width: { ideal: 1280 },
          height: { ideal: 720 },
        },
      })
      error.value = ''
      await refreshDevices()
    } catch (e) {
      error.value = describeMediaError(e, 'camera')
    }
  }

  function stopCameraPreview() {
    stopStream(cameraStream.value)
    cameraStream.value = null
  }

  watch(
    () => [options.mode, options.cameraId],
    () => {
      if (phase.value !== 'idle') return
      if (modeConfig().camera) startCameraPreview()
      else stopCameraPreview()
    },
  )

  navigator.mediaDevices?.addEventListener?.('devicechange', refreshDevices)
  refreshDevices()

  // ------------------------------------------------------------ start

  async function start(title) {
    if (phase.value !== 'idle') return
    error.value = ''
    cancelled = false
    const mode = modeConfig()

    try {
      // Ask for the screen first: it is the one prompt people most often cancel.
      if (mode.screen) {
        try {
          screenStream = await navigator.mediaDevices.getDisplayMedia({
            video: { frameRate: { ideal: 30 } },
            audio: options.systemAudio,
          })
        } catch (e) {
          // Closing the picker is a normal way to change your mind, not an error.
          if (e?.name !== 'NotAllowedError') error.value = describeMediaError(e, 'screen')
          return releaseMedia()
        }
      }

      if (mode.camera && !cameraStream.value) {
        await startCameraPreview()
        if (!cameraStream.value) return releaseMedia()
      }

      if (options.micEnabled) {
        try {
          micStream = await navigator.mediaDevices.getUserMedia({
            audio: {
              deviceId: options.micId ? { exact: options.micId } : undefined,
              echoCancellation: true,
              noiseSuppression: true,
            },
          })
          refreshDevices()
        } catch (e) {
          error.value = describeMediaError(e, 'microphone')
          return releaseMedia()
        }
      }

      mimeType = pickMimeType()
      const created = await api.createRecording(title, mimeType || 'video/webm')
      token = created.token

      // If the user stops sharing during the countdown, call the whole thing off.
      screenStream?.getVideoTracks()[0].addEventListener('ended', onScreenShareEnded)

      await runCountdown()
      if (cancelled) return

      beginRecording(mode)
    } catch (e) {
      error.value = errorMessage(e)
      await abandon()
    }
  }

  function runCountdown() {
    phase.value = 'countdown'
    countdown.value = COUNTDOWN_SECONDS
    return new Promise((resolve) => {
      countdownTimer = setInterval(() => {
        countdown.value -= 1
        if (countdown.value <= 0 || cancelled) {
          clearInterval(countdownTimer)
          resolve()
        }
      }, 1000)
    })
  }

  function buildAudioTrack() {
    const systemTracks = screenStream?.getAudioTracks() || []
    const micTracks = micStream?.getAudioTracks() || []
    if (!systemTracks.length && !micTracks.length) return null

    // Always mix through one AudioContext: it merges system + mic into the single
    // audio track MediaRecorder accepts, and gives the mic a gain node for muting.
    audioContext = new AudioContext()
    const destination = audioContext.createMediaStreamDestination()
    if (systemTracks.length) {
      audioContext.createMediaStreamSource(new MediaStream(systemTracks)).connect(destination)
    }
    if (micTracks.length) {
      micGain = audioContext.createGain()
      audioContext.createMediaStreamSource(new MediaStream(micTracks)).connect(micGain).connect(destination)
    }
    return destination.stream.getAudioTracks()[0]
  }

  function beginRecording(mode) {
    let videoTrack
    if (mode.screen && mode.camera) {
      compositor = createCompositor(screenStream, cameraStream.value)
      videoTrack = compositor.track
    } else if (mode.screen) {
      videoTrack = screenStream.getVideoTracks()[0]
    } else {
      videoTrack = cameraStream.value.getVideoTracks()[0]
    }

    const audioTrack = buildAudioTrack()
    recordedStream = new MediaStream(audioTrack ? [videoTrack, audioTrack] : [videoTrack])

    monitor = document.createElement('video')
    monitor.muted = true
    monitor.playsInline = true
    monitor.srcObject = new MediaStream([videoTrack])
    monitor.play().catch(() => {})
    thumbnailTimer = setTimeout(captureThumbnail, 1200)

    chunkQueue = []
    allChunks = []
    nextChunkIndex = 0
    uploadError = null
    uploadPending.value = 0
    micMuted.value = false

    recorder = new MediaRecorder(recordedStream, {
      ...(mimeType ? { mimeType } : {}),
      videoBitsPerSecond: VIDEO_BITS_PER_SECOND,
    })
    recorder.ondataavailable = (event) => {
      if (!event.data?.size) return
      allChunks.push(event.data)
      chunkQueue.push(event.data)
      uploadPending.value += event.data.size
      pumpUploads()
    }
    recorder.start(TIMESLICE_MS)

    accumulated = 0
    startedAt = Date.now()
    elapsed.value = 0
    timer = setInterval(tick, 250)
    phase.value = 'recording'
    window.addEventListener('beforeunload', warnBeforeLeaving)
  }

  function tick() {
    elapsed.value = (accumulated + (phase.value === 'recording' ? Date.now() - startedAt : 0)) / 1000
  }

  function onScreenShareEnded() {
    if (phase.value === 'countdown') discard()
    else if (phase.value === 'recording' || phase.value === 'paused') finishAfterShareEnded()
  }

  let onAutoFinish = null
  async function finishAfterShareEnded() {
    const recording = await stop()
    if (recording) onAutoFinish?.(recording)
  }

  // ------------------------------------------------------------ upload

  /** Sends queued pieces one request at a time, in order, retrying on failure. */
  function pumpUploads() {
    if (uploading) return uploading
    uploading = (async () => {
      while (chunkQueue.length && !uploadError) {
        // Whatever piled up while the last request was in flight goes out together.
        const batch = chunkQueue.splice(0, chunkQueue.length)
        const blob = new Blob(batch)
        const index = nextChunkIndex
        let attempt = 0
        for (;;) {
          try {
            await uploadChunk(token, index, blob)
            break
          } catch (e) {
            attempt += 1
            // 4xx means the server understood and refused; retrying will not help.
            const refused = e.status >= 400 && e.status < 500
            if (refused || attempt > UPLOAD_RETRIES || cancelled) {
              uploadError = e
              return
            }
            await new Promise((r) => setTimeout(r, Math.min(1000 * 2 ** attempt, 15000)))
          }
        }
        nextChunkIndex += 1
        uploadPending.value -= blob.size
      }
    })().finally(() => {
      uploading = null
    })
    return uploading
  }

  // ------------------------------------------------------------ controls

  function pause() {
    if (phase.value !== 'recording') return
    recorder.pause()
    accumulated += Date.now() - startedAt
    phase.value = 'paused'
    tick()
  }

  function resume() {
    if (phase.value !== 'paused') return
    recorder.resume()
    startedAt = Date.now()
    phase.value = 'recording'
  }

  function toggleMic() {
    if (!micGain) return
    micMuted.value = !micMuted.value
    micGain.gain.value = micMuted.value ? 0 : 1
  }

  function captureThumbnail() {
    if (!monitor?.videoWidth) return
    const width = 640
    const canvas = document.createElement('canvas')
    canvas.width = width
    canvas.height = Math.round((monitor.videoHeight / monitor.videoWidth) * width)
    canvas.getContext('2d').drawImage(monitor, 0, 0, canvas.width, canvas.height)
    try {
      thumbnail = canvas.toDataURL('image/jpeg', 0.8)
    } catch (e) {
      thumbnail = null
    }
  }

  function stopRecorder() {
    return new Promise((resolve) => {
      if (!recorder || recorder.state === 'inactive') return resolve()
      recorder.addEventListener('stop', resolve, { once: true })
      recorder.stop()
    })
  }

  /** Stops, waits for the last bytes to reach the server, and returns the saved recording. */
  async function stop() {
    if (phase.value !== 'recording' && phase.value !== 'paused') return null
    if (phase.value === 'recording') accumulated += Date.now() - startedAt
    const durationSeconds = Math.max(1, Math.round(accumulated / 1000))
    phase.value = 'finishing'
    clearInterval(timer)
    elapsed.value = accumulated / 1000

    if (!thumbnail) captureThumbnail()
    await stopRecorder()
    releaseMedia()

    try {
      await pumpUploads()
      // A chunk can be queued while the pump is winding down; drain until empty.
      while (chunkQueue.length && !uploadError) await pumpUploads()
      if (uploadError) throw uploadError

      const recording = await api.finalizeRecording(token, durationSeconds, thumbnail)
      reset({ restartPreview: false })
      return recording
    } catch (e) {
      error.value = `${errorMessage(e)} Your recording was not lost: download it below.`
      phase.value = 'failed'
      return null
    }
  }

  /** The recording as a local file, for when it could not be uploaded. */
  function localBlob() {
    return allChunks.length ? new Blob(allChunks, { type: (mimeType || 'video/webm').split(';')[0] }) : null
  }

  /** Throws the current recording away, at any point. */
  async function discard() {
    cancelled = true
    clearInterval(countdownTimer)
    clearInterval(timer)
    if (recorder && recorder.state !== 'inactive') {
      recorder.ondataavailable = null
      await stopRecorder()
    }
    await abandon()
  }

  async function abandon() {
    const abandoned = token
    releaseMedia()
    reset()
    if (abandoned) await api.deleteRecording(abandoned).catch(() => {})
  }

  function releaseMedia() {
    clearTimeout(thumbnailTimer)
    screenStream?.getVideoTracks()[0]?.removeEventListener('ended', onScreenShareEnded)
    compositor?.stop()
    compositor = null
    stopStream(screenStream)
    stopStream(micStream)
    stopStream(recordedStream)
    screenStream = micStream = recordedStream = null
    audioContext?.close().catch(() => {})
    audioContext = micGain = null
    if (monitor) monitor.srcObject = null
    monitor = null
    // The camera preview keeps running while idle so the setup screen stays live.
    if (phase.value !== 'idle' && phase.value !== 'countdown') stopCameraPreview()
  }

  function reset({ restartPreview = true } = {}) {
    window.removeEventListener('beforeunload', warnBeforeLeaving)
    recorder = null
    token = null
    thumbnail = null
    chunkQueue = []
    allChunks = []
    uploadPending.value = 0
    elapsed.value = 0
    phase.value = 'idle'
    if (restartPreview && modeConfig().camera && !cameraStream.value) startCameraPreview()
  }

  function warnBeforeLeaving(event) {
    event.preventDefault()
    event.returnValue = ''
  }

  onBeforeUnmount(() => {
    navigator.mediaDevices?.removeEventListener?.('devicechange', refreshDevices)
    window.removeEventListener('beforeunload', warnBeforeLeaving)
    clearInterval(countdownTimer)
    clearInterval(timer)
    if (recorder && recorder.state !== 'inactive') {
      recorder.ondataavailable = null
      recorder.stop()
    }
    phase.value = 'finishing' // so releaseMedia also stops the camera preview
    releaseMedia()
    if (token) api.deleteRecording(token).catch(() => {})
  })

  return {
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
    onAutoFinish(callback) {
      onAutoFinish = callback
    },
  }
}
