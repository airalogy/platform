import { createApp } from "vue"

import App from "./App.vue"
import { setupDirectives } from "./directives"

import { setupI18n } from "./locales"
import { setupDayjs } from "./plugins"
import { setupRouter } from "./router"
import { setupStore } from "./store"
import { registerUnauthorizedHandler } from "./utils/auth/unauthorized"
import "virtual:uno.css"
import "@styles/sass/global.sass"
import "@styles/css/global.css"
import "@airalogy/aimd-recorder/styles"

async function setupApp() {
  setupDayjs()

  const app = createApp(App)

  setupDirectives(app)
  setupStore(app)

  await setupRouter(app)
  registerUnauthorizedHandler()

  setupI18n(app)

  app.mount("#app")
}

void setupApp()
