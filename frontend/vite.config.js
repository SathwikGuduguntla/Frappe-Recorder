import path from 'path'
import vue from '@vitejs/plugin-vue'
import frappeui from 'frappe-ui/vite'
import { defineConfig } from 'vite'

export default defineConfig({
	plugins: [
		frappeui({
			// proxies /api, /files, /login… to the bench, injects boot data and
			// writes the built index.html to ../frappe_recorder/www/recorder.html
			frontendRoute: '/recorder',
			frappeProxy: true,
			jinjaBootData: true,
			lucideIcons: true,
			buildConfig: {
				outDir: '../frappe_recorder/public/frontend',
				baseUrl: '/assets/frappe_recorder/frontend/',
				indexHtmlPath: '../frappe_recorder/www/recorder.html',
			},
		}),
		vue(),
	],
	resolve: {
		alias: {
			'@': path.resolve(__dirname, 'src'),
		},
	},
	build: {
		target: 'es2022',
	},
})
