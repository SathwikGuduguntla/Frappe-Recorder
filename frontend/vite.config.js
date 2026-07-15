import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 8080, // Frontend dev server
    proxy: {
      '^/(api|files|assets)': {
        target: 'http://localhost:8000', //  Points straight to your local running Frappe backend
        changeOrigin: true,
      },
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    outDir: '../frappe_recorder/public/frontend',
    emptyOutDir: true,
    commonjsOptions: {
      include: [/feather-icons/, /node_modules/],
    },
  },
  optimizeDeps: {
    include: ['frappe-ui > feather-icons', 'showdown', 'engine.io-client'],
  },
})