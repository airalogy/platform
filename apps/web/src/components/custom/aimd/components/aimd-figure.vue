<template>
  <figure
    :id="`rf-${figId}`"
    class="aimd-figure"
    data-aimd-type="fig"
    :data-aimd-fig-id="figId"
    :data-aimd-fig-src="figSrc"
  >
    <img
      v-if="resolvedSrc"
      :src="resolvedSrc"
      :alt="figTitle || figId"
      class="aimd-figure__image"
      loading="lazy"
    >
    <div v-else-if="isLoading" class="aimd-figure__loading">
      {{ $t("common.loadingImage") }}
    </div>
    <div v-else-if="hasError" class="aimd-figure__error">
      <div>{{ $t("common.loadImageFailed") }}</div>
      <div v-if="isAiralogyFile" class="aimd-figure__error-detail">
        {{ $t("common.airalogyFileId") }}: {{ figSrc }}
      </div>
      <div v-else class="aimd-figure__error-detail">
        {{ $t("common.source") }}: {{ figSrc }}
      </div>
    </div>
    <div v-else class="aimd-figure__placeholder">
      {{ $t("common.noImageSource") }}
    </div>

    <figcaption v-if="figTitle || figLegend || figSequence !== undefined" class="aimd-figure__caption">
      <div v-if="figSequence !== undefined || figTitle" class="aimd-figure__title">
        {{ figureTitleText }}
      </div>
      <div v-if="figLegend" class="aimd-figure__legend">
        {{ figLegend }}
      </div>
    </figcaption>
  </figure>
</template>

<script setup lang="ts">
import { getCachedAttachment } from "@/service/api/attachments"
import { computed, ref, watchEffect } from "vue"
import { useI18n } from "vue-i18n"

interface AimdFigureProps {
  figId: string
  figSrc: string
  figTitle?: string
  figLegend?: string
  figSequence?: number
  resolveFile?: (src: string) => Promise<{ url: string } | null> | null
}

const props = defineProps<AimdFigureProps>()
const { t, locale } = useI18n()

const resolvedSrc = ref<string>("")
const isLoading = ref(false)
const hasError = ref(false)

const figureTitleText = computed(() => {
  if (props.figSequence === undefined)
    return props.figTitle
  if (props.figTitle) {
    return t("common.figureIndexWithTitle", {
      index: props.figSequence + 1,
      title: props.figTitle,
    })
  }
  return t("common.figureIndex", { index: props.figSequence + 1 })
})

// Check if src is an Airalogy file ID
const isAiralogyFile = computed(() =>
  props.figSrc.startsWith("airalogy.id.file."),
)

// Check if src is a relative path
const isRelativePath = computed(() => {
  const src = props.figSrc
  return src
    && !src.startsWith("http://")
    && !src.startsWith("https://")
    && !src.startsWith("data:")
    && !src.startsWith("blob:")
    && !src.startsWith("airalogy.id.file.")
})

// Resolve file URL
watchEffect(async () => {
  const src = props.figSrc

  // Reset state
  hasError.value = false
  resolvedSrc.value = ""

  // If it's a full URL, use it directly
  if (!isAiralogyFile.value && !isRelativePath.value) {
    resolvedSrc.value = src
    return
  }

  isLoading.value = true

  try {
    // Handle Airalogy file IDs
    if (isAiralogyFile.value) {
      const attachment = await getCachedAttachment(src)
      if (attachment && attachment.url) {
        resolvedSrc.value = attachment.url
      }
      else {
        hasError.value = true
      }
    }
    // Handle relative paths
    else if (isRelativePath.value) {
      if (!props.resolveFile) {
        hasError.value = true
        return
      }

      const result = await props.resolveFile(src)

      if (result && result.url) {
        resolvedSrc.value = result.url
      }
      else {
        hasError.value = true
      }
    }
    else {
      hasError.value = true
    }
  }
  catch (error) {
    hasError.value = true
    console.error("[aimd-figure] Error loading file:", src, error)
  }
  finally {
    isLoading.value = false
  }
})
</script>

<style scoped lang="sass">
.aimd-figure
  margin: 1.5rem 0
  padding: 0
  border: 1px solid #e0e0e0
  border-radius: 4px
  overflow: hidden
  display: flex
  flex-direction: column
  width: fit-content
  min-width: 200px
  max-width: 75%

  &__image
    max-width: 100% !important
    height: auto
    display: block
    object-fit: contain

  &__loading,
  &__error,
  &__placeholder
    padding: 2rem
    text-align: center
    color: #666
    background-color: #fafafa

  &__error
    color: #d32f2f
    background-color: #ffebee

  &__error-detail
    margin-top: 0.5rem
    font-size: 0.85rem
    color: #666
    word-break: break-all

  &__caption
    padding: 1rem
    background-color: #f5f5f5

  &__title
    font-weight: 600
    margin-bottom: 0.5rem
    color: #333

  &__legend
    font-size: 0.9rem
    color: #666
    line-height: 1.5
    white-space: pre-line
</style>
