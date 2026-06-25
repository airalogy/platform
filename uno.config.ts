import type { Preset } from "@unocss/core"
import type { Theme } from "@unocss/preset-uno"
import presetUno from "@unocss/preset-uno"
import transformerDirectives from "@unocss/transformer-directives"
import transformerVariantGroup from "@unocss/transformer-variant-group"
import { defineConfig } from "@unocss/vite"
import { breakpoints, themeVars } from "./packages/shared/src/theme/themeVars"

function presetAIRA(): Preset<Theme> {
  const preset: Preset<Theme> = {
    name: "preset-aira",
    shortcuts: [
      {
        "flex-center": "flex justify-center items-center",
        "flex-x-center": "flex justify-center",
        "flex-y-center": "flex items-center",
        "flex-vertical": "flex flex-col",
        "flex-vertical-center": "flex-center flex-col",
        "flex-vertical-stretch": "flex-vertical items-stretch",
        "i-flex-center": "inline-flex justify-center items-center",
        "i-flex-x-center": "inline-flex justify-center",
        "i-flex-y-center": "inline-flex items-center",
        "i-flex-vertical": "inline-flex flex-col",
        "i-flex-vertical-stretch": "i-flex-vertical items-stretch",
        "flex-1-hidden": "flex-1 overflow-hidden",
      },
      {
        "absolute-lt": "absolute left-0 top-0",
        "absolute-lb": "absolute left-0 bottom-0",
        "absolute-rt": "absolute right-0 top-0",
        "absolute-rb": "absolute right-0 bottom-0",
        "absolute-tl": "absolute-lt",
        "absolute-tr": "absolute-rt",
        "absolute-bl": "absolute-lb",
        "absolute-br": "absolute-rb",
        "absolute-center": "absolute-lt flex-center size-full",
        "absolute-x-center": "absolute left-1/2 -translate-x-1/2",
        "absolute-y-center": "absolute top-1/2 -translate-y-1/2",
        "fixed-lt": "fixed left-0 top-0",
        "fixed-lb": "fixed left-0 bottom-0",
        "fixed-rt": "fixed right-0 top-0",
        "fixed-rb": "fixed right-0 bottom-0",
        "fixed-tl": "fixed-lt",
        "fixed-tr": "fixed-rt",
        "fixed-bl": "fixed-lb",
        "fixed-br": "fixed-rb",
        "fixed-center": "fixed-lt flex-center size-full",
      },
      {
        "nowrap-hidden": "overflow-hidden whitespace-nowrap",
        "ellipsis-text": "nowrap-hidden text-ellipsis",
      },
      {
        "router-link": "underline decoration-solid text-[#1161FC]",
      },
    ],
  }

  return preset
}

const breakpointsWithUnit = Object.fromEntries(Object.entries(breakpoints).map(([key, value]) => [key, `${value}px`]))
export default defineConfig<Theme>({
  safelist: [
    "bg-amber-100",
    "text-amber-700",
    "dark:bg-amber-900/40",
    "dark:text-amber-200",
    "bg-emerald-100",
    "text-emerald-700",
    "dark:bg-emerald-900/40",
    "dark:text-emerald-200",
  ],
  content: {
    pipeline: {
      exclude: ["node_modules", "dist"],
    },
  },
  theme: {
    ...themeVars,
    // colors: {
    //   primary: {
    //     DEFAULT: "#1A79FF",
    //     hover: "#4181FD",
    //     pressed: "#1454D4",
    //     disabled: "#A0C0FE",
    //   },
    //   text: {
    //     base: "#333333",
    //     primary: "#333333",
    //     secondary: "#666666",
    //   },
    //   button: {
    //     "ghost": "#666666",
    //     "ghost-hover": "#4181FD",
    //     "ghost-pressed": "#1454D4",
    //     "ghost-disabled": "#BCBCBC",
    //   },
    //   input: {
    //     bg: "#F7F8F9",
    //     focus: "#FFFFFF",
    //   },
    //   table: {
    //     header: "#F3F5F9",
    //   },
    //   border: {
    //     upload: "#EAECF0",
    //     disabled: "#E5E6EB",
    //   },
    // },
    fontSize: {
      "icon-xs": "0.875rem",
      "icon-small": "1rem",
      "icon": "1.125rem",
      "icon-large": "1.5rem",
      "icon-xl": "2rem",
    },
    breakpoints: breakpointsWithUnit,
    container: {
      padding: {
        sm: "1rem",
        md: "1rem",
        lg: "2rem",
        xl: "2rem",
      },
      maxWidth: {
        ...breakpointsWithUnit,
        sm: "100%",
        md: "100%",
        lg: "100%",
        xl: "100%",
      },
    },
  },
  shortcuts: {
    "card-wrapper": "rd-8px shadow-sm",
  },
  transformers: [transformerDirectives(), transformerVariantGroup()],
  presets: [presetUno({ dark: "class" }), presetAIRA() as any],
})
