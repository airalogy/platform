import { extend } from "dayjs"
import duration from "dayjs/plugin/duration"
import localeData from "dayjs/plugin/localeData"
import timezone from "dayjs/plugin/timezone"
import utc from "dayjs/plugin/utc"
import { setDayjsLocale } from "../locales/dayjs"

export function setupDayjs() {
  // Extend with plugins
  extend(duration)
  extend(localeData)
  extend(utc)
  extend(timezone)

  setDayjsLocale()
}
