import dayjs from "dayjs"

/**
 * All duration components are numbers.
 * Example: "P1Y2M3DT4H5M6.7S" ->
 * { years: 1, months: 2, weeks: 0, days: 3, hours: 4, minutes: 5, seconds: 6.7 }
 */
export interface ISODuration {
  years: number
  months: number
  weeks: number
  days: number
  hours: number
  minutes: number
  seconds: number
}

/**
 * Parses a full ISO 8601 duration string into its components.
 * Supports P[n]Y[n]M[n]W[n]DT[n]H[n]M[n]S format, including decimal values.
 * @param duration - ISO 8601 duration string (e.g., "P1DT12H", "PT0.5S").
 * @returns An object with all duration components (years, months, etc.), or null if the format is invalid.
 */
export function parseISODurationWithoutDate(duration?: string): ISODuration | null {
  if (!duration) {
    return null
  }

  // This regex combines the best of all approaches:
  // - It supports the full P...T... spec (Y, M, W, D, H, M, S).
  // - It uses non-capturing groups `(?:...)` for structure, and captures only the numeric values.
  // - It uses a negative lookahead `(?!$)` to ensure "P" is not the only character.
  // - It uses a positive lookahead `(?=\d)` to ensure "T" is followed by a number, invalidating "PT".
  // - It supports both `.` and `,` as decimal separators.
  const iso8601DurationRegex
    = /^P(?!$)(?:(\d+(?:[.,]\d+)?)Y)?(?:(\d+(?:[.,]\d+)?)M)?(?:(\d+(?:[.,]\d+)?)W)?(?:(\d+(?:[.,]\d+)?)D)?(?:T(?=\d)(?:(\d+(?:[.,]\d+)?)H)?(?:(\d+(?:[.,]\d+)?)M)?(?:(\d+(?:[.,]\d+)?)S)?)?$/

  const matches = duration.match(iso8601DurationRegex)

  // The regex is strict enough that if it doesn't match, the format is invalid.
  if (!matches) {
    return null
  }

  // Helper to parse matched string to a float, supporting both '.' and ',' as decimal separators.
  const parseFloatWithComma = (value: string | undefined): number => {
    if (!value)
      return 0
    return Number.parseFloat(value.replace(",", "."))
  }

  // Capture groups are indexed from 1.
  // [1]: Years, [2]: Months, [3]: Weeks, [4]: Days
  // [5]: Hours, [6]: Minutes, [7]: Seconds
  return {
    years: parseFloatWithComma(matches[1]),
    months: parseFloatWithComma(matches[2]),
    weeks: parseFloatWithComma(matches[3]),
    days: parseFloatWithComma(matches[4]),
    hours: parseFloatWithComma(matches[5]),
    minutes: parseFloatWithComma(matches[6]),
    seconds: parseFloatWithComma(matches[7]),
  }
}
/**
 * Parse ISO 8601 duration string to time components
 * @param duration - ISO 8601 duration string (e.g., "PT1H30M45S")
 * @returns Object with hours, minutes, seconds, formatted string, and date
 */
export function parseISODuration(duration?: string) {
  // Updated regex to support fractional seconds (e.g., PT0.5S, PT0.001S)
  const parsed = parseISODurationWithoutDate(duration)
  if (!parsed) {
    return null
  }

  const { years, months, days, hours, minutes, seconds, ...rest } = parsed

  // Format hours, minutes and seconds manually to preserve hours > 24
  const formattedHours = hours.toString().padStart(2, "0")
  const formattedMinutes = minutes.toString().padStart(2, "0")
  const formattedSeconds = seconds.toString().padStart(2, "0")
  const formatted = `${formattedHours}:${formattedMinutes}:${formattedSeconds}`

  // Create date object for compatibility, but note it will wrap hours > 24
  const date = dayjs().year(years).month(months).date(days).hour(hours).minute(minutes).second(seconds).toDate()

  return { years, months, days, hours, minutes, seconds, formatted, date, ...rest }
}

/**
 * Convert time string to ISO 8601 duration
 * @param date - Time string in format "HH:MM:SS"
 * @returns ISO 8601 duration string
 */
export function dateMillisecondsToISODuration(date: string): string {
  const [hours, minutes, seconds] = date.split(":").map(n => Number.parseInt(n, 10))

  return numberToISODuration(hours, minutes, seconds)
}

/**
 * Convert time components to ISO 8601 duration string
 * @param hours - Hours component
 * @param minutes - Minutes component
 * @param seconds - Seconds component
 * @returns ISO 8601 duration string
 */
export function numberToISODuration(hours: number, minutes: number, seconds: number): string {
  // Build ISO 8601 duration string
  let isoDuration = "P"
  if (hours > 0 || minutes > 0 || seconds > 0) {
    isoDuration += "T"
    if (hours > 0)
      isoDuration += `${hours}H`
    if (minutes > 0)
      isoDuration += `${minutes}M`
    if (seconds > 0)
      isoDuration += `${seconds}S`
  }

  return isoDuration
}
