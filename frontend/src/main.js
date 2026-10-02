import { createApp } from 'vue'
import { FrappeUI, setConfig, frappeRequest } from 'frappe-ui'

import App from './App.vue'
import router from './router'
import './index.css'
import { getDeviceKey } from './utils/deviceKey'

setConfig('resourceFetcher', frappeRequest)
// identifies this browser as the owner of recordings made without logging in
setConfig('requestHeaders', () => ({ 'X-Recorder-Key': getDeviceKey() }))

createApp(App).use(router).use(FrappeUI).mount('#app')
