/**
 * Draws the camera as a round bubble in the bottom-left corner of the screen
 * video, so "Screen + Camera" recordings include the camera even when only a
 * window or a tab is shared.
 *
 * Chromium browsers process frames with insertable streams: drawing is driven
 * by the screen's own frames, so it keeps running while this tab is in the
 * background (the person is busy in the window they share). Elsewhere it falls
 * back to a canvas whose redraws are timed from a worker, whose timers are not
 * throttled in background tabs the way the page's are.
 */
export function composeCameraBubble(screenTrack, cameraTrack) {
	if ('MediaStreamTrackProcessor' in window && 'MediaStreamTrackGenerator' in window) {
		return insertableStreamsCompositor(screenTrack, cameraTrack)
	}
	return canvasCompositor(screenTrack, cameraTrack)
}

function drawBubble(ctx, camera, cameraWidth, cameraHeight, width, height) {
	const size = Math.round(Math.min(width, height) * 0.24)
	const margin = Math.round(size * 0.15)
	const x = margin
	const y = height - size - margin
	const side = Math.min(cameraWidth, cameraHeight)
	const sx = (cameraWidth - side) / 2
	const sy = (cameraHeight - side) / 2

	ctx.save()
	ctx.beginPath()
	ctx.arc(x + size / 2, y + size / 2, size / 2, 0, Math.PI * 2)
	ctx.clip()
	// mirrored, like the preview: people expect to see themselves as in a mirror
	ctx.translate(x + size, y)
	ctx.scale(-1, 1)
	ctx.drawImage(camera, sx, sy, side, side, 0, 0, size, size)
	ctx.restore()

	ctx.beginPath()
	ctx.arc(x + size / 2, y + size / 2, size / 2, 0, Math.PI * 2)
	ctx.lineWidth = Math.max(2, Math.round(size * 0.03))
	ctx.strokeStyle = 'rgba(255, 255, 255, 0.85)'
	ctx.stroke()
}

function insertableStreamsCompositor(screenTrack, cameraTrack) {
	const screenReader = new window.MediaStreamTrackProcessor({
		track: screenTrack,
	}).readable.getReader()
	const cameraReader = new window.MediaStreamTrackProcessor({
		track: cameraTrack,
	}).readable.getReader()
	const generator = new window.MediaStreamTrackGenerator({ kind: 'video' })
	const writer = generator.writable.getWriter()
	const canvas = new OffscreenCanvas(2, 2)
	const ctx = canvas.getContext('2d')
	let cameraFrame = null
	let stopped = false

	async function readCamera() {
		while (!stopped) {
			const { value, done } = await cameraReader.read()
			if (done) break
			cameraFrame?.close()
			cameraFrame = value
		}
	}

	async function compose() {
		while (!stopped) {
			const { value: frame, done } = await screenReader.read()
			if (done) break
			const width = frame.displayWidth
			const height = frame.displayHeight
			if (canvas.width !== width || canvas.height !== height) {
				canvas.width = width
				canvas.height = height
			}
			ctx.drawImage(frame, 0, 0, width, height)
			if (cameraFrame) {
				drawBubble(
					ctx,
					cameraFrame,
					cameraFrame.displayWidth,
					cameraFrame.displayHeight,
					width,
					height
				)
			}
			const output = new VideoFrame(canvas, { timestamp: frame.timestamp })
			frame.close()
			try {
				await writer.write(output)
			} catch {
				output.close()
				break
			}
		}
	}

	readCamera().catch(() => {})
	compose()
		.catch(() => {})
		.finally(() => stop())

	function stop() {
		if (stopped) return
		stopped = true
		screenReader.cancel().catch(() => {})
		cameraReader.cancel().catch(() => {})
		cameraFrame?.close()
		cameraFrame = null
		generator.stop()
	}

	return { track: generator, stop }
}

function canvasCompositor(screenTrack, cameraTrack) {
	const screen = videoFor(screenTrack)
	const camera = videoFor(cameraTrack)
	const settings = screenTrack.getSettings()
	const canvas = document.createElement('canvas')
	canvas.width = settings.width || 1920
	canvas.height = settings.height || 1080
	const ctx = canvas.getContext('2d')

	function draw() {
		if (
			screen.videoWidth &&
			(canvas.width !== screen.videoWidth || canvas.height !== screen.videoHeight)
		) {
			canvas.width = screen.videoWidth
			canvas.height = screen.videoHeight
		}
		ctx.drawImage(screen, 0, 0, canvas.width, canvas.height)
		if (camera.videoWidth) {
			drawBubble(
				ctx,
				camera,
				camera.videoWidth,
				camera.videoHeight,
				canvas.width,
				canvas.height
			)
		}
	}

	const ticker = new Worker(
		URL.createObjectURL(
			new Blob(['setInterval(() => postMessage(0), 1000 / 30)'], { type: 'text/javascript' })
		)
	)
	ticker.onmessage = draw
	const track = canvas.captureStream(30).getVideoTracks()[0]

	function stop() {
		ticker.terminate()
		track.stop()
		screen.srcObject = null
		camera.srcObject = null
	}

	return { track, stop }
}

function videoFor(track) {
	const video = document.createElement('video')
	video.muted = true
	video.playsInline = true
	video.srcObject = new MediaStream([track])
	video.play().catch(() => {})
	return video
}
