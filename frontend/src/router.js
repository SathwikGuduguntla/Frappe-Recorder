import { createRouter, createWebHistory } from 'vue-router'
import Home from './pages/Home.vue' // Add this import

const routes = [
  {
    path: '/',
    name: 'Home',
    component: Home
  },
  {
    path: '/library',
    name: 'Library',
    component: () => import('./pages/Library.vue'),
  },
  {
    path: '/record',
    name: 'Record',
    component: () => import('./pages/Record.vue'),
  },
  {
    path: '/share/:route',
    name: 'Share',
    component: () => import('./pages/Share.vue'),
    meta: { isPublic: true }
  }
]

const router = createRouter({
  history: createWebHistory('/recorder'),
  routes,
})

export default router