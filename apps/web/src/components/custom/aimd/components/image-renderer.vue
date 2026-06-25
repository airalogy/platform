<template>
  <n-image
    :width="480"
    :src="imageUrl"
    :placeholder="props.src"
    :alt="props.alt"
    class="min-h-30"
    :loading="isLoading"
  >
    <template #error>
      <n-icon :size="100" color="lightGray" :component="ImageOutlineIcon" />
    </template>
  </n-image>
</template>

<script setup lang="ts">
import type { AttachmentModels } from "@airalogy/shared"
import ImageOutlineIcon from "~icons/ion/image-outline"
import { NIcon, NImage } from "naive-ui"
import { ref, toValue, watch } from "vue"

interface Props {
  src: string
  alt: string
  getStaticResearchAssets: (id: string) => Promise<AttachmentModels.AttachmentItemResponse | null>
}

const props = defineProps<Props>()

const imageUrl = ref<string | undefined>(undefined)
const isLoading = ref(true)

watch(
  () => props.src,
  async (id) => {
    try {
      isLoading.value = true
      const data = await props.getStaticResearchAssets?.(toValue(id))
      if (data) {
        imageUrl.value = data.url
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
