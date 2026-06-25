import type { App } from "vue"
import { createI18n } from "vue-i18n"
import { DEFAULT_LOCALE } from "./constants"
import messages from "./locale"

const i18n = createI18n({
  locale: DEFAULT_LOCALE,
  fallbackLocale: DEFAULT_LOCALE,
  messages: messages as any,
  legacy: false,
})

/**
 * Setup plugin i18n
 *
 * @param app
 */
export function setupI18n(app: App) {
  app.use(i18n)
}

export const $t = (i18n.global as any).t as I18n.$T

export function setLocale(locale: I18n.LangType) {
  i18n.global.locale.value = locale
}

export { DEFAULT_LOCALE, LOCALE_OPTIONS, SUPPORTED_LOCALES } from "./constants"
