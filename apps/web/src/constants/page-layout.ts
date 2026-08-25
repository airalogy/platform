/**
 * Semantic widths for top-level Platform pages.
 *
 * Keep the application shell on the workspace width. Pages that need a calmer
 * reading or form experience should opt into a narrower content width through
 * route meta instead of adding one-off max-width utilities to the page shell.
 */
export const PAGE_LAYOUT_MAX_WIDTHS = {
  workspace: 1920,
  focused: 1440,
  reading: 960,
} as const

export type PageLayoutWidth = keyof typeof PAGE_LAYOUT_MAX_WIDTHS

export const DEFAULT_PAGE_LAYOUT_WIDTH: PageLayoutWidth = "workspace"

export function resolvePageLayoutMaxWidth(
  width: PageLayoutWidth = DEFAULT_PAGE_LAYOUT_WIDTH,
  customMaxWidth?: number,
) {
  if (customMaxWidth && Number.isFinite(customMaxWidth) && customMaxWidth > 0) {
    return customMaxWidth
  }

  return PAGE_LAYOUT_MAX_WIDTHS[width]
}
