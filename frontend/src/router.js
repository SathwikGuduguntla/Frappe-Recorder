import { createRouter, createWebHistory } from 'vue-router'
import { loadSession, redirectToLogin } from './session'

const routes = [
	{
		path: '/',
		name: 'Library',
		component: () => import('./pages/LibraryPage.vue'),
		meta: { requiresAuth: true },
	},
	{
		path: '/record',
		name: 'Record',
		component: () => import('./pages/RecordPage.vue'),
		meta: { requiresAuth: true },
	},
	{
		path: '/v/:shareId',
		name: 'Watch',
		component: () => import('./pages/WatchPage.vue'),
		props: true,
	},
	{
		path: '/settings',
		name: 'Settings',
		component: () => import('./pages/SettingsPage.vue'),
		meta: { requiresAuth: true },
	},
	{ path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
	history: createWebHistory('/recorder'),
	routes,
})

router.beforeEach(async (to) => {
	const session = await loadSession()
	if (to.meta.requiresAuth && session.isGuest) {
		redirectToLogin(router.resolve(to).href)
		return false
	}
})

export default router
