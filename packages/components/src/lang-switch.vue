<template>
  <n-dropdown :value="lang" :options="langOptions" trigger="hover" @select="changeLang">
    <div>
      <n-tooltip :content="tooltipContent" placement="left">
        <n-icon>
          <icon-ion-language />
        </n-icon>
      </n-tooltip>
    </div>
  </n-dropdown>
</template>

<script setup lang="ts">
import type { DropdownOption } from "naive-ui"
import { $t } from "@airalogy/shared/locales"
import { computed } from "vue"

defineOptions({
  name: "LangSwitch",
})

const props = withDefaults(defineProps<Props>(), {
  showTooltip: true,
})

const emit = defineEmits<Emits>()

interface Props {
  /** Current language */
  lang: I18n.LangType
  /** Language options */
  langOptions: (I18n.LangOption & DropdownOption) []
  /** Show tooltip */
  showTooltip?: boolean
}

interface Emits {
  (e: "changeLang", lang: I18n.LangType): void
}

const tooltipContent = computed(() => {
  if (!props.showTooltip)
    return ""

  return $t("icon.lang")
})

function changeLang(lang: I18n.LangType) {
  emit("changeLang", lang)
}
</script>

<style scoped></style>
