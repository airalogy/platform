/** Create color palette vars */
function createColorPaletteVars() {
  const colors: Theme.ThemeColorKey[] = ["primary", "info", "success", "warning", "error"]
  const colorPaletteNumbers: Theme.ColorPaletteNumber[] = [
    50,
    100,
    200,
    300,
    400,
    500,
    600,
    700,
    800,
    900,
    950,
  ]

  const colorPaletteVar = {} as Theme.ThemePaletteColor

  colors.forEach((color) => {
    colorPaletteVar[color] = `rgb(var(--${color}-color))`
    colorPaletteNumbers.forEach((number) => {
      colorPaletteVar[`${color}-${number}`] = `rgb(var(--${color}-${number}-color))`
    })
  })

  return colorPaletteVar
}

const colorPaletteVars = createColorPaletteVars()

/**
 *     colors: {
      primary: {
        DEFAULT: "#1A79FF",
        hover: "#4181FD",
        pressed: "#1454D4",
        disabled: "#A0C0FE",
      },
      text: {
        base: "#333333",
        primary: "#333333",
        secondary: "#666666",
      },
      button: {
        "ghost": "#666666",
        "ghost-hover": "#4181FD",
        "ghost-pressed": "#1454D4",
        "ghost-disabled": "#BCBCBC",
      },
      input: {
        bg: "#F7F8F9",
        focus: "#FFFFFF",
      },
      table: {
        header: "#F3F5F9",
      },
      border: {
        upload: "#EAECF0",
        disabled: "#E5E6EB",
      },
    },
 */
/** Theme vars */
export const themeVars: Theme.ThemeSettingToken = {
  colors: {
    ...colorPaletteVars,
    "nprogress": "rgb(var(--nprogress-color))",
    "container": "rgb(var(--container-bg-color))",
    "layout": "rgb(var(--layout-bg-color))",
    "inverted": "rgb(var(--inverted-bg-color))",
    "base-text": "rgb(var(--base-text-color))",
    "text-secondary": "rgb(var(--text-secondary-color))",
    "button": {
      "ghost": "#666666",
      "ghost-hover": "#4181FD",
      "ghost-pressed": "#1454D4",
      "ghost-disabled": "#BCBCBC",
    },
    "input": {
      bg: "#F7F8F9",
      focus: "#FFFFFF",
    },
    "table": {
      header: "#F3F5F9",
    },
    // "border": {
    //   upload: "#EAECF0",
    //   disabled: "#E5E6EB",
    // },
    "border": "rgb(var(--border-color))",
    "border-hover": "rgb(var(--border-hover-color))",
    "border-focus": "rgb(var(--border-focus-color))",
  },
  boxShadow: {
    header: "var(--header-box-shadow)",
    sider: "var(--sider-box-shadow)",
    tab: "var(--tab-box-shadow)",
  },
}
export const breakpoints = Object.freeze({
  "sm": 640,
  "md": 768,
  "lg": 1024,
  "xl": 1280,
  "2xl": 1536,
})
