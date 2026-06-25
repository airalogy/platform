<template>
  <n-select
    v-model:value="sortOption"
    class="w-fit"
    :options="props.options"
    :render-tag="customRenderTag"
    :theme-overrides="themeOverrides"
    @update:value="handleSortChange"
  />
</template>

<script lang="ts" setup>
import type { SelectOption, SelectProps } from "naive-ui"
import { $t } from "@airalogy/shared/locales"
import { h } from "vue"

interface IProps {
  modelValue: string | number
  options: SelectOption[]
  renderTag?: SelectProps["renderTag"]
  themeOverrides?: SelectProps["themeOverrides"]
  label?: string
}

const props = withDefaults(defineProps<IProps>(), {
  label: "",
})
const emit = defineEmits<IEmits>()
interface IEmits {
  (e: "update:modelValue", value: string): void
}

const sortOption = useVModel(props, "modelValue", emit)
const labelText = computed(() => {
  const customLabel = props.label?.trim()
  return customLabel || $t("common.sortedBy")
})
const displayLabel = computed(() => {
  const label = labelText.value.trim()
  if (label.endsWith(":") || label.endsWith("：")) {
    return label
  }
  return `${label}:`
})

interface RenderTagParams {
  option: SelectOption
  handleClose: () => void
}

function customRenderTag({ option, handleClose }: RenderTagParams) {
  if (props.renderTag) {
    return props.renderTag({ option, handleClose })
  }

  return h("div", { class: "flex items-center" }, [
    h("span", { class: "text-gray-400 mr-2" }, displayLabel.value),
    h("span", { class: "mx-auto" }, option.label as string),
  ])
}

const themeOverrides = computed(() => {
  return {
    peers: {
      InternalSelection: {
        heightMedium: "36px",
        fontSizeMedium: "14px",
        borderRadius: "8px",
        paddingMedium: "0 12px",
        color: "transparent",
      },
      InternalSelectMenu: {
        borderRadius: "6px",
      },
    },
    ...props.themeOverrides,
  }
})

function handleSortChange(value: string) {
  emit("update:modelValue", value)
}
</script>

<style scoped>
.n-select {
  min-width: 180px;
}
</style>
