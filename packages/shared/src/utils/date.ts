import dayjs, { type ConfigType } from "dayjs"
import relativeTime from "dayjs/plugin/relativeTime"

dayjs.extend(relativeTime)

export type DateFormatStyle =
  | "date"
  | "date-short"
  | "date-time"
  | "date-time-minute"
  | "month"
  | "month-day"
  | "month-year"

const DATE_FORMATS: Record<DateFormatStyle, { en: string, zh: string }> = {
  date: {
    en: "MMM D, YYYY",
    zh: "YYYY年M月D日",
  },
  "date-short": {
    en: "YYYY-MM-DD",
    zh: "YYYY年M月D日",
  },
  "date-time": {
    en: "YYYY-MM-DD HH:mm:ss",
    zh: "YYYY年M月D日 HH:mm:ss",
  },
  "date-time-minute": {
    en: "YYYY-MM-DD HH:mm",
    zh: "YYYY年M月D日 HH:mm",
  },
  month: {
    en: "MMMM",
    zh: "M月",
  },
  "month-day": {
    en: "MMM D",
    zh: "M月D日",
  },
  "month-year": {
    en: "MMMM YYYY",
    zh: "YYYY年M月",
  },
}

function isZhLocale(): boolean {
  return dayjs.locale().toLowerCase().startsWith("zh")
}

function resolveDateFormat(style: DateFormatStyle): string {
  const formats = DATE_FORMATS[style]
  return isZhLocale() ? formats.zh : formats.en
}

export function formatDate(dateInput: ConfigType, style: DateFormatStyle = "date-time"): string {
  return dayjs(dateInput).format(resolveDateFormat(style))
}

export function formatDistanceToNow(date: Date): string {
  return dayjs(date).fromNow()
}
