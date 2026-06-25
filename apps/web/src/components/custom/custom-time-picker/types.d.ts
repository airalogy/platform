// Follow Naive UI's interface pattern
export interface TimePickerColumn {
  type: "hour" | "minute" | "second"
  list: string[]
  current: string
  label: string
}

export interface TimeValue {
  hour: string
  minute: string
  second: string
}

// Expand Naive UI's TimePickerProps explicitly
export interface TimePickerProps {
  // Value handling
  value?: string | number | null
  defaultValue?: number | null

  // Time constraints
  minTime?: string
  maxTime?: string
  showSeconds?: boolean

  // Input props
  readonly?: boolean
  disabled?: boolean
  clearable?: boolean
  size?: "tiny" | "small" | "medium" | "large"
  placeholder?: string
  status?: "success" | "warning" | "error" | undefined

  // // Events
  // onBlur?: (e: FocusEvent) => void
  // onFocus?: (e: FocusEvent) => void
  // onClear?: () => void
  // onClick?: (e: MouseEvent) => void

  // Theme
  theme?: string | null
  themeOverrides?: Partial<NTimePickerProps["themeOverrides"]>

  // Add new format prop
  format?: "timestamp" | "timedelta"
  valueFormat?: string // e.g. 'HH:mm:ss' or 'HH:mm'
}

// Define emit types
export interface Emits {
  (e: "update:value", value: number | null): void
  (e: "blur", event: FocusEvent): void
  (e: "focus", event: FocusEvent): void
  (e: "clear"): void
  (e: "click", event: MouseEvent): void
}
