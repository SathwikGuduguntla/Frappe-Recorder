import { computed, reactive, ref, shallowRef, watch } from 'vue'
import { call } from 'frappe-ui'

import { composeCameraBubble } from './compositor'

const CHUNK_INTERVAL_MS = 3000
const UPLOAD_RETRIES = 5
const API = 'frappe_recorder.api.recording'

export const MODES = [
	{ value: 'Screen + Camera', label: 'Screen + Camera', icon: 'lucide-monitor-smartphone' },
	{ value: 'Screen', label: 'Screen only', icon: 'lucide-monitor' },
	{ value: 'Camera', label: 'Camera only', icon: 'lucide-video' },
]

const MIME_TYPES = [
	'video/webm;codecs=vp9,opus',
	'video/webm;codecs=vp8,opus',
	'video/webm',
	'video/mp4;codecs=avc1,mp4a.40.2',
	'video/mp4',
]

export function isRecordingSupported() {
	return Boolean(
		window.MediaRecorder &&
			navigator.mediaDevices?.getUserMedia &&
			navigator.mediaDevices?.getDisplayMedia
	)
}

function pickMimeType() {
	return MIME_TYPES.find((type) => MediaRecorder.isTypeSupported(type)) || ''
}

function stopStream(stream) {
	stream?.getTracks().forEach((track) => track.stop())
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

/**
 * Browser-side recorder in the style of Loom/Kommodo:
 * - screen, camera, or screen with a floating camera bubble
 * - microphone + system audio mixed into one track
 * - 3-2-1 countdown, pause/resume, mute, restart and cancel
 * - the video is uploaded in slices *while* recording, so the share link exists
 *   from the first second and is ready as soon as the recording stops
 */
export function useRecorder() {
	const settings = reactive({
		mode: 'Screen + Camera',
		cameraId: '',
		micId: '',
		micEnabled: true,
		systemAudio: true,
		countdown: true,
	})

	const phase = ref('idle') // idle | starting | countdown | recording | paused | finishing | done | error
	const error = ref('')
	const countdownValue = ref(0)
	const elapsedMs = ref(0)
	const micMuted = ref(false)

	const cameras = ref([])
	const microphones = ref([])
	const cameraStream = shallowRef(null)
	const micStream = shallowRef(null)
	const screenStream = shallowRef(null)
	const recordedStream = shallowRef(null)
	const pipWindow = shallowRef(null)

	const recording = ref(null) // { name, share_id, share_url }
	const upload = reactive({ sentBytes: 0, totalBytes: 0, failed: false })

	const usesCamera = computed(() => settings.mode !== 'Screen')
	const usesScreen = computed(() => settings.mode !== 'Camera')
	const isActive = computed(() => ['countdown', 'recording', 'paused'].includes(phase.value))
	const isBusy = computed(
		() => ['starting', 'finishing'].includes(phase.value) || isActive.value
	)

	let mediaRecorder = null
	let compositor = null
	let audioContext = null
	let thumbnail = null
	let chunks = []
	let queue = []
	let nextChunkIndex = 0
	let pumping = null
	let lastUploadError = null
	let accumulatedMs = 0
	let segmentStartedAt = 0
	let timer = null
	let cancelled = false
	let cancelCountdown = null
	let finishedResolve = null

	// ---- devices & previews -------------------------------------------------

	async function refreshDevices() {
		const devices = await navigator.mediaDevices.enumerateDevices()
		cameras.value = devices.filter((d) => d.kind === 'videoinput' && d.deviceId)
		microphones.value = devices.filter((d) => d.kind === 'audioinput' && d.deviceId)
		if (settings.cameraId && !cameras.value.some((d) => d.deviceId === settings.cameraId))
			settings.cameraId = ''
		if (settings.micId && !microphones.value.some((d) => d.deviceId === settings.micId))
			settings.micId = ''
	}

	async function openCamera() {
		stopStream(cameraStream.value)
		cameraStream.value = null
		if (!usesCamera.value) return
		try {
			cameraStream.value = await navigator.mediaDevices.getUserMedia({
				video: {
					deviceId: settings.cameraId ? { exact: settings.cameraId } : undefined,
					width: { ideal: 1280 },
					height: { ideal: 720 },
				},
			})
		} catch (e) {
			error.value = `Camera unavailable: ${e.message}`
		}
	}

	async function openMicrophone() {
		stopStream(micStream.value)
		micStream.value = null
		if (!settings.micEnabled) return
		try {
			micStream.value = await navigator.mediaDevices.getUserMedia({
				audio: {
					deviceId: settings.micId ? { exact: settings.micId } : undefined,
					echoCancellation: true,
					noiseSuppression: true,
				},
			})
		} catch (e) {
			error.value = `Microphone unavailable: ${e.message}`
		}
	}

	async function preparePreview() {
		error.value = ''
		await Promise.all([openCamera(), openMicrophone()])
		// device labels are only exposed after a permission grant
		await refreshDevices()
	}

	watch(
		() => [settings.mode, settings.cameraId],
		() => !isBusy.value && openCamera().then(refreshDevices)
	)
	watch(
		() => [settings.micEnabled, settings.micId],
		() => !isBusy.value && openMicrophone().then(refreshDevices)
	)

	// ---- recording ----------------------------------------------------------

	async function start(title, folder = null) {
		if (isBusy.value) return
		error.value = ''
		phase.value = 'starting'
		cancelled = false
		resetUpload()

		try {
			if (usesScreen.value) {
				screenStream.value = await navigator.mediaDevices.getDisplayMedia({
					video: {
						displaySurface: 'monitor',
						frameRate: { ideal: 30 },
						width: { ideal: 1920 },
						height: { ideal: 1080 },
					},
					audio: settings.systemAudio,
					systemAudio: settings.systemAudio ? 'include' : 'exclude',
					surfaceSwitching: 'include',
					selfBrowserSurface: 'include',
				})
			}
			if (usesCamera.value && !cameraStream.value) await openCamera()
			if (settings.micEnabled && !micStream.value) await openMicrophone()
			if (settings.mode === 'Camera' && !cameraStream.value) {
				throw new Error(error.value || 'No camera available')
			}
		} catch (e) {
			stopStream(screenStream.value)
			screenStream.value = null
			phase.value = 'idle'
			if (e.name !== 'NotAllowedError' && e.name !== 'AbortError') error.value = e.message
			return
		}

		const sourceTrack = usesScreen.value
			? screenStream.value.getVideoTracks()[0]
			: cameraStream.value.getVideoTracks()[0]
		let videoTrack = sourceTrack
		if (settings.mode === 'Screen + Camera' && cameraStream.value) {
			// the bubble is drawn into the video itself, so it is there whatever is shared
			compositor = composeCameraBubble(sourceTrack, cameraStream.value.getVideoTracks()[0])
			videoTrack = compositor.track
		}
		recordedStream.value = new MediaStream([videoTrack, ...buildAudioTracks()])

		const mimeType = pickMimeType()
		try {
			recording.value = await call(`${API}.create_recording`, {
				title,
				folder,
				recording_mode: settings.mode,
				mime_type: mimeType || 'video/webm',
			})
		} catch (e) {
			teardownCapture()
			phase.value = 'idle'
			error.value = e?.messages?.[0] || e.message
			return
		}

		// the browser's own "Stop sharing" bar ends the recording too
		if (usesScreen.value) sourceTrack.addEventListener('ended', () => isActive.value && stop())

		await openFloatingControls().catch(() => {})

		if (settings.countdown) {
			phase.value = 'countdown'
			const finished = await runCountdown()
			if (!finished) return
		}
		if (cancelled) return

		mediaRecorder = new MediaRecorder(recordedStream.value, {
			mimeType: mimeType || undefined,
			videoBitsPerSecond: usesScreen.value ? 2_500_000 : 1_500_000,
			audioBitsPerSecond: 128_000,
		})
		mediaRecorder.ondataavailable = (event) => {
			if (!cancelled && event.data?.size) enqueueChunk(event.data)
		}
		mediaRecorder.onstop = () => !cancelled && finish()
		mediaRecorder.start(CHUNK_INTERVAL_MS)

		phase.value = 'recording'
		micMuted.value = false
		accumulatedMs = 0
		segmentStartedAt = performance.now()
		timer = setInterval(tick, 250)
		setTimeout(() => captureThumbnail(videoTrack), 1200)
	}

	function buildAudioTracks() {
		const sources = [
			...(settings.micEnabled ? micStream.value?.getAudioTracks() || [] : []),
			...(screenStream.value?.getAudioTracks() || []),
		]
		if (sources.length <= 1) return sources

		audioContext = new AudioContext()
		const destination = audioContext.createMediaStreamDestination()
		for (const track of sources) {
			audioContext.createMediaStreamSource(new MediaStream([track])).connect(destination)
		}
		return destination.stream.getAudioTracks()
	}

	function runCountdown() {
		return new Promise((resolve) => {
			countdownValue.value = 3
			const interval = setInterval(() => {
				countdownValue.value -= 1
				if (countdownValue.value <= 0) {
					clearInterval(interval)
					cancelCountdown = null
					resolve(true)
				}
			}, 1000)
			cancelCountdown = () => {
				clearInterval(interval)
				cancelCountdown = null
				resolve(false)
			}
		})
	}

	function skipCountdown() {
		if (phase.value !== 'countdown') return
		countdownValue.value = 1
	}

	function tick() {
		elapsedMs.value =
			accumulatedMs +
			(phase.value === 'recording' ? performance.now() - segmentStartedAt : 0)
	}

	function pause() {
		if (phase.value !== 'recording') return
		mediaRecorder.pause()
		accumulatedMs += performance.now() - segmentStartedAt
		phase.value = 'paused'
		tick()
	}

	function resume() {
		if (phase.value !== 'paused') return
		mediaRecorder.resume()
		segmentStartedAt = performance.now()
		phase.value = 'recording'
	}

	function toggleMute() {
		micMuted.value = !micMuted.value
		micStream.value?.getAudioTracks().forEach((track) => (track.enabled = !micMuted.value))
	}

	/** Resolves with the finished recording once every slice is uploaded. */
	function stop() {
		return new Promise((resolve) => {
			finishedResolve = resolve
			if (phase.value === 'countdown') {
				// nothing recorded yet: treat as cancel
				cancel().then(() => resolve(null))
				return
			}
			if (!mediaRecorder || mediaRecorder.state === 'inactive') return resolve(null)
			if (phase.value === 'recording') accumulatedMs += performance.now() - segmentStartedAt
			clearInterval(timer)
			elapsedMs.value = accumulatedMs
			phase.value = 'finishing'
			mediaRecorder.stop()
		})
	}

	async function finish() {
		phase.value = 'finishing'
		clearInterval(timer)
		teardownCapture()
		try {
			await drainQueue()
			const result = await call(`${API}.finalize_recording`, {
				recording: recording.value.name,
				duration_seconds: Math.round(elapsedMs.value / 100) / 10,
				thumbnail,
			})
			phase.value = 'done'
			finishedResolve?.({ ...recording.value, ...result })
		} catch (e) {
			upload.failed = true
			phase.value = 'error'
			error.value = e?.messages?.[0] || e.message || 'Upload failed'
			finishedResolve?.(null)
		}
	}

	async function retryUpload() {
		upload.failed = false
		error.value = ''
		await finish()
		return phase.value === 'done' ? recording.value : null
	}

	async function cancel() {
		cancelled = true
		cancelCountdown?.()
		clearInterval(timer)
		if (mediaRecorder && mediaRecorder.state !== 'inactive') mediaRecorder.stop()
		teardownCapture()
		queue = []
		const name = recording.value?.name
		recording.value = null
		phase.value = 'idle'
		elapsedMs.value = 0
		if (name) await call(`${API}.discard_recording`, { recording: name }).catch(() => {})
	}

	async function restart(title, folder) {
		await cancel()
		await start(title, folder)
	}

	/** Local safety net: the whole recording as a file, even if uploading failed. */
	function downloadLocalCopy() {
		const type = mediaRecorder?.mimeType || 'video/webm'
		const blob = new Blob(chunks, { type })
		const url = URL.createObjectURL(blob)
		const link = document.createElement('a')
		link.href = url
		link.download = `recording-${Date.now()}.${type.startsWith('video/mp4') ? 'mp4' : 'webm'}`
		link.click()
		setTimeout(() => URL.revokeObjectURL(url), 10_000)
	}

	function teardownCapture() {
		compositor?.stop()
		compositor = null
		stopStream(screenStream.value)
		screenStream.value = null
		recordedStream.value = null
		closeFloatingControls()
		audioContext?.close().catch(() => {})
		audioContext = null
	}

	function dispose() {
		if (isActive.value) cancel()
		teardownCapture()
		stopStream(cameraStream.value)
		stopStream(micStream.value)
		cameraStream.value = micStream.value = null
	}

	// ---- uploading ----------------------------------------------------------

	function resetUpload() {
		chunks = []
		queue = []
		nextChunkIndex = 0
		thumbnail = null
		elapsedMs.value = 0
		Object.assign(upload, { sentBytes: 0, totalBytes: 0, failed: false })
	}

	function enqueueChunk(blob) {
		chunks.push(blob)
		queue.push({ index: nextChunkIndex++, blob })
		upload.totalBytes += blob.size
		kickQueue()
	}

	function kickQueue() {
		if (pumping) return
		pumping = pumpQueue()
			.catch((e) => (lastUploadError = e))
			.finally(() => (pumping = null))
	}

	async function pumpQueue() {
		while (queue.length && !cancelled) {
			const item = queue[0]
			await uploadChunk(item)
			queue.shift()
			upload.sentBytes += item.blob.size
		}
	}

	async function drainQueue() {
		// the final slice arrives in the dataavailable event right before onstop
		lastUploadError = null
		kickQueue()
		while (pumping) await pumping
		if (queue.length) throw lastUploadError || new Error('Upload failed')
	}

	async function uploadChunk({ index, blob }) {
		for (let attempt = 0; ; attempt++) {
			try {
				const form = new FormData()
				form.append('recording', recording.value.name)
				form.append('chunk_index', index)
				form.append('chunk', blob, `chunk-${index}`)
				const response = await fetch(`/api/method/${API}.upload_chunk`, {
					method: 'POST',
					headers: {
						'X-Frappe-CSRF-Token': window.csrf_token,
						Accept: 'application/json',
					},
					body: form,
				})
				if (!response.ok) {
					const body = await response.json().catch(() => ({}))
					throw new Error(serverError(body) || `Upload failed (${response.status})`)
				}
				return
			} catch (e) {
				if (attempt >= UPLOAD_RETRIES || cancelled) throw e
				await sleep(1000 * 2 ** attempt)
			}
		}
	}

	async function captureThumbnail(track) {
		if (track.readyState !== 'live') return
		const video = document.createElement('video')
		video.muted = true
		video.playsInline = true
		video.srcObject = new MediaStream([track])
		try {
			await video.play()
			await sleep(200)
			const width = 960
			const height = Math.round((width * video.videoHeight) / video.videoWidth) || 540
			const canvas = document.createElement('canvas')
			canvas.width = width
			canvas.height = height
			canvas.getContext('2d').drawImage(video, 0, 0, width, height)
			thumbnail = canvas.toDataURL('image/jpeg', 0.8)
		} catch {
			// a missing thumbnail is not worth failing the recording over
		} finally {
			video.srcObject = null
		}
	}

	// ---- floating controls (Document Picture-in-Picture) --------------------

	/**
	 * Opens an always-on-top mini window with the stop/pause controls, so they
	 * stay reachable while the person works in other windows. (The camera is not
	 * shown there: it is already drawn into the recording.)
	 */
	async function openFloatingControls() {
		// camera-only recordings don't need it: the page itself is the preview
		if (!window.documentPictureInPicture || pipWindow.value || !usesScreen.value) return
		const size = { width: 320, height: 96 }

		const win = await window.documentPictureInPicture.requestWindow(size)
		for (const sheet of document.styleSheets) {
			try {
				const style = win.document.createElement('style')
				style.textContent = [...sheet.cssRules].map((rule) => rule.cssText).join('\n')
				win.document.head.appendChild(style)
			} catch {
				if (sheet.href) {
					const link = win.document.createElement('link')
					link.rel = 'stylesheet'
					link.href = sheet.href
					win.document.head.appendChild(link)
				}
			}
		}
		for (const attr of document.documentElement.attributes) {
			win.document.documentElement.setAttribute(attr.name, attr.value)
		}
		win.document.body.className = 'bg-surface-base m-0 overflow-hidden'
		win.addEventListener('pagehide', () => (pipWindow.value = null))
		pipWindow.value = win
	}

	function closeFloatingControls() {
		pipWindow.value?.close()
		pipWindow.value = null
	}

	return {
		settings,
		phase,
		error,
		countdownValue,
		elapsedMs,
		micMuted,
		cameras,
		microphones,
		cameraStream,
		micStream,
		screenStream,
		pipWindow,
		recording,
		upload,
		usesCamera,
		usesScreen,
		isActive,
		isBusy,
		preparePreview,
		refreshDevices,
		start,
		stop,
		pause,
		resume,
		cancel,
		restart,
		skipCountdown,
		toggleMute,
		retryUpload,
		downloadLocalCopy,
		openFloatingControls,
		dispose,
	}
}

function serverError(body) {
	try {
		if (body._server_messages) return JSON.parse(JSON.parse(body._server_messages)[0]).message
	} catch {
		// fall through
	}
	return body.exception || body.message
}
