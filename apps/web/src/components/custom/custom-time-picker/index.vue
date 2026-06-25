<template>
  <div class="custom-time-picker">
    <n-popover
      v-model:show="showPopover"
      trigger="click"
      placement="bottom-start"
      :disabled="disabled"
      header-class="flex flex-row justify-between !px-0"
      content-class="h-60 flex flex-row !px-0"
      footer-class="flex-center"
      :show-arrow="false"
    >
      <template #trigger>
        <n-input
          ref="inputRef"
          :value="displayValue"
          :placeholder="placeholderText"
          :disabled="disabled"
          :status="inputStatus"
          :readonly="readonly"
          :clearable="clearable"
          :size="size"
          :theme-overrides="themeOverrides?.peers?.Input"
          @update:value="handleTimeInputUpdateValue"
          @focus="handleFocus"
          @blur="handleBlur"
        >
          <template #suffix>
            <slot name="suffix" />
            <n-icon class="text-[var(--n-text-color-3)]">
              <icon-ion-time-outline />
            </n-icon>
          </template>
        </n-input>
      </template>

      <template #header>
        <div
          v-for="column in columns"
          :key="column.type"
          class="flex-1 text-center"
        >
          {{ column.label }}
        </div>
      </template>

      <n-scrollbar
        v-for="(column, index) in columns"
        :key="column.type"
      >
        <div
          v-for="item in column.list"
          :key="item"
          :ref="el => handleRef(el as HTMLElement, index, item)"
          class="time-option"
          :class="{ active: item === column.current }"
          @click="updateTime(column.type, item)"
        >
          {{ item }}
        </div>
      </n-scrollbar>

      <template #footer>
        <n-button
          size="tiny"
          type="primary"
          @click="confirmSelection()"
        >
          Confirm
        </n-button>
      </template>
    </n-popover>
  </div>
</template>

<script setup lang="ts">
import type { Emits, TimePickerColumn, TimePickerProps, TimeValue } from "./types"
import { numberToISODuration, parseISODuration } from "@airalogy/shared/utils"
import { useTimeoutFn, useVModel } from "@vueuse/core"
import { NButton, NIcon, NInput, NPopover, NScrollbar } from "naive-ui"
import { useI18n } from "vue-i18n"

// Update props definition
const props = withDefaults(defineProps<TimePickerProps>(), {
  showSeconds: true,
  clearable: true,
  disabled: false,
  readonly: false,
  size: "medium",
  placeholder: "",
  format: "timestamp",
  valueFormat: "HH:mm:ss",
})
// Use generic type for emits
const emit = defineEmits<Emits>()

const timestamp = useVModel(props, "value", emit, { passive: true })
const { t, locale } = useI18n()
const placeholderText = computed(() => props.placeholder || t("common.selectTime"))

const formattedValue = computed({
  get() {
    if (!timestamp.value)
      return null

    if (props.format === "timedelta") {
      // For timedelta, interpret timestamp as seconds
      const result = parseISODuration(timestamp.value as string)
      return result?.formatted || null
    }

    // For timestamp format, manually format to preserve hours > 24
    const timeValue = parseTimeString(timestamp.value as string)
    return formatTimeString(timeValue)
  },
  set(value: string | null) {
    if (!value) {
      timestamp.value = null
      return
    }

    if (props.format === "timedelta") {
      timestamp.value = parseISODuration(value)?.formatted
    }
    else {
      // Store the raw time string instead of converting to timestamp
      timestamp.value = value
    }
  },
})

const showPopover = ref(false)

const selectedTime = ref<TimeValue>({
  hour: "00",
  minute: "00",
  second: "00",
})

// Follow Naive UI's column pattern
const columns = computed(() => {
  return [
    {
      type: "hour",
      list: Array.from({ length: 100 }, (_, i) => i.toString().padStart(2, "0")),
      current: selectedTime.value.hour,
      label: t("common.hour"),
    },
    {
      type: "minute",
      list: Array.from({ length: 60 }, (_, i) => i.toString().padStart(2, "0")),
      current: selectedTime.value.minute,
      label: t("common.minute"),
    },
    ...(props.showSeconds
      ? [{
          type: "second",
          list: Array.from({ length: 60 }, (_, i) => i.toString().padStart(2, "0")),
          current: selectedTime.value.second,
          label: t("common.second"),
        }]
      : []) as TimePickerColumn[],
  ] satisfies TimePickerColumn[]
})

const displayValue = ref("")

function parseTimeString(timeStr: string | null): TimeValue {
  if (!timeStr) {
    return { hour: "00", minute: "00", second: "00" }
  }

  // Handle ISO duration format
  const durationResult = parseISODuration(timeStr)
  if (durationResult) {
    return {
      hour: durationResult.hours.toString().padStart(2, "0"),
      minute: durationResult.minutes.toString().padStart(2, "0"),
      second: durationResult.seconds.toString().padStart(2, "0"),
    }
  }

  // Handle HH:mm:ss format
  const [hour = "00", minute = "00", second = "00"] = timeStr.split(":")
  return { hour, minute, second }
}

function updateTime(type: keyof TimeValue, value: string) {
  selectedTime.value[type] = value

  if (type === "hour") {
    if (!selectedTime.value.minute)
      selectedTime.value.minute = "00"
    if (!selectedTime.value.second)
      selectedTime.value.second = "00"
  }
  else if (type === "minute") {
    if (!selectedTime.value.second)
      selectedTime.value.second = "00"
  }

  confirmSelection(false)
}

function formatTimeString(time: TimeValue): string {
  const parts = [time.hour, time.minute]
  if (props.showSeconds) {
    parts.push(time.second)
  }
  return parts.join(":")
}

function isTimeInRange(time: string): boolean {
  if (!props.minTime && !props.maxTime)
    return true

  const current = parseTimeString(time)
  const min = props.minTime ? parseTimeString(props.minTime) : null
  const max = props.maxTime ? parseTimeString(props.maxTime) : null

  function compareTime(t1: TimeValue, t2: TimeValue): number {
    const h1 = Number.parseInt(t1.hour)
    const h2 = Number.parseInt(t2.hour)
    if (h1 !== h2)
      return h1 - h2

    const m1 = Number.parseInt(t1.minute)
    const m2 = Number.parseInt(t2.minute)
    if (m1 !== m2)
      return m1 - m2

    return Number.parseInt(t1.second) - Number.parseInt(t2.second)
  }

  if (min && compareTime(current, min) < 0)
    return false
  if (max && compareTime(current, max) > 0)
    return false

  return true
}

function confirmSelection(closePopover = true) {
  const { hour, minute, second } = selectedTime.value
  const timeString = formatTimeString(selectedTime.value)

  if (isTimeInRange(timeString)) {
    formattedValue.value = timeString
    if (props.format === "timedelta") {
      timestamp.value = numberToISODuration(Number(hour), Number(minute), Number(second))
    }
    else {
      timestamp.value = timeString
    }
  }

  if (closePopover) {
    showPopover.value = false
  }
}

// Add refs for scrollbar elements
const scrollbars = ref<Record<number, any>>({})

// Modify watch for showPopover
watch(showPopover, (newVal) => {
  if (newVal) {
    const timeValue = formattedValue.value
    Object.assign(selectedTime.value, parseTimeString(timeValue))

    useTimeoutFn(() => {
      scrollToCurrentValues()
    }, 0)
  }
})

function handleRef(el: HTMLElement | null, index: number, value: string) {
  if (!el)
    return
  if (!scrollbars.value[index])
    scrollbars.value[index] = {}
  scrollbars.value[index][value] = el
}

// Add function to scroll to current values
function scrollToCurrentValues() {
  const { hour, minute, second } = selectedTime.value
  const hourEl = scrollbars.value[0][hour]
  if (hourEl) {
    (hourEl as HTMLElement).scrollIntoView({ block: "start" })
  }
  const minuteEl = scrollbars.value[1][minute]
  if (minuteEl) {
    (minuteEl as HTMLElement).scrollIntoView({ block: "start" })
  }
  const secondEl = scrollbars.value[2][second]
  if (secondEl) {
    (secondEl as HTMLElement).scrollIntoView({ block: "start" })
  }
}

// Add time validation regex
const TIME_REGEX = /^(?:[01]?\d|2[0-3]):[0-5]\d(?::[0-5]\d)?$/

// Update handleValueChange function to handle keyboard input and paste
function handleTimeInputUpdateValue(value: string | null) {
  displayValue.value = value ?? ""
}

// Update handleBlur to format and validate on blur
function handleBlur(e: FocusEvent) {
  const value = displayValue.value

  emit("blur", e)

  if (!value) {
    formattedValue.value = null
    return
  }

  const timeMatch = value.match(/(\d{1,2}):?(\d{0,2}):?(\d{0,2})/)
  if (timeMatch) {
    const [_, hours, minutes, seconds] = timeMatch

    // Handle numeric input
    if (!minutes && hours.length > 2) {
      const combinedTime = hours.padStart(6, "0")
      const formattedTime = `${combinedTime.slice(0, 2)}:${combinedTime.slice(2, 4)}:${combinedTime.slice(4)}`

      if (isTimeInRange(formattedTime)) {
        formattedValue.value = formattedTime
        displayValue.value = formattedTime
      }
      else {
        formattedValue.value = null
        displayValue.value = ""
      }
      return
    }

    // Build time string without using dayjs
    const timeStr = `${hours.padStart(2, "0")}:${minutes ? minutes.padStart(2, "0") : "00"}:${seconds ? seconds.padStart(2, "0") : "00"}`

    if (isTimeInRange(timeStr)) {
      displayValue.value = timeStr
      if (props.format === "timedelta") {
        timestamp.value = numberToISODuration(Number(hours), Number(minutes), Number(seconds))
      }
      else {
        formattedValue.value = timeStr
      }
    }
    else {
      formattedValue.value = null
      displayValue.value = ""
    }
  }
  else {
    const durationResult = parseISODuration(value)
    if (durationResult) {
      timestamp.value = durationResult.formatted
      displayValue.value = durationResult.formatted
    }
    else {
      formattedValue.value = null
      displayValue.value = ""
    }
  }
}

// Add input validation status
const inputStatus = computed(() => {
  if (!displayValue.value)
    return undefined
  return TIME_REGEX.test(displayValue.value) && isTimeInRange(displayValue.value)
    ? undefined
    : "error"
})

function handleFocus(e: FocusEvent) {
  emit("focus", e)
}

// Watch for min/max time changes
watch([() => props.minTime, () => props.maxTime], () => {
  if (formattedValue.value && !isTimeInRange(formattedValue.value)) {
    formattedValue.value = null
  }
})

// Add watch for formattedValue
watch(formattedValue, (newVal) => {
  displayValue.value = newVal ?? ""
}, { immediate: true })

const inputRef = ref<HTMLInputElement | null>(null)
</script>

<style lang="sass" scoped>
@use "@styles/sass/variable.sass" as *

$hover-color: rgb(243, 243, 245)
.custom-time-picker

  :deep(.time-picker-icon)
    color: var(--n-text-color-3)

.time-option
  padding: 4px 24px
  cursor: pointer
  transition: background-color .3s cubic-bezier(.4, 0, .2, 1)
  border-radius: 3px
  text-align: center

  &:hover,
  &:focus,
  &.active
    background-color: $hover-color

  &.active
    color: $primary-color
</style>
