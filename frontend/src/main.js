import { createApp } from 'vue'
import { FrappeUI, frappeRequest, setConfig } from 'frappe-ui'
import App from './App.vue'
import router from './router'
import './index.css'

setConfig('resourceFetcher', frappeRequest)

createApp(App).use(FrappeUI).use(router).mount('#app')
