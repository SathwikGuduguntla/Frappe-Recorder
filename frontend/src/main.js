import { createApp } from 'vue'
import { FrappeUI, setConfig, frappeRequest } from 'frappe-ui'

import App from './App.vue'
import router from './router'
import './index.css'

setConfig('resourceFetcher', frappeRequest)

createApp(App).use(router).use(FrappeUI).mount('#app')
