/**
 * Draws the screen with the camera as a round bubble in the bottom-left corner
 * onto a canvas, and exposes the canvas as a video track.
 *
 * The frame loop is driven by a Web Worker timer instead of requestAnimationFrame:
 * people switch to another tab or window to present, and browsers stop
 * requestAnimationFrame (and throttle page timers) in a background tab.
 */

const FPS = 30
const MAX_WIDTH = 1920
const BUBBLE_RATIO = 0.24 // bubble diameter as a share of the video height
const BUBBLE_MARGIN = 0.035

const TICKER_SOURCE = `
  let timer = null
  onmessage = (e) => {
    clearInterval(timer)
    if (e.data > 0) timer = setInterval(() => postMessage(0), e.data)
  }
`

function liveVideo(stream) {
  const video = document.createElement('video')
  video.muted = true
  video.playsInline = true
  video.srcObject = stream
  video.play().catch(() => {})
  return video
}

export function createCompositor(screenStream, cameraStream) {
  const settings = screenStream.getVideoTracks()[0].getSettings()
  const sourceWidth = settings.width || 1280
  const sourceHeight = settings.height || 720
  const scale = Math.min(1, MAX_WIDTH / sourceWidth)

  const canvas = document.createElement('canvas')
  // Even dimensions keep every video encoder happy.
  canvas.width = Math.round((sourceWidth * scale) / 2) * 2
  canvas.height = Math.round((sourceHeight * scale) / 2) * 2
  const ctx = canvas.getContext('2d', { alpha: false })

  const screen = liveVideo(screenStream)
  const camera = liveVideo(cameraStream)
  let bubbleVisible = true

  function draw() {
    const { width, height } = canvas
    if (screen.readyState >= 2) {
      ctx.drawImage(screen, 0, 0, width, height)
    } else {
      ctx.fillStyle = '#000'
      ctx.fillRect(0, 0, width, height)
    }
    if (!bubbleVisible || camera.readyState < 2 || !camera.videoWidth) return

    const diameter = Math.round(height * BUBBLE_RATIO)
    const margin = Math.round(height * BUBBLE_MARGIN)
    const cx = margin + diameter / 2
    const cy = height - margin - diameter / 2

    // Crop the camera to a centred square, then mirror it like a selfie view.
    const side = Math.min(camera.videoWidth, camera.videoHeight)
    const sx = (camera.videoWidth - side) / 2
    const sy = (camera.videoHeight - side) / 2

    ctx.save()
    ctx.beginPath()
    ctx.arc(cx, cy, diameter / 2, 0, Math.PI * 2)
    ctx.closePath()
    ctx.clip()
    ctx.translate(cx + diameter / 2, cy - diameter / 2)
    ctx.scale(-1, 1)
    ctx.drawImage(camera, sx, sy, side, side, 0, 0, diameter, diameter)
    ctx.restore()

    ctx.beginPath()
    ctx.arc(cx, cy, diameter / 2, 0, Math.PI * 2)
    ctx.lineWidth = Math.max(2, Math.round(height / 270))
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.92)'
    ctx.stroke()
  }

  const ticker = new Worker(URL.createObjectURL(new Blob([TICKER_SOURCE], { type: 'text/javascript' })))
  ticker.onmessage = draw
  draw()
  ticker.postMessage(1000 / FPS)

  const stream = canvas.captureStream(FPS)

  return {
    track: stream.getVideoTracks()[0],
    setBubbleVisible(visible) {
      bubbleVisible = visible
    },
    stop() {
      ticker.postMessage(0)
      ticker.terminate()
      stream.getTracks().forEach((t) => t.stop())
      screen.srcObject = null
      camera.srcObject = null
    },
  }
}
