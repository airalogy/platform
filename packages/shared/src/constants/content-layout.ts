import type { TabsProps } from "naive-ui"

export const defaultTabsProps: TabsProps = {
  placement: "top",
  themeOverrides: {
    tabColor: "#EDEFF4",
    // tabTextColorActiveLine: "#1A79FF",
    tabGapMediumLine: "16px",
    panePaddingMedium: "1rem 0",
  },
  tabClass: "rounded hover:bg-[#EDEFF4] !px-3",
  paneClass: "overflow-visible flex-1",
  type: "line",
}
