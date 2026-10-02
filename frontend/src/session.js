import { reactive } from 'vue'
import { call } from 'frappe-ui'

export const session = reactive({
	ready: false,
	user: 'Guest',
	isGuest: true,
	fullName: '',
	userImage: null,
	isSystemManager: false,
	driveEnabled: false,
})

let loading = null

export function loadSession() {
	if (!loading) {
		loading = call('frappe_recorder.api.recording.get_boot').then((boot) => {
			Object.assign(session, {
				ready: true,
				user: boot.user,
				isGuest: boot.is_guest,
				fullName: boot.full_name || '',
				userImage: boot.user_image || null,
				isSystemManager: Boolean(boot.is_system_manager),
				driveEnabled: Boolean(boot.drive_enabled),
			})
			return session
		})
	}
	return loading
}

export function redirectToLogin(path = window.location.pathname) {
	window.location.href = `/login?redirect-to=${encodeURIComponent(path)}`
}

export async function logout() {
	await call('logout')
	window.location.href = '/login'
}
