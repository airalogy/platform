<template>
  <template v-if="content.type === 'traceback'">
    <tracebacks :data="content.data" :code-source="content.codeSource" />
  </template>
  <template v-else-if="content.type === 'syntax_error'">
    <div class="traceback" :style="{ ...sourceStyles, color: 'red' }">
      {{ content.text }}
      <friendly-message :friendly="content.friendly" />
    </div>
  </template>
  <template v-else-if="content.type === 'internal_error_explanation'">
    <internal-error :ran-code="true" :can-give-feedback="false" class="mt-3" />
  </template>
  <template v-else>
    <span
      :style="{ ...sourceStyles, color }"
      v-html="ansiUp.ansi_to_html(content.text?.trimStart?.())"
    />
  </template>
</template>

<script setup lang="ts">
import type { OutputContent } from "./types"
import { computed } from "vue"
import FriendlyMessage from "./components/FriendlyMessage.vue"
import InternalError from "./components/InternalError.vue"
import Tracebacks from "./components/Tracebacks.vue"
import { ansiUp } from "./utils"

const props = defineProps<{
  content: OutputContent
}>()

const sourceStyles = {
  margin: "0",
  lineHeight: "21px",
  whiteSpace: "pre",
}

const color = computed(() => {
  if (
    typeof props.content === "object"
    && (["stderr", "traceback"].includes(props.content.type)
      || props.content.type.includes("error"))
  ) {
    return "red"
  }
  return "white"
})
</script>
