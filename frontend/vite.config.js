import path from 'path'
import vue from '@vitejs/plugin-vue'
import frappeui from 'frappe-ui/vite'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [
    frappeui({
      frappeProxy: true,
      jinjaBootData: true,
      buildConfig: {
        outDir: '../frappe_recorder/public/frontend',
        indexHtmlPath: '../frappe_recorder/www/recorder.html',
      },
    }),
    vue(),
  ],
  // The AI models run in module workers (see src/ai), which import packages.
  worker: { format: 'es' },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
})
