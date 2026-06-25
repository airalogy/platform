import { locale } from "dayjs"
import { DEFAULT_LOCALE } from "./constants"
import "dayjs/locale/zh-cn"
import "dayjs/locale/en"

const localMap: Record<I18n.LangType, string> = {
  "zh-CN": "zh-cn",
  "en-US": "en",
}

/**
 * Set dayjs locale
 *
 * @param lang
 */
export function setDayjsLocale(lang: I18n.LangType = DEFAULT_LOCALE) {
  const l = lang

  locale(localMap[l])
}
