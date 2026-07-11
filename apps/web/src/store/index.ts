import type { App } from "vue"
import { localStg } from "@/utils/storage"
import { setupThemeStore } from "@airalogy/composables"
import { initThemeSettings } from "@airalogy/composables/src/theme/shared"
import { createPinia } from "pinia"
import piniaPluginPersistedstate from "pinia-plugin-persistedstate"
import { darkThemeOverrides, lightThemeOverrides, themeOverrides } from "../theme/overrides"
import { resetSetupStore } from "./plugins"

/** Setup Vue store plugin pinia */
export function setupStore(app: App) {
  const isProd = import.meta.env.PROD
  const store = createPinia()

  store.use(resetSetupStore)
  store.use(piniaPluginPersistedstate)

  app.use(store)

  setupThemeStore({
    settings: initThemeSettings({
      isProd,
      themeSettings: localStg.get("themeSettings") || {} as Theme.ThemeSetting,
      isOverride: localStg.get("overrideThemeFlag") === BUILD_TIME || false,
    }),
    themeOverrides,
    lightThemeOverrides,
    darkThemeOverrides,
    cacheThemeSettings: (settings) => {
      if (isProd) {
        localStg.set("themeSettings", settings)
      }
    },
  })

  return store
}
