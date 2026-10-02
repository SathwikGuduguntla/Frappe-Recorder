const STORAGE_KEY = 'frappe_recorder_device_key'
let memoryKey = null

/**
 * A random key that identifies this browser. Recordings made without logging in
 * belong to whoever holds the key, so it stays in this browser only.
 */
export function getDeviceKey() {
	try {
		let key = localStorage.getItem(STORAGE_KEY)
		if (!key) {
			key = newKey()
			localStorage.setItem(STORAGE_KEY, key)
		}
		return key
	} catch {
		// storage blocked (private mode): the key lasts as long as the page
		memoryKey = memoryKey || newKey()
		return memoryKey
	}
}

function newKey() {
	const bytes = crypto.getRandomValues(new Uint8Array(24))
	return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
}
