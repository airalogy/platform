<template>
  <component :is="props.component" v-if="props.component" :src="sourceUrl" :alt="alt" v-bind="$attrs" />
  <n-image
    v-else
    :width="480"
    :src="sourceUrl"
    :placeholder="props.src"
    :alt="props.alt"
    class="min-h-30"
    :loading="isLoading"
    v-bind="$attrs"
  >
    <template #error>
      <n-icon :size="100" color="lightGray" :component="ImageOutlineIcon" />
    </template>
  </n-image>
</template>

<script setup lang="ts">
import type { AttachmentModels } from "@airalogy/shared"
import type { Component } from "vue"
import ImageOutlineIcon from "~icons/ion/image-outline"
import { NIcon, NImage } from "naive-ui"
import { ref, toValue, watch } from "vue"

defineOptions({ inheritAttrs: false })

const props = defineProps<Props>()

interface Props {
  src: string
  alt: string
  getStaticResearchAssets: (id: string) => Promise<AttachmentModels.AttachmentItemResponse | null>
  component?: string | Component
}

const sourceUrl = ref<string | undefined>(undefined)
const isLoading = ref(true)

watch(
  () => props.src,
  async (id) => {
    try {
      isLoading.value = true
      const data = await props.getStaticResearchAssets?.(toValue(id))
      if (data) {
        sourceUrl.value = data.url
      }
    }
    catch (e) {
      // Handle error
    }
    finally {
      isLoading.value = false
    }
  },
  { immediate: true },
)
</script>
