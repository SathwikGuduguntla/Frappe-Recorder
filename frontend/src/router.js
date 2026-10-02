import { createRouter, createWebHistory } from 'vue-router'
import { loadSession } from '@/api'

const routes = [
  { path: '/recorder', name: 'Record', component: () => import('@/pages/Record.vue') },
  { path: '/recorder/library', name: 'Library', component: () => import('@/pages/Library.vue') },
  {
    path: '/recorder/settings',
    name: 'Settings',
    component: () => import('@/pages/Settings.vue'),
    meta: { managerOnly: true },
  },
  // The share link. Open to anyone who has it.
  { path: '/r/:token', name: 'Watch', component: () => import('@/pages/Watch.vue'), meta: { isPublic: true } },
  { path: '/recorder/:pathMatch(.*)*', redirect: { name: 'Record' } },
]

const router = createRouter({
  history: createWebHistory('/'),
  routes,
})

router.beforeEach(async (to) => {
  if (to.meta.isPublic) return true
  const session = await loadSession()
  if (!session.user) {
    window.location.href = `/login?redirect-to=${encodeURIComponent(to.fullPath)}`
    return false
  }
  if (to.meta.managerOnly && !session.is_manager) return { name: 'Record' }
  return true
})

export default router
