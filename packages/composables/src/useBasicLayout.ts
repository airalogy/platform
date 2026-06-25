import { breakpoints as defaultBreakpoints } from "@airalogy/shared/utils"
import { useBreakpoints } from "@vueuse/core"

export function useBasicLayout() {
  const breakpoints = useBreakpoints(defaultBreakpoints)
  const isMobile = breakpoints.smaller("sm")

  return { isMobile, breakpoints }
}
