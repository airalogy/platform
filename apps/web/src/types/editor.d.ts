export interface MenuSectionConfig {
  name: string
  items?: (string | MenuSectionConfig)[]
  tooltip?: string
  icon?: Component | null
  label?: string
  renderLabel?: (t: (...args: any[]) => string, ...args: any[]) => string
  // groupItems?: readonly (string | { name: string, label?: string })[]
  // groupTooltip?: string
  // groupIcon?: Component | null
  // groupLabel?: string
}
