<template>
  <n-input
    clearable
    :value="search"
    :on-focus="setInputFocus"
    :on-blur="setInputBlur"
    type="text"
    placeholder="Search"
    size="medium"
    :maxlength="props.maxlength"
    class="h-9 rounded-2 bg-[rgba(255,255,255,0.1)]"
    :style="[
      {
        '--n-text-color': showBorder || isInputFocus ? '#333333' : '#FFFFFF',
        '--n-height': '2.25rem',
        '--n-padding-left': props.iconPosition === 'left' ? '0' : '12px',
        '--n-padding-right': props.iconPosition === 'right' ? '0' : '12px',
        ...props.inputStyle,
      },
      !showBorder && '--n-border: 0',
    ]"
    :class="[!authStore.isLogin && 'ml-auto', props.inputClass]"
    @update:value="handleInputChange"
    @keydown.enter="handleSubmit"
  >
    <template v-if="props.iconPosition === 'left'" #prefix>
      <n-button quaternary @click="handleSubmit">
        <template #icon>
          <search-icon :color="showBorder || isInputFocus ? 'black' : 'white'" />
        </template>
      </n-button>
    </template>
    <template v-if="props.iconPosition === 'right'" #suffix>
      <n-button quaternary @click="handleSubmit">
        <template #icon>
          <search-icon :color="showBorder || isInputFocus ? 'black' : 'white'" />
        </template>
      </n-button>
    </template>
  </n-input>
</template>

<script setup lang="ts">
import type { InputProps } from "naive-ui/es/input"
import { useAuthStore } from "@/store/modules/auth"
import { useBoolean } from "@airalogy/composables"

export interface IProps {
  isStatic?: boolean
  blurClass?: string
  focusClass?: string
  inputClass?: string
  inputStyle?: Record<string, string | number>
  showBorder?: boolean
  onSubmit?: null | ((val: string) => void)
  maxlength?: number
  iconPosition?: "left" | "right"
}

interface IEmits {
  (e: "update:value", val: string | string[]): void
  (e: "submit:search", val: string): void
  (e: "clear"): void
}

const props = withDefaults(defineProps<IProps>(), {
  isStatic: false,
  class: "",
  blurClass: "",
  focusClass: "",
  showBorder: true,
  onSubmit: null,
  inputClass: "",
  inputStyle: () => ({}),
  maxlength: 100,
  iconPosition: "left",
})

const emits = defineEmits<IEmits>()
const search = ref<string>("")
const authStore = useAuthStore()

const { bool: isInputFocus, setTrue: setInputFocus, setFalse: setInputBlur } = useBoolean()
const handleInputChange: InputProps["onUpdateValue"] = (val, meta) => {
  emits("update:value", val)
  if (meta.source === "clear") {
    emits("clear")
  }
  search.value = val
}

function handleSubmit(e: KeyboardEvent | MouseEvent) {
  const { onSubmit } = props
  e.preventDefault()
  e.stopImmediatePropagation()
  if (typeof onSubmit === "function") {
    onSubmit(search.value)
  }
  else {
    // console.log(search.value)
  }
  emits("submit:search", search.value)
}
</script>

<style scoped></style>
