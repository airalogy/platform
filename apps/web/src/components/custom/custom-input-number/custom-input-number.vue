<template>
  <div
    :class="[
      `${mergedClsPrefixRef}-input-number`,
      rtlEnabledRef && `${mergedClsPrefixRef}-input-number--rtl`,
    ]"
  >
    <n-input
      ref="inputInstRef"
      class="h-full w-full"
      autosize
      :autofocus="autofocus"
      :status="mergedStatusRef"
      :bordered="mergedBorderedRef"
      :loading="loading"
      :value="displayedValueRef"
      :theme="themeRef.peers.Input"
      :theme-overrides="themeRef.peerOverrides.Input"
      :builtin-theme-overrides="inputThemeOverrides"
      :size="mergedSizeRef"
      :placeholder="mergedPlaceholderRef"
      :disabled="mergedDisabledRef"
      :text-decoration="displayedValueInvalidRef ? 'line-through' : undefined"
      :readonly="readonly"
      :input-props="inputProps"
      :clearable="clearable"
      internal-loading-before-suffix
      @update-value="handleUpdateDisplayedValue"
      @focus="handleFocus"
      @blur="handleBlur"
      @keydown="handleKeyDown"
      @mousedown="handleMouseDown"
      @clear="handleClear"
    >
      <template #prefix>
        <template v-if="showButton && buttonPlacement === 'both'">
          <span :class="`${mergedClsPrefixRef}-input-number-prefix`">
            <NButton
              ref="minusButtonInstRef"
              text
              :disabled="!reducibleRef || mergedDisabledRef || readonly"
              :focusable="false"
              :theme="themeRef.peers.Button"
              :theme-overrides="themeRef.peerOverrides.Button"
              :builtin-theme-overrides="buttonThemeOverrides"
              @click="handleMinusClick"
              @mousedown="handleMinusMousedown"
            >
              <n-base-icon :cls-prefix="mergedClsPrefixRef">
                <template #default>
                  <remove-icon />
                </template>
              </n-base-icon>
            </NButton>
          </span>
          <span v-if="$slots.prefix" :class="`${mergedClsPrefixRef}-input-number-prefix`">
            <slot name="prefix" />
          </span>
        </template>
        <template v-else>
          <slot name="prefix" />
        </template>
      </template>
      <template #suffix>
        <template v-if="showButton">
          <span v-if="$slots.suffix" :class="`${mergedClsPrefixRef}-input-number-suffix`">
            <slot name="suffix" />
          </span>
          <NButton
            v-if="buttonPlacement === 'right'"
            ref="minusButtonInstRef"
            text
            :disabled="!reducibleRef || mergedDisabledRef || readonly"
            :focusable="false"
            :theme="themeRef.peers.Button"
            :theme-overrides="themeRef.peerOverrides.Button"
            :builtin-theme-overrides="buttonThemeOverrides"
            @click="handleMinusClick"
            @mousedown="handleMinusMousedown"
          >
            <n-base-icon :cls-prefix="mergedClsPrefixRef">
              <template #default>
                <remove-icon />
              </template>
            </n-base-icon>
          </NButton>
          <NButton
            ref="addButtonInstRef"
            text
            :disabled="!addableRef || mergedDisabledRef || readonly"
            :focusable="false"
            :theme="themeRef.peers.Button"
            :theme-overrides="themeRef.peerOverrides.Button"
            :builtin-theme-overrides="buttonThemeOverrides"
            @click="handleAddClick"
            @mousedown="handleAddMousedown"
          >
            <n-base-icon :cls-prefix="mergedClsPrefixRef">
              <template #default>
                <add-icon />
              </template>
            </n-base-icon>
          </NButton>
        </template>
        <template v-else>
          <slot name="suffix" />
        </template>
      </template>
    </n-input>
  </div>
</template>

<script setup lang="ts">
import type Big from "big.js"
import type { FormValidationStatus } from "naive-ui/es/form/src/interface"

import type { InputInst } from "naive-ui/es/input"
import type { InputNumberInst, Size } from "naive-ui/es/input-number/src/interface"
import type { MaybeArray } from "naive-ui/lib/_utils"
import type { InputHTMLAttributes } from "vue"
import type { ICustomInputNumberPayload } from "./types"
import {
  formatter as defaultFormat,
  parser as defaultParse,
  validator as defaultValidator,
  isWipValue,
} from "@airalogy/shared/utils"
import BigNum from "big.js"
import { NBaseIcon } from "naive-ui/es/_internal"
import { AddIcon, RemoveIcon } from "naive-ui/es/_internal/icons"
import { useConfig, useFormItem, useLocale, useTheme } from "naive-ui/es/_mixins"
import { useRtl } from "naive-ui/es/_mixins/use-rtl"
import { call } from "naive-ui/es/_utils"
import { NInput } from "naive-ui/es/input"
import style from "naive-ui/es/input-number/src/styles/input-number.cssr"
import { inputNumberLight } from "naive-ui/es/input-number/styles"

defineOptions({ name: "CustomInputNumber" })

const props = withDefaults(defineProps<IProps>(), {
  "type": "integer",
  "theme": undefined,
  "themeOverrides": undefined,
  "builtinThemeOverrides": undefined,
  "loading": undefined,
  "defaultValue": null,
  "step": 1,
  "disabled": undefined,
  "bordered": undefined,
  "showButton": true,
  "buttonPlacement": "right",
  "keyboard": () => ({}),
  "updateValueOnInput": true,
  "placeholder": undefined,
  "value": undefined,
  "displayedValue": undefined,
  "min": undefined,
  "max": undefined,
  "size": undefined,
  "validator": undefined,
  "inputProps": undefined,
  "parse": undefined,
  "format": undefined,
  "precision": undefined,
  "status": undefined,
  "onUpdate:value": undefined,
  "onUpdateValue": undefined,
  "onChange": undefined,
  "onFocus": undefined,
  "onBlur": undefined,
  "onClear": undefined,
  "stepper": undefined,
  "onInvalidInput": undefined,
})
const HOLDING_CHANGE_THRESHOLD = 800
const HOLDING_CHANGE_INTERVAL = 100

export interface IProps {
  "type"?: "integer" | "float" | "number"
  "theme"?: object
  "themeOverrides"?: object
  "builtinThemeOverrides"?: object
  "autofocus"?: boolean
  "loading"?: boolean | undefined
  "placeholder"?: string
  "defaultValue"?: Big.Big | number | null
  "value"?: Big.Big | number | null
  "displayedValue"?: string
  "step"?: number | string
  "min"?: Big.Big | number | string
  "max"?: Big.Big | number | string
  "size"?: Size
  "disabled"?: boolean | undefined
  "bordered"?: boolean | undefined
  "showButton"?: boolean
  "buttonPlacement"?: "right" | "both"
  "inputProps"?: InputHTMLAttributes
  "readonly"?: boolean
  "clearable"?: boolean
  "keyboard"?: {
    ArrowUp?: boolean
    ArrowDown?: boolean
  }
  "updateValueOnInput"?: boolean
  "parse"?: (input: string) => Big.Big | number | null
  "format"?: (
    value: Big.Big | number | null,
    precision?: number,
    displayedValue?: string,
    fromStepper?: boolean,
  ) => string
  "validator"?: (value: Big.Big | number | null) => boolean
  "stepper"?: (value: Big.Big | number | null, offset: number) => Big.Big | number
  "precision"?: number
  "status"?: FormValidationStatus
  // eslint-disable-next-line vue/prop-name-casing
  "onUpdate:value"?: MaybeArray<(payload: ICustomInputNumberPayload) => void>
  "onUpdateValue"?: MaybeArray<(payload: ICustomInputNumberPayload) => void>
  "onFocus"?: MaybeArray<(e: FocusEvent) => void>
  "onBlur"?: MaybeArray<(e: FocusEvent) => void>
  "onClear"?: MaybeArray<(e: MouseEvent) => void>
  // deprecated
  "onChange"?: MaybeArray<(payload: ICustomInputNumberPayload) => void>
  "onInvalidInput"?: MaybeArray<(value: string) => void>
}

function getPrecision(value: Big.Big | string | number): number {
  const fraction = String(value).split(".")[1]
  return fraction ? fraction.length : 0
}

function getMaxPrecision(currentValue: number): number {
  const precisions = [props.min, props.max, props.step, currentValue].map((value): number => {
    if (value === undefined)
      return 0
    return getPrecision(
      typeof value === "number" || typeof value === "string" ? value : value.toNumber(),
    )
  })
  return Math.max(...precisions)
}

function defaultStepper(value: Big.Big | number, offset: number, precision?: number) {
  // return parseFloat((value + offset).toFixed(precision ?? getMaxPrecision(value)))
  if (offset === 0)
    return value

  const bigValue = value instanceof BigNum ? value : new BigNum(value)

  return bigValue.plus(offset)
}

function parseNumber(value?: Big.Big | string | number) {
  if (value === null || typeof value === "undefined")
    return null
  if (typeof value === "number") {
    return value
  }

  let parsedNumber
  if (typeof value === "string") {
    parsedNumber = Number(value)
  }
  else {
    parsedNumber = value.toNumber()
  }

  if (Number.isNaN(parsedNumber))
    return null

  return parsedNumber
}

function useMergedState<T>(
  controlledStateRef: Ref<T | undefined>,
  uncontrolledStateRef: Ref<T>,
): ComputedRef<T> {
  watch(controlledStateRef, (value) => {
    if (value !== undefined) {
      uncontrolledStateRef.value = value
    }
  })
  return computed(() => {
    if (controlledStateRef.value === undefined) {
      return uncontrolledStateRef.value
    }
    return controlledStateRef.value
  })
}

const { mergedBorderedRef, mergedClsPrefixRef, mergedRtlRef } = useConfig(props)

const themeRef = useTheme(
  "InputNumber",
  "-input-number",
  style,
  inputNumberLight,
  props as any,
  mergedClsPrefixRef,
)

const { localeRef } = useLocale("InputNumber")
const formItem = useFormItem(props)
const { mergedSizeRef, mergedDisabledRef, mergedStatusRef } = formItem
// dom ref
const inputInstRef = ref<InputInst | null>(null)
const minusButtonInstRef = ref<{ $el: HTMLElement } | null>(null)
const addButtonInstRef = ref<{ $el: HTMLElement } | null>(null)
// value
const uncontrolledValueRef = ref(props.defaultValue)
const controlledValueRef = toRef(props, "value")
const mergedValueRef = useMergedState(controlledValueRef, uncontrolledValueRef)
const displayedValueRef = ref("")

const mergedPlaceholderRef = computed(() => {
  const { placeholder } = props
  if (placeholder !== undefined)
    return placeholder
  return localeRef.value.placeholder
})
const mergedStepRef = computed(() => {
  const parsedNumber = parseNumber(props.step)
  if (parsedNumber !== null) {
    return parsedNumber === 0 ? 1 : Math.abs(parsedNumber)
  }
  return 1
})

const mergedMinRef = computed(() => {
  const parsedNumber = parseNumber(props.min)
  if (parsedNumber !== null)
    return parsedNumber
  return null
})
const mergedMaxRef = computed(() => {
  const parsedNumber = parseNumber(props.max)
  if (parsedNumber !== null)
    return parsedNumber
  return null
})
function doUpdateValue(value: Big.Big | number | null, fromStepper = false): void {
  const { value: mergedValue } = mergedValueRef
  if (
    value instanceof BigNum && mergedValue instanceof BigNum
      ? value.eq(mergedValue)
      : value === mergedValue
  ) {
    deriveDisplayedValueFromValue()
    return
  }

  if (fromStepper) {
    deriveDisplayedValueFromValue(value, true)
  }

  const { "onUpdate:value": _onUpdateValue, onUpdateValue, onChange } = props
  const { nTriggerFormInput, nTriggerFormChange } = formItem
  const payload = { value, displayedValue: displayedValueRef.value, type: props.type }

  if (onChange)
    call(onChange, payload)
  if (onUpdateValue)
    call(onUpdateValue, payload)
  if (_onUpdateValue)
    call(_onUpdateValue, payload)

  uncontrolledValueRef.value = value instanceof BigNum ? value.toNumber() : value
  nTriggerFormInput()
  nTriggerFormChange()
}
function deriveValueFromDisplayedValue({
  offset,
  doUpdateIfValid,
  fixPrecision,
  isInputting,
  fromStepper = false,
}: {
  offset: number
  doUpdateIfValid: boolean
  fixPrecision: boolean
  isInputting: boolean
  fromStepper?: boolean
}): null | Big.Big | number | false {
  const { value: displayedValue } = displayedValueRef
  if (isInputting && isWipValue(displayedValue)) {
    return false
  }
  const parsedValue = (props.parse || defaultParse)(displayedValue)

  if (parsedValue === null) {
    if (doUpdateIfValid)
      doUpdateValue(null)
    return null
  }

  if (!defaultValidator(parsedValue)) {
    return false
  }

  const currentPrecision = getPrecision(parsedValue)
  const { precision } = props
  if (precision !== undefined && precision < currentPrecision && !fixPrecision) {
    return false
  }

  let nextValue = (props.stepper || defaultStepper)(parsedValue, offset, precision)

  if (defaultValidator(nextValue)) {
    const { value: mergedMax } = mergedMaxRef
    const { value: mergedMin } = mergedMinRef
    if (typeof nextValue === "number") {
      if (mergedMax !== null && nextValue > mergedMax) {
        if (!doUpdateIfValid || isInputting)
          return false
        // if doUpdateIfValid=true, we try to make it a valid value
        nextValue = mergedMax
      }
      if (mergedMin !== null && nextValue < mergedMin) {
        if (!doUpdateIfValid || isInputting)
          return false
        // if doUpdateIfValid=true, we try to make it a valid value
        nextValue = mergedMin
      }
    }
    else {
      if (mergedMax !== null && nextValue.gt(mergedMax)) {
        if (!doUpdateIfValid || isInputting)
          return false
        // if doUpdateIfValid=true, we try to make it a valid value
        nextValue = new BigNum(mergedMax)
      }
      if (mergedMin !== null && nextValue.lt(mergedMin)) {
        if (!doUpdateIfValid || isInputting)
          return false
        // if doUpdateIfValid=true, we try to make it a valid value
        nextValue = new BigNum(mergedMin)
      }
    }

    if (props.validator && !props.validator(nextValue))
      return false
    if (doUpdateIfValid)
      doUpdateValue(nextValue, fromStepper)
    return nextValue
  }

  return false
}
function deriveDisplayedValueFromValue(
  value: Big.Big | number | null = null,
  fromStepper = false,
): void {
  const { value: mergedValue } = mergedValueRef
  const { value: displayedValue } = displayedValueRef
  const targetValue = fromStepper ? value : mergedValue

  if (defaultValidator(targetValue)) {
    const { format: formatProp, precision } = props
    if (formatProp) {
      displayedValueRef.value = formatProp(targetValue, precision, displayedValue, fromStepper)
    }
    else if (
      targetValue === null
      || precision === undefined
      // precision overflow
      || getPrecision(targetValue) > precision
    ) {
      // displayedValueRef.value = defaultFormat(targetValue, undefined, displayedValue, fromStepper)
      const { onInvalidInput } = props
      if (onInvalidInput && displayedValueRef.value) {
        call(onInvalidInput, displayedValueRef.value)
      }
    }
    else {
      displayedValueRef.value = defaultFormat(targetValue, precision, displayedValue, fromStepper)
    }
  }
  else {
    // null can pass the validator check
    // so mergedValue is a number
    displayedValueRef.value = String(targetValue)
  }
}
deriveDisplayedValueFromValue()
const displayedValueInvalidRef = computed(() => {
  const derivedValue = deriveValueFromDisplayedValue({
    offset: 0,
    doUpdateIfValid: false,
    isInputting: false,
    fixPrecision: false,
  })
  return derivedValue === false
})

const reducibleRef = computed(() => {
  const { value: mergedValue } = mergedValueRef
  if (props.validator && mergedValue === null) {
    return false
  }
  const { value: mergedStep } = mergedStepRef
  const derivedNextValue = deriveValueFromDisplayedValue({
    offset: -mergedStep,
    doUpdateIfValid: false,
    isInputting: false,
    fixPrecision: false,
  })
  return derivedNextValue !== false
})
const addableRef = computed(() => {
  const { value: mergedValue } = mergedValueRef
  if (props.validator && mergedValue === null) {
    return false
  }
  const { value: mergedStep } = mergedStepRef
  const derivedNextValue = deriveValueFromDisplayedValue({
    offset: Number(mergedStep),
    doUpdateIfValid: false,
    isInputting: false,
    fixPrecision: false,
  })
  return derivedNextValue !== false
})
function doFocus(e: FocusEvent): void {
  const { onFocus } = props
  const { nTriggerFormFocus } = formItem
  if (onFocus)
    call(onFocus, e)
  nTriggerFormFocus()
}
function doBlur(e: FocusEvent): void {
  if (e.target === inputInstRef.value?.wrapperElRef) {
    // hit input wrapper
    // which means not activated
    return
  }
  const value = deriveValueFromDisplayedValue({
    offset: 0,
    doUpdateIfValid: true,
    isInputting: false,
    fixPrecision: true,
  })

  if (value === false) {
    // If not valid, nothing will be emitted, so derive displayed value from
    // origin value
    deriveDisplayedValueFromValue()
  }
  else {
    const inputElRef = inputInstRef.value?.inputElRef
    if (inputElRef) {
      inputElRef.value = String(value || "")
    }
    // If value is not changed, the displayed value may be greater than or
    // less than the current value. The derived value is reformatted so the
    // value is not changed. We can simply derive a new displayed value
    const { value: mergedValue } = mergedValueRef
    if (
      value === null && mergedValue === null
        ? true
        : value instanceof BigNum && mergedValue !== null
          ? value.eq(mergedValue)
          : mergedValue === value
    ) {
      deriveDisplayedValueFromValue()
    }
  }

  const previousValue = unref(mergedValueRef)
  const { onBlur } = props
  const { nTriggerFormBlur } = formItem
  if (onBlur)
    call(onBlur, e)
  nTriggerFormBlur()
  // User may change value in blur callback, we make sure it will be

  // displayed. Sometimes mergedValue won't be viewed as changed
  if (previousValue !== unref(mergedValueRef)) {
    deriveDisplayedValueFromValue()
  }
}
function doClear(e: MouseEvent): void {
  const { onClear } = props
  if (onClear)
    call(onClear, e)
}
function doAdd(): void {
  const { value: addable } = addableRef
  if (!addable) {
    clearAddHoldTimeout()
    return
  }
  const { value: mergedValue } = mergedValueRef
  if (mergedValue === null) {
    if (!props.validator) {
      doUpdateValue(createValidValue())
    }
  }
  else {
    const { value: mergedStep } = mergedStepRef
    deriveValueFromDisplayedValue({
      offset: mergedStep,
      doUpdateIfValid: true,
      isInputting: false,
      fixPrecision: true,
      fromStepper: true,
    })
  }
}
function doMinus(): void {
  const { value: reducible } = reducibleRef
  if (!reducible) {
    clearMinusHoldTimeout()
    return
  }
  const { value: mergedValue } = mergedValueRef
  if (mergedValue === null) {
    if (!props.validator) {
      doUpdateValue(createValidValue())
    }
  }
  else {
    const { value: mergedStep } = mergedStepRef
    deriveValueFromDisplayedValue({
      offset: -mergedStep,
      doUpdateIfValid: true,
      isInputting: false,
      fixPrecision: true,
      fromStepper: true,
    })
  }
}
const handleFocus = doFocus
const handleBlur = doBlur
function createValidValue(): number | null {
  if (props.validator)
    return null
  const { value: mergedMin } = mergedMinRef
  const { value: mergedMax } = mergedMaxRef
  if (mergedMin !== null) {
    return Math.max(0, mergedMin)
  }
  else if (mergedMax !== null) {
    return Math.min(0, mergedMax)
  }
  return 0
}
function handleClear(e: MouseEvent): void {
  doClear(e)
  doUpdateValue(null)
}
function handleMouseDown(e: MouseEvent): void {
  if (addButtonInstRef.value?.$el.contains(e.target as Node)) {
    e.preventDefault()
  }
  if (minusButtonInstRef.value?.$el.contains(e.target as Node)) {
    e.preventDefault()
  }
  inputInstRef.value?.activate()
}
let minusHoldStateIntervalId: number | null = null
let addHoldStateIntervalId: number | null = null
let firstMinusMousedownId: number | null = null
let firstAddMousedownId: number | null = null

function clearMinusHoldTimeout(): void {
  if (firstMinusMousedownId) {
    window.clearTimeout(firstMinusMousedownId)
    firstMinusMousedownId = null
  }
  if (minusHoldStateIntervalId) {
    window.clearInterval(minusHoldStateIntervalId)
    minusHoldStateIntervalId = null
  }
}
function clearAddHoldTimeout(): void {
  if (firstAddMousedownId) {
    window.clearTimeout(firstAddMousedownId)
    firstAddMousedownId = null
  }
  if (addHoldStateIntervalId) {
    window.clearInterval(addHoldStateIntervalId)
    addHoldStateIntervalId = null
  }
}
function handleMinusMousedown(): void {
  clearMinusHoldTimeout()
  firstMinusMousedownId = window.setTimeout(() => {
    minusHoldStateIntervalId = window.setInterval(() => {
      doMinus()
    }, HOLDING_CHANGE_INTERVAL)
  }, HOLDING_CHANGE_THRESHOLD)
  document.addEventListener("mouseup", clearMinusHoldTimeout, {
    once: true,
  })
}
function handleAddMousedown(): void {
  clearAddHoldTimeout()
  firstAddMousedownId = window.setTimeout(() => {
    addHoldStateIntervalId = window.setInterval(() => {
      doAdd()
    }, HOLDING_CHANGE_INTERVAL)
  }, HOLDING_CHANGE_THRESHOLD)
  document.addEventListener("mouseup", clearAddHoldTimeout, {
    once: true,
  })
}
function handleAddClick(): void {
  if (addHoldStateIntervalId)
    return
  doAdd()
}
function handleMinusClick(): void {
  if (minusHoldStateIntervalId)
    return
  doMinus()
}
function handleKeyDown(e: KeyboardEvent): void {
  if (e.key === "Enter") {
    if (e.target === inputInstRef.value?.wrapperElRef) {
      // hit input wrapper
      // which means not activated
      return
    }
    const value = deriveValueFromDisplayedValue({
      offset: 0,
      doUpdateIfValid: true,
      isInputting: false,
      fixPrecision: true,
    })
    if (value !== false) {
      inputInstRef.value?.deactivate()
    }
  }
  else if (e.key === "ArrowUp") {
    if (!addableRef.value)
      return
    if (props.keyboard.ArrowUp === false)
      return
    e.preventDefault()
    const value = deriveValueFromDisplayedValue({
      offset: 0,
      doUpdateIfValid: true,
      isInputting: false,
      fixPrecision: true,
    })
    if (value !== false) {
      doAdd()
    }
  }
  else if (e.key === "ArrowDown") {
    if (!reducibleRef.value)
      return
    if (props.keyboard.ArrowDown === false)
      return
    e.preventDefault()
    const value = deriveValueFromDisplayedValue({
      offset: 0,
      doUpdateIfValid: true,
      isInputting: false,
      fixPrecision: true,
    })
    if (value !== false) {
      doMinus()
    }
  }
}
function handleUpdateDisplayedValue(value: string): void {
  displayedValueRef.value = value

  const { onInvalidInput } = props
  if (onInvalidInput && displayedValueInvalidRef.value) {
    call(onInvalidInput, value)
  }

  if (props.updateValueOnInput && !props.format && !props.parse && props.precision === undefined) {
    deriveValueFromDisplayedValue({
      offset: 0,
      doUpdateIfValid: true,
      isInputting: true,
      fixPrecision: false,
    })
  }
}

watch(mergedValueRef, (val) => {
  void nextTick(() => {
    deriveDisplayedValueFromValue()
  })
})

watch(
  () => props.displayedValue,
  (val) => {
    const inputInst = inputInstRef.value
    if (typeof val === "undefined" || !inputInst) {
      return
    }

    displayedValueRef.value = val
    const mirrorEl = (inputInst as any).inputMirrorElRef as HTMLDivElement
    if (mirrorEl) {
      if (val) {
        mirrorEl.textContent = val
      }
      else if (mergedPlaceholderRef.value) {
        mirrorEl.textContent = mergedPlaceholderRef.value
      }
      else {
        mirrorEl.innerHTML = "&nbsp;"
      }
    }
  },
)

const exposedMethods: InputNumberInst = {
  focus: () => inputInstRef.value?.focus(),
  blur: () => inputInstRef.value?.blur(),
  select: () => inputInstRef.value?.select(),
}
const rtlEnabledRef = useRtl("InputNumber", mergedRtlRef, mergedClsPrefixRef)

const inputThemeOverrides = {
  paddingSmall: "0 8px 0 10px",
  paddingMedium: "0 8px 0 12px",
  paddingLarge: "0 8px 0 14px",
}
const buttonThemeOverrides = computed(() => {
  const {
    self: { iconColorDisabled },
  } = themeRef.value

  return {
    textColorTextDisabled: "",
    opacityDisabled: "",
  }
})

defineExpose({
  ...exposedMethods,
  rtlEnabled: rtlEnabledRef,
  inputInstRef,
  minusButtonInstRef,
  addButtonInstRef,
  mergedClsPrefix: mergedClsPrefixRef,
  mergedBordered: mergedBorderedRef,
  uncontrolledValue: uncontrolledValueRef,
  mergedValue: mergedValueRef,
  mergedPlaceholder: mergedPlaceholderRef,
  displayedValueInvalid: displayedValueInvalidRef,
  mergedSize: mergedSizeRef,
  mergedDisabled: mergedDisabledRef,
  displayedValue: displayedValueRef,
  addable: addableRef,
  reducible: reducibleRef,
  mergedStatus: mergedStatusRef,
  handleFocus,
  handleBlur,
  handleClear,
  handleMouseDown,
  handleAddClick,
  handleMinusClick,
  handleAddMousedown,
  handleMinusMousedown,
  handleKeyDown,
  handleUpdateDisplayedValue,
})

watchEffect(() => {
  const { value: placeholder } = mergedPlaceholderRef
  if (!placeholder || (typeof props.value !== "undefined" && props.value !== null))
    return

  const mirrorEl = (inputInstRef.value as any)?.inputMirrorElRef as HTMLDivElement

  if (mirrorEl) {
    mirrorEl.textContent = placeholder.replaceAll("\n", "")
  }
})
</script>

<style scoped lang="sass">
.n-input-number-suffix
  margin: 0 6px
</style>
