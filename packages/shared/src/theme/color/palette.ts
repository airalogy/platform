import type { AnyColor, HsvColor } from "colord"
import { getHex, getHsv, getHue, getSaturation, getValue, isValidColor, lightColorCount, mixColor } from "./colord"

/** Map of dark color index and opacity */
const darkColorMap = [
  { index: 7, opacity: 0.15 },
  { index: 6, opacity: 0.25 },
  { index: 5, opacity: 0.3 },
  { index: 5, opacity: 0.45 },
  { index: 5, opacity: 0.65 },
  { index: 5, opacity: 0.85 },
  { index: 5, opacity: 0.9 },
  { index: 4, opacity: 0.93 },
  { index: 3, opacity: 0.95 },
  { index: 2, opacity: 0.97 },
  { index: 1, opacity: 0.98 },
]

type ColorIndex = 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11
/**
 * Get palette color by index
 *
 * @param color - Color
 * @param index - The color index of color palette (the main color index is 6)
 * @returns Hex color
 */
export function getPaletteColorByIndex(color: AnyColor, index: ColorIndex): string {
  if (!isValidColor(color)) {
    throw new Error("invalid input color value")
  }

  if (index === 6) {
    return getHex(color)
  }

  const isLight = index < 6
  const hsv = getHsv(color)
  const i = isLight ? lightColorCount + 1 - index : index - lightColorCount - 1

  const newHsv: HsvColor = {
    h: getHue(hsv, i, isLight),
    s: getSaturation(hsv, i, isLight),
    v: getValue(hsv, i, isLight),
  }

  return getHex(newHsv)
}

/**
 * Get color palette
 *
 * @param color - Color
 * @param darkTheme - Dark theme
 * @param darkThemeMixColor - Dark theme mix color (default: #141414)
 */
export function getDefaultColorPalette(color: AnyColor, darkTheme = false, darkThemeMixColor = "#141414"): string[] {
  const indexes: ColorIndex[] = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]

  const patterns = indexes.map(index => getPaletteColorByIndex(color, index))

  if (darkTheme) {
    const darkPatterns = darkColorMap.map(({ index, opacity }) => {
      const darkColor = mixColor(darkThemeMixColor, patterns[index], opacity)

      return darkColor
    })

    return darkPatterns.map(item => getHex(item))
  }

  return patterns
}

/**
 * get color palette by provided color
 *
 * @param color
 */
export function getColorPalette(color: AnyColor) {
  const colorMap = new Map<Theme.ColorPaletteNumber, string>()

  const colors = getDefaultColorPalette(color)

  const colorNumbers: Theme.ColorPaletteNumber[] = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950]

  colorNumbers.forEach((number, index) => {
    colorMap.set(number, colors[index])
  })

  return colorMap
}

/**
 * get color palette color by number
 *
 * @param color the provided color
 * @param number the color palette number
 */
export function getPaletteColorByNumber(color: AnyColor, number: Theme.ColorPaletteNumber) {
  const colorMap = getColorPalette(color)

  return colorMap.get(number as Theme.ColorPaletteNumber)!
}
