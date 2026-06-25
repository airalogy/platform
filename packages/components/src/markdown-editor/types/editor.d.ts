export interface MenuSectionConfig {
  name: string
  items?: (string | MenuSectionConfig)[]
  tooltip?: string
  icon?: Component | null
  label?: string
  renderLabel?: (t: (...args: any[]) => string, ...args: any[]) => string
  eventHandlers?: Record<string, (...args: any[]) => any>
}

export interface MenuItemConfig {
  name: string
  icon?: string
  action: string
  isActive?: boolean
  isDisabled?: boolean
}
