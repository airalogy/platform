<template>
  <n-spin
    size="large" :show="loading" tabindex="0"
    class="image-preview-container relative size-full"
    content-class="size-full bg-gray-50 outline-none group/image min-h-24"
    @focus="isContainerFocused = true"
    @blur="isContainerFocused = false"
    @mouseenter="isMouseOver = true"
    @mouseleave="isMouseOver = false"
  >
    <!-- Loading State -->
    <template #description>
      <span class="text-gray-600">Loading image...</span>
    </template>

    <div
      ref="previewWrapperRef"
      class="image-preview-wrapper relative size-full max-h-full min-h-24 overflow-hidden"
      @wheel.prevent="handleWheel"
    >
      <!-- Image -->
      <img
        ref="previewRef"
        :src="src"
        :alt="alt"
        class="image-preview-img cursor-grab select-none"
        :class="loading && 'invisible'"
        draggable="false"
        crossorigin="anonymous"
        @mousedown="handlePreviewMousedown"
        @dblclick="handlePreviewDblclick"
        @dragstart.prevent
        @load="handleImageLoad"
        @error="handleImageError"
      >
    </div>

    <!-- Toolbar -->
    <image-actions
      v-if="showToolbar"
      class="absolute bottom-1 left-1/2 transform opacity-0 transition-opacity -translate-x-1/2 group-hover/image:opacity-30 hover:!opacity-100"
      :show-download="showDownload"
      @rotate-counterclockwise="rotateCounterclockwise"
      @rotate-clockwise="rotateClockwise"
      @zoom-out="zoomOut"
      @reset-size="resizeToOriginalImageSize"
      @zoom-in="zoomIn"
      @download="handleDownload"
    />
    <!-- Error State -->
    <div v-if="error" class="absolute inset-0 flex flex-col items-center justify-center text-gray-600">
      <n-icon size="64" class="mb-4 text-red-500">
        <icon-ion-warning-outline />
      </n-icon>
      <p class="mb-2 text-lg font-medium">
        Failed to load image
      </p>
      <p class="text-sm opacity-75">
        {{ error }}
      </p>
    </div>
  </n-spin>
</template>

<script setup lang="ts">
import { useEventListener } from "@vueuse/core"
import { NIcon, NSpin } from "naive-ui"
import { computed, ref, watch } from "vue"
import ImageActions from "./image-actions.vue"

// Icons
import IconIonWarningOutline from "~icons/ion/warning-outline"

interface Props {
  src?: string
  alt?: string
  showToolbar?: boolean
  showDownload?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  alt: "Image preview",
  showToolbar: true,
  showDownload: true,
})

const emit = defineEmits<Emits>()

interface Emits {
  (e: "download", src: string): void
  (e: "resize", size: { width: number, height: number }): void
}

// Refs
const previewRef = ref<HTMLImageElement | null>(null)
const previewWrapperRef = ref<HTMLDivElement | null>(null)

// State
const loading = ref(true)
const error = ref("")
const isContainerFocused = ref(false)
const isMouseOver = ref(false)

// Transform state
const offsetX = ref(0)
const offsetY = ref(0)
const scale = ref(1)
const rotate = ref(0)
const scaleExp = ref(0)

// Drag state
const startX = ref(0)
const startY = ref(0)
const startOffsetX = ref(0)
const startOffsetY = ref(0)
const mouseDownClientX = ref(0)
const mouseDownClientY = ref(0)
const dragging = ref(false)

// Constants
const BLEEDING = 32
const scaleRadix = 1.5

// Computed
const fileName = computed(() => {
  if (!props.src)
    return "image"
  const parts = props.src.split("/")
  return parts[parts.length - 1] || "image"
})

// Methods
function handleKeydown(e: KeyboardEvent) {
  // Only handle keyboard events if container is focused or mouse is over it
  if (!isContainerFocused.value && !isMouseOver.value) {
    return
  }

  switch (e.key) {
    case " ":
      e.preventDefault()
      break
    case "=":
    case "+":
      zoomIn()
      break
    case "-":
      zoomOut()
      break
    case "0":
      resizeToOriginalImageSize()
      break
  }
}

function handleWheel(e: WheelEvent) {
  if (e.deltaY < 0) {
    zoomIn()
  }
  else {
    zoomOut()
  }
}

function handleMouseMove(e: MouseEvent) {
  const { clientX, clientY } = e
  offsetX.value = clientX - startX.value
  offsetY.value = clientY - startY.value
  requestAnimationFrame(derivePreviewStyle)
}

function getDerivedOffset(): { offsetX: number, offsetY: number } {
  const preview = unrefElement(previewRef)
  if (!preview)
    return { offsetX: 0, offsetY: 0 }

  const container = unrefElement(previewWrapperRef)
  if (!container)
    return { offsetX: 0, offsetY: 0 }

  const pbox = preview.getBoundingClientRect()
  const cbox = container.getBoundingClientRect()
  let nextOffsetX = 0
  let nextOffsetY = 0

  if (pbox.width <= cbox.width) {
    nextOffsetX = 0
  }
  else if (pbox.left > cbox.left) {
    nextOffsetX = (pbox.width - cbox.width) / 2
  }
  else if (pbox.right < cbox.right) {
    nextOffsetX = -(pbox.width - cbox.width) / 2
  }

  if (pbox.height <= cbox.height) {
    nextOffsetY = 0
  }
  else if (pbox.top > cbox.top) {
    nextOffsetY = (pbox.height - cbox.height) / 2
  }
  else if (pbox.bottom < cbox.bottom) {
    nextOffsetY = -(pbox.height - cbox.height) / 2
  }

  return { offsetX: nextOffsetX, offsetY: nextOffsetY }
}

let cleanupMouseEvents: (() => void) | null = null

function handleMouseUp() {
  if (cleanupMouseEvents) {
    cleanupMouseEvents()
    cleanupMouseEvents = null
  }

  dragging.value = false
  const offset = getDerivedOffset()
  offsetX.value = offset.offsetX
  offsetY.value = offset.offsetY
  derivePreviewStyle()
}

function handlePreviewMousedown(e: MouseEvent) {
  if (e.button !== 0)
    return

  const { clientX, clientY } = e
  dragging.value = true
  startX.value = clientX - offsetX.value
  startY.value = clientY - offsetY.value
  startOffsetX.value = offsetX.value
  startOffsetY.value = offsetY.value
  mouseDownClientX.value = clientX
  mouseDownClientY.value = clientY

  derivePreviewStyle()

  // Setup event listeners with VueUse
  const stopMouseMove = useEventListener(document, "mousemove", handleMouseMove)
  const stopMouseUp = useEventListener(document, "mouseup", handleMouseUp)

  cleanupMouseEvents = () => {
    stopMouseMove()
    stopMouseUp()
  }
}

function handlePreviewDblclick() {
  const originalImageSizeScale = getFitScale()
  scale.value = scale.value === originalImageSizeScale ? 1 : originalImageSizeScale
  derivePreviewStyle()
}

function getMaxScale(): number {
  const preview = unrefElement(previewRef)
  const container = unrefElement(previewWrapperRef)
  if (!preview || !container)
    return 1

  const cbox = container.getBoundingClientRect()
  const heightMaxScale = Math.max(1, preview.naturalHeight / (cbox.height - BLEEDING))
  const widthMaxScale = Math.max(1, preview.naturalWidth / (cbox.width - BLEEDING))
  return Math.max(5, heightMaxScale * 2, widthMaxScale * 2)
}

function getFitScale(): number {
  const preview = unrefElement(previewRef)
  const container = unrefElement(previewWrapperRef)
  if (!preview || !container)
    return 1

  const cbox = container.getBoundingClientRect()
  const height = cbox.height - BLEEDING
  const width = cbox.width - BLEEDING

  const heightScale = height / preview.naturalHeight
  const widthScale = width / preview.naturalWidth

  if (heightScale > 1 && widthScale > 1) {
    return 1
  }

  return Math.min(heightScale, widthScale, 1)
}

function zoomIn() {
  const maxScale = getMaxScale()
  if (scale.value < maxScale) {
    scaleExp.value += 1
    scale.value = Math.min(maxScale, scaleRadix ** scaleExp.value)
    derivePreviewStyle()
  }
}

function zoomOut() {
  if (scale.value < 0.1) {
    return
  }

  scaleExp.value -= 1
  scale.value = Math.max(0.1, scaleRadix ** scaleExp.value)
  const offset = getDerivedOffset()
  offsetX.value = offset.offsetX
  offsetY.value = offset.offsetY
  derivePreviewStyle()
}

function rotateClockwise() {
  rotate.value += 90
  derivePreviewStyle()
}

function rotateCounterclockwise() {
  rotate.value -= 90
  derivePreviewStyle()
}

function resizeToOriginalImageSize() {
  scale.value = getFitScale()
  scaleExp.value = Math.ceil(Math.log(scale.value) / Math.log(scaleRadix))
  offsetX.value = 0
  offsetY.value = 0
  derivePreviewStyle()
}

function resetScale() {
  scale.value = 1
  scaleExp.value = 0
  rotate.value = 0
  offsetX.value = 0
  offsetY.value = 0
}

function derivePreviewStyle() {
  const preview = unrefElement(previewRef)
  if (!preview)
    return

  const { style } = preview
  const transformStyle = `transform-origin: center; transform: translate(-50%, -50%) translateX(${offsetX.value}px) translateY(${offsetY.value}px) rotate(${rotate.value}deg) scale(${scale.value});`

  if (dragging.value) {
    style.cssText = `cursor: grabbing; transition: none; ${transformStyle}`
  }
  else {
    style.cssText = `cursor: grab; ${transformStyle}`
  }
}

async function handleImageLoad(e: Event) {
  error.value = ""

  // Set initial scale to fit the container

  await nextTick()
  const { naturalHeight, naturalWidth } = e.target as HTMLImageElement
  const container = unrefElement(previewWrapperRef)
  if (container) {
    const cbox = container.getBoundingClientRect()

    const height = cbox.width / naturalWidth * naturalHeight

    emit("resize", { width: cbox.width, height })
  }
  await nextTick()
  const originalScale = getFitScale()
  scale.value = originalScale
  scaleExp.value = Math.ceil(Math.log(scale.value) / Math.log(scaleRadix))
  derivePreviewStyle()

  setTimeout(() => {
    loading.value = false
  }, 100)
}

function handleImageError() {
  loading.value = false
  error.value = "Failed to load image"
}

function handleDownload() {
  if (props.src) {
    emit("download", props.src)
  }
}

// Setup event listeners with VueUse
useEventListener(document, "keydown", handleKeydown)

// Lifecycle
watch(() => props.src, () => {
  if (props.src) {
    loading.value = true
    error.value = ""
    resetScale()
  }
})

watch(() => props.src, () => {
  if (props.src) {
    loading.value = true
  }
}, { immediate: true })
</script>

<style scoped lang="sass">
.image-preview-container
  border-radius: 8px

.image-preview-img
  position: absolute
  top: 50%
  left: 50%
  transform: translate(-50%, -50%)
  width: fit-content!important
  max-width: none
  max-height: none
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1)
</style>
