import { createApp } from "vue";
import router from "./router";
import App from "./App.vue";
import "./index.css"; // Ensure Tailwind utilities are loaded

// Explicitly import FrappeUI base setup plugin wrapper
import { FrappeUI, setConfig, frappeRequest } from "frappe-ui";

const app = createApp(App);

// 1. Register FrappeUI core components & directives layout bounds
app.use(FrappeUI);

// 2. Configure base application fetch settings globally 
setConfig("resourceFetcher", frappeRequest);

// 3. Bind client router definitions
app.use(router);

// 4. Mount application DOM root shell node
app.mount("#app");