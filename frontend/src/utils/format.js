export function formatDuration(seconds) {
	seconds = Math.max(0, Math.floor(Number(seconds) || 0))
	const h = Math.floor(seconds / 3600)
	const m = Math.floor((seconds % 3600) / 60)
	const s = String(seconds % 60).padStart(2, '0')
	return h ? `${h}:${String(m).padStart(2, '0')}:${s}` : `${m}:${s}`
}

export function formatBytes(bytes) {
	bytes = Number(bytes) || 0
	const units = ['B', 'KB', 'MB', 'GB']
	let i = 0
	while (bytes >= 1024 && i < units.length - 1) {
		bytes /= 1024
		i++
	}
	return `${bytes.toFixed(i ? 1 : 0)} ${units[i]}`
}

export function timeAgo(date) {
	if (!date) return ''
	const then = new Date(String(date).replace(' ', 'T'))
	const seconds = Math.round((Date.now() - then.getTime()) / 1000)
	const steps = [
		[60, 'second'],
		[60, 'minute'],
		[24, 'hour'],
		[7, 'day'],
		[4.35, 'week'],
		[12, 'month'],
		[Infinity, 'year'],
	]
	let value = seconds
	for (const [size, unit] of steps) {
		if (Math.abs(value) < size) {
			return new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' }).format(
				-Math.round(value),
				unit
			)
		}
		value /= size
	}
	return ''
}

export async function copyToClipboard(text) {
	try {
		await navigator.clipboard.writeText(text)
	} catch {
		const input = document.createElement('textarea')
		input.value = text
		document.body.appendChild(input)
		input.select()
		document.execCommand('copy')
		input.remove()
	}
}

export function errorMessage(error, fallback = 'Something went wrong') {
	return error?.messages?.[0] || error?.message || fallback
}
