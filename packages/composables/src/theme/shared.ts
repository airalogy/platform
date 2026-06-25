import type { GlobalThemeOverrides } from "naive-ui"
import { getColorPalette, getPaletteColorByNumber, themeVars } from "@airalogy/shared/theme"
import { addColorAlpha, getRgb } from "@airalogy/shared/theme/color/colord"
import { defaultsDeep } from "lodash-es"

const DARK_CLASS = "dark"
/**
 * Theme schemes (only light mode is supported now)
 * @deprecated Dark and auto modes have been removed
 */
export const themeSchemes: Theme.ThemeScheme[] = ["light"]

/** Init theme settings */
export function initThemeSettings(options: { isProd: boolean, themeSettings?: Theme.ThemeSetting, isOverride?: boolean, overrideThemeSettings?: Theme.ThemeSetting }) {
  const { isProd, themeSettings, isOverride, overrideThemeSettings } = options

  // if it is development mode, the theme settings will not be cached, by update `themeSettings` in `src/theme/settings.ts` to update theme settings
  if (!isProd) {
    return themeSettings
  }

  // if it is production mode, the theme settings will be cached in localStorage
  // if want to update theme settings when publish new version, please update `overrideThemeSettings` in `src/theme/settings.ts`

  let settings = themeSettings

  if (!isOverride) {
    settings = defaultsDeep(overrideThemeSettings, settings)
  }

  return settings
}

/**
 * Create theme token
 *
 * @param colors Theme colors
 */
export function createThemeToken(colors: Theme.ThemeColor, tokens: Theme.ThemeSetting["tokens"]) {
  const paletteColors = createThemePaletteColors(colors)

  const { light } = tokens
  const themeTokens: Theme.ThemeTokenCSSVars = {
    colors: {
      ...paletteColors,
      nprogress: paletteColors.primary,
      ...light.colors,
    },
    boxShadow: {
      ...light.boxShadow,
    },
  }

  // Dark theme has been removed, only return light theme tokens
  return {
    themeTokens,
  }
}

/**
 * Create theme palette colors
 *
 * @param colors Theme colors
 */
function createThemePaletteColors(colors: Theme.ThemeColor) {
  const colorKeys = Object.keys(colors) as Theme.ThemeColorKey[]
  const colorPaletteVar = {} as Theme.ThemePaletteColor

  colorKeys.forEach((key) => {
    const colorMap = getColorPalette(colors[key])

    colorPaletteVar[key] = colorMap.get(500)!

    colorMap.forEach((hex, number) => {
      colorPaletteVar[`${key}-${number}`] = hex
    })
  })

  return colorPaletteVar
}

export function removeVarPrefix(value: string) {
  return value.replace("var(", "").replace(")", "")
}

export function removeRgbPrefix(value: string) {
  return value.replace("rgb(", "").replace(")", "")
}
/**
 * Get css var by tokens
 *
 * @param tokens Theme base tokens
 */
function getCssVarByTokens(tokens: Theme.BaseToken, source = themeVars, path?: string[]) {
  const styles: string[] = []

  for (const [key, tokenValues] of Object.entries(source)) {
    for (const [tokenKey, tokenValue] of Object.entries(tokenValues)) {
      if (typeof tokenValue === "object") {
        continue
      }
      let cssVarsKey = removeVarPrefix(tokenValue as string)
      let cssValue = tokens[key][tokenKey]

      if (key === "colors") {
        cssVarsKey = removeRgbPrefix(cssVarsKey)
        const { r, g, b } = getRgb(cssValue)
        cssValue = `${r} ${g} ${b}`
      }

      styles.push(`${cssVarsKey}: ${cssValue}`)
    }
  }

  const styleStr = styles.join(";")

  return styleStr
}

/**
 * Add theme vars to html
 * Dark theme has been removed, only light theme is applied
 *
 * @param tokens
 */
export function addThemeVarsToGlobal(tokens: Theme.BaseToken, _darkTokens?: Theme.BaseToken) {
  const cssVarStr = getCssVarByTokens(tokens)

  const css = `
    :root {
      ${cssVarStr}
    }
  `

  // Dark theme has been removed, no longer apply dark styles
  const styleId = "theme-vars"

  const style = document.querySelector(`#${styleId}`) || document.createElement("style")

  style.id = styleId

  style.textContent = css

  document.head.appendChild(style)
}

/**
 * Toggle css dark mode (DEPRECATED - dark mode has been removed)
 * Kept for backward compatibility but does nothing except ensure dark class is removed
 *
 * @deprecated Dark mode has been removed from the project
 */
export function toggleCssDarkMode(_darkMode = false) {
  // Dark mode functionality has been removed
  // Ensure dark class is always removed
  document.documentElement.classList.remove(DARK_CLASS)
}

type NaiveColorScene = "" | "Suppl" | "Hover" | "Pressed" | "Active"
type NaiveColorKey = `${Theme.ThemeColorKey}Color${NaiveColorScene}`
type NaiveThemeColor = Partial<Record<NaiveColorKey, string>>
interface NaiveColorAction {
  scene: NaiveColorScene
  handler: (color: string) => string
}

/**
 * Get naive theme colors
 *
 * @param colors Theme colors
 */
function getNaiveThemeColors(colors: Theme.ThemeColor) {
  const colorActions: NaiveColorAction[] = [
    { scene: "", handler: color => color },
    { scene: "Suppl", handler: color => color },
    { scene: "Hover", handler: color => getPaletteColorByNumber(color, 400) },
    { scene: "Pressed", handler: color => getPaletteColorByNumber(color, 700) },
    { scene: "Active", handler: color => addColorAlpha(color, 0.1) },
  ]

  const themeColors: NaiveThemeColor = {}

  const colorEntries = Object.entries(colors) as [Theme.ThemeColorKey, string][]

  colorEntries.forEach((color) => {
    colorActions.forEach((action) => {
      const [colorType, colorValue] = color
      const colorKey: NaiveColorKey = `${colorType}Color${action.scene}`
      themeColors[colorKey] = action.handler(colorValue)
    })
  })

  return themeColors
}

/**
 * Get naive theme
 *
 * @param colors Theme colors
 */
export function getNaiveTheme(options: { colors: Theme.ThemeColor, isDarkMode?: boolean, themeOverrides?: GlobalThemeOverrides, darkThemeOverrides?: GlobalThemeOverrides, lightThemeOverrides?: GlobalThemeOverrides }) {
  const { colors, themeOverrides, lightThemeOverrides } = options
  // isDarkMode and darkThemeOverrides are deprecated but kept for backward compatibility
  const { primary: colorLoading } = colors

  const theme: GlobalThemeOverrides = {
    common: {
      ...getNaiveThemeColors(colors),
    },
    LoadingBar: {
      colorLoading,
    },
  }

  // Dark mode has been removed, always use light theme overrides
  return defaultsDeep(theme, themeOverrides, lightThemeOverrides)
}
