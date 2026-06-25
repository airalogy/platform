<template>
  <div class="pin-input-container">
    <div class="pin-input-group" :class="{ 'pin-input-group--error': error }">
      <input
        v-for="(digit, index) in digits"
        :key="index"
        :ref="(el) => setInputRef(el, index)"
        v-model="digits[index]"
        type="text"
        inputmode="numeric"
        maxlength="1"
        class="pin-input-digit"
        :class="{ 'pin-input-digit--filled': digit }"
        :placeholder="placeholder"
        :disabled="disabled"
        @input="handleInput(index, $event)"
        @keydown="handleKeydown(index, $event)"
        @paste="handlePaste"
        @focus="handleFocus(index)"
        @blur="handleBlur"
      >
    </div>
    <div v-if="error" class="pin-input-error">
      {{ error }}
    </div>
  </div>
</template>

<script setup lang="ts">
interface Props {
  modelValue?: string
  length?: number
  placeholder?: string
  disabled?: boolean
  error?: string
  autoFocus?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: "",
  length: 6,
  placeholder: "",
  disabled: false,
  error: "",
  autoFocus: false,
})

const emit = defineEmits<{
  (e: "update:modelValue", value: string): void
  (e: "confirm", value: string): void
}>()

const digits = ref<string[]>(Array.from({ length: props.length }, () => ""))
const inputRefs = ref<(HTMLInputElement | null)[]>([])

function setInputRef(el: Element | ComponentPublicInstance | null, index: number) {
  inputRefs.value[index] = el as HTMLInputElement | null
}

function focusInput(index: number) {
  nextTick(() => {
    inputRefs.value[index]?.focus()
  })
}

function handleInput(index: number, event: Event) {
  const target = event.target as HTMLInputElement
  const value = target.value

  // Only allow numeric characters
  const numericValue = value.replace(/\D/g, "")

  if (numericValue !== value) {
    target.value = numericValue
    digits.value[index] = numericValue
    return
  }

  digits.value[index] = numericValue

  // Auto-focus next input if current input is filled
  if (numericValue && index < props.length - 1) {
    focusInput(index + 1)
  }

  updateModelValue()
}

function handleKeydown(index: number, event: KeyboardEvent) {
  // Handle backspace
  if (event.key === "Backspace") {
    if (!digits.value[index] && index > 0) {
      // If current input is empty, focus previous input and clear it
      focusInput(index - 1)
      digits.value[index - 1] = ""
      updateModelValue()
    }
    else if (digits.value[index]) {
      // If current input has value, clear it
      digits.value[index] = ""
      updateModelValue()
    }
  }

  // Handle arrow keys
  if (event.key === "ArrowLeft" && index > 0) {
    focusInput(index - 1)
  }
  else if (event.key === "ArrowRight" && index < props.length - 1) {
    focusInput(index + 1)
  }
}

function handlePaste(event: ClipboardEvent) {
  event.preventDefault()
  const pastedData = event.clipboardData?.getData("text") || ""
  const numericData = pastedData.replace(/\D/g, "")

  // Fill digits from pasted data
  for (let i = 0; i < Math.min(numericData.length, props.length); i++) {
    digits.value[i] = numericData[i]
  }

  // Focus last filled input or first empty input
  const lastFilledIndex = Math.min(numericData.length - 1, props.length - 1)
  focusInput(lastFilledIndex)

  updateModelValue()
}

function handleFocus(index: number) {
  // Select all text when focusing (for easier editing)
  nextTick(() => {
    inputRefs.value[index]?.select()
  })
}

function handleBlur() {
  // Optional: Add any blur handling logic
}

function updateModelValue() {
  const value = digits.value.join("")
  emit("update:modelValue", value)

  // Emit complete event when all digits are filled
  if (value.length === props.length) {
    emit("confirm", value)
  }
}

function clear() {
  digits.value = Array.from({ length: props.length }, () => "")
  updateModelValue()
  focusInput(0)
}

// Watch for external value changes
watch(() => props.modelValue, (newValue) => {
  const cleanValue = (newValue || "").replace(/\D/g, "")
  for (let i = 0; i < props.length; i++) {
    digits.value[i] = cleanValue[i] || ""
  }
}, { immediate: true })

// Auto-focus first input when component mounts
onMounted(() => {
  if (props.autoFocus) {
    focusInput(0)
  }
})

defineExpose({
  clear,
  focus: () => focusInput(0),
})
</script>

<style scoped lang="sass">
.pin-input-container
  width: 100%

.pin-input-group
  display: flex
  gap: 8px
  justify-content: center

  &--error
    .pin-input-digit
      border-color: #d03050
      &:focus
        border-color: #d03050
        box-shadow: 0 0 0 2px rgba(208, 48, 80, 0.2)

.pin-input-digit
  width: 48px
  height: 48px
  border: 2px solid #e0e0e6
  border-radius: 8px
  font-size: 18px
  font-weight: 600
  text-align: center
  background: #fff
  transition: all 0.2s ease
  outline: none

  &:focus
    border-color: #2080f0
    box-shadow: 0 0 0 2px rgba(32, 128, 240, 0.2)

  &--filled
    border-color: #2080f0
    background: #f6f9ff

  &:disabled
    background: #f5f5f5
    border-color: #d0d0d0
    color: #999
    cursor: not-allowed

  &::placeholder
    color: #c0c4cc

.pin-input-error
  margin-top: 8px
  font-size: 14px
  color: #d03050
  text-align: center
</style>
