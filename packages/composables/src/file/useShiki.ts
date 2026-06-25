import type { HighlighterCore } from "@shikijs/types"
import type { LanguageRegistration, ThemeRegistration } from "shiki"
import { aimdSyntaxTheme, aimdLanguage, aimdInjection } from "@airalogy/aimd-core"
import { aimdTokenColors, aimdTheme } from "@airalogy/aimd-editor"
import { mermaidShikiTheme } from "@airalogy/shared/constants"
import { createHighlighterCore } from "shiki/core"
import { createOnigurumaEngine } from "shiki/engine/oniguruma"
import { ref } from "vue"

export interface UseShikiOptions {
  themes?: string[]
  langs?: string[]
  disposeOnUnMounted?: boolean
}

/**
 * Merge AIMD token colors into a base theme
 */
function mergeAimdColors(baseTheme: ThemeRegistration): ThemeRegistration {
  const baseSettings = baseTheme.settings || baseTheme.tokenColors || []
  return {
    ...baseTheme,
    settings: [...baseSettings, ...aimdTokenColors],
  }
}

// Map of supported themes and their import functions
const themeImports: Record<string, () => Promise<any>> = {
  "github-dark": () => import("shiki/themes/github-dark.mjs").then(m => mergeAimdColors(m.default || m)),
  "github-light": () => import("shiki/themes/github-light.mjs").then(m => mergeAimdColors(m.default || m)),
  "dark-plus": () => import("shiki/themes/dark-plus.mjs").then(m => mergeAimdColors(m.default || m)),
  "light-plus": () => import("shiki/themes/light-plus.mjs").then(m => mergeAimdColors(m.default || m)),
  "aimd-theme": () => Promise.resolve(aimdTheme),
  "mermaid-dark": () => Promise.resolve(mermaidShikiTheme),
}

// Map of supported languages and their import functions
const langImports: Record<string, () => Promise<LanguageRegistration[]>> = {
  python: () => import("shiki/langs/python.mjs") as any as Promise<LanguageRegistration[]>,
  markdown: () => import("shiki/langs/markdown.mjs") as any as Promise<LanguageRegistration[]>,
  json: () => import("shiki/langs/json.mjs") as any as Promise<LanguageRegistration[]>,
  // AIMD syntax - imports aimd language, markdown base, and injection
  aimd: async () => {
    // Use the aimd language and injection from @airalogy/aimd-core
    // aimdLanguage is the full aimd language definition based on markdown
    // aimdInjection is for injecting AIMD syntax into markdown
    return [aimdLanguage, aimdInjection].flat() as LanguageRegistration[]
  },
  toml: () => import("shiki/langs/toml.mjs") as any as Promise<LanguageRegistration[]>,
  dotenv: () => import("shiki/langs/dotenv.mjs") as any as Promise<LanguageRegistration[]>,
  javascript: () => import("shiki/langs/javascript.mjs") as any as Promise<LanguageRegistration[]>,
  typescript: () => import("shiki/langs/typescript.mjs") as any as Promise<LanguageRegistration[]>,
  mermaid: () => import("shiki/langs/mermaid.mjs") as any as Promise<LanguageRegistration[]>,
  html: () => import("shiki/langs/html.mjs") as any as Promise<LanguageRegistration[]>,
  css: () => import("shiki/langs/css.mjs") as any as Promise<LanguageRegistration[]>,
  yaml: () => import("shiki/langs/yaml.mjs") as any as Promise<LanguageRegistration[]>,
  bash: () => import("shiki/langs/bash.mjs") as any as Promise<LanguageRegistration[]>,
  sql: () => import("shiki/langs/sql.mjs") as any as Promise<LanguageRegistration[]>,
}

const [useProvideShiki, _useShiki] = createInjectionState((options: UseShikiOptions = {}) => {
  const highlighter = ref<HighlighterCore>()
  const isLoading = ref(true)

  async function loadLanguage(language: string) {
    const highlighterInstance = highlighter.value
    if (!highlighterInstance) {
      return false
    }

    try {
      highlighterInstance.getLanguage(language)
    }
    catch (error) {
      // NOTHING
    }

    try {
      const importFn = langImports[language as keyof typeof langImports] || (() => import(/* @vite-ignore */`shiki/langs/${language}.mjs`))

      if (!importFn) {
        return false
      }

      const lang = await importFn()

      if (!lang) {
        return false
      }

      await highlighterInstance.loadLanguage(lang as any)

      return true
    }
    catch (error) {
      console.error("Failed to load language:", error)
      return false
    }
  }

  async function initializeShiki() {
    try {
      const selectedThemes = options.themes || ["github-dark", "aimd-theme", "mermaid-theme"]
      const selectedLangs = options.langs || ["markdown", "json", "aimd", "python", "toml", "dotenv", "javascript", "mermaid"]

      const themes = await Promise.all(
        selectedThemes.map((theme) => {
          const importFn = themeImports[theme as keyof typeof themeImports]
          if (!importFn)
            throw new Error(`Theme "${theme}" is not supported`)
          return importFn()
        }),
      )

      const langs = await Promise.all(
        selectedLangs.map((lang) => {
          const importFn = langImports[lang as keyof typeof langImports]
          if (!importFn)
            throw new Error(`Language "${lang}" is not supported`)
          return importFn()
        }),
      )

      const instance = await createHighlighterCore({
        themes,
        langs,
        engine: await createOnigurumaEngine(import("shiki/wasm")),
      }) as HighlighterCore

      highlighter.value = instance
      isLoading.value = false

      return instance
    }
    catch (error) {
      console.error("Failed to initialize Shiki:", error)
      isLoading.value = false
      return null
    }
  }

  if (options.disposeOnUnMounted) {
    onUnmounted(async () => {
      if (highlighter.value) {
        highlighter.value.dispose()
      }
    })
  }

  return {
    highlighter,
    isLoading,
    initializeShiki,
    loadLanguage,
  }
})

export function useShiki() {
  const state = _useShiki()
  if (!state)
    throw new Error("useShiki must be used after useProvideShiki")
  return state
}

export function useOrProvideShiki(options: UseShikiOptions = {}) {
  try {
    return useShiki()
  }
  catch (e) {
    return useProvideShiki(options)
  }
}
