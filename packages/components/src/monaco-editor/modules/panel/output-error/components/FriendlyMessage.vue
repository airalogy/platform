<template>
  <div v-if="friendly">
    <div
      ref="messageRef"
      class="markdown-body" :class="[{ truncated }]"
      @click="setTruncated(false)"
    >
      <div v-html="friendly" />
      <div v-if="truncated" class="click-to-expand">
        {{ terms.click_to_expand }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue"
import { useTruncation } from "../composables/useTruncation"
import { terms } from "../constants"

defineProps<{
  friendly?: string
}>()

const messageRef = ref<HTMLElement | null>(null)
const { truncated, setTruncated } = useTruncation(messageRef)
</script>

<style scoped lang="sass">
.markdown-body.truncated
  max-height: 200px
  overflow: hidden
  position: relative
  cursor: pointer

.click-to-expand
  @apply absolute left-0 bottom-0 right-0 bg-white bg-opacity-30 text-center
</style>
