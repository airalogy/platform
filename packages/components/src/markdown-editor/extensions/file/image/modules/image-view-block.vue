<template>
  <node-view-wrapper
    class="group relative mx-auto h-fit w-fit rounded-md"
    data-drag-handle
    :class="{ 'outline outline-2 outline-offset-1 outline-primary': props.selected || isResizing }"
  >
    <n-spin
      ref="containerRef"
      :show="imageState.isServerUploading || (!imageState.imageLoaded && !imageState.error)"
      class="relative inset-0 min-w-6 flex items-center justify-center"
      content-class="h-full w-full"
      :content-style="{
        maxWidth: `min(${maxWidth}px, 100%)`,
        width: `${currentWidth}px`,
        maxHeight: `${MAX_HEIGHT}px`,
        aspectRatio: `${imageState.naturalSize.width} / ${imageState.naturalSize.height}`,
      }"
    >
      <n-image
        :src="imageState.src"
        :alt="props.node.attrs.alt"
        :title="props.node.attrs.title"
        class="h-full w-full rounded-md object-contain opacity-0"
        :class="{ 'opacity-100': imageState.imageLoaded }"
        :width="currentWidth"
        :height="currentHeight"
        @load="handleImageLoad"
        @error="handleImageError"
      >
        <template v-if="imageState.error" #error>
          <info-circled-icon class="text-destructive size-8" />
          <p className="mt-2 text-sm text-muted-foreground">
            Failed to load image
          </p>
        </template>
      </n-image>
    </n-spin>
    <!--
      <image-overlay
        v-if="imageState.error || imageState.isServerUploading"
        :error="imageState.error"
        :uploading="imageState.isServerUploading"
      /> -->

    <resize-handle
      class="left-1"
      :class="{ hidden: isResizing && activeResizeHandle === 'right' }"
      position="left"
      :is-resizing="isResizing && activeResizeHandle === 'left'"
      @pointerdown="handleResizeStart('left', $event)"
      @pointerup="handleResizeEnd"
    />

    <resize-handle
      class="right-1"
      :class="{ hidden: isResizing && activeResizeHandle === 'left' }"
      position="right"
      :is-resizing="isResizing && activeResizeHandle === 'right'"
      @pointerdown="handleResizeStart('right', $event)"
      @pointerup="handleResizeEnd"
    />

    <image-actions
      v-if="!imageState.error && imageState.imageLoaded"
      class="opacity-0 group-hover:opacity-100" :class="[{ 'opacity-60': currentWidth > 96 && props.selected }]"
      :is-link="isLink"
      :should-merge="shouldMerge"
      @download="onDownload"
      @copy="onCopy"
      @copy-id="onCopyId"
      @copy-link="onCopyLink"
    />
  </node-view-wrapper>
</template>

<script setup lang="ts">
import type { Editor, NodeViewProps } from "@tiptap/vue-3"
import type { ElementDimensions } from "../../hooks/use-drag-resize"
import type { UploadReturnType } from "../../types"
import type { CustomImageOptions } from "../types"
// import { getCachedAttachment } from "@airalogy/components/service/api/attachments"

import { blobUrlToBase64, blobUrlToFile } from "@airalogy/shared/utils"
import { NodeViewWrapper } from "@tiptap/vue-3"
import InfoCircledIcon from "~icons/heroicons/information-circle-20-solid"
import { NImage } from "naive-ui"
import { nanoid } from "nanoid"
import { useDragResize } from "../../hooks/use-drag-resize"
import { useImageActions } from "../../hooks/use-image-actions"
import ResizeHandle from "../../modules/resize-handle.vue"
import ImageActions from "./image-actions.vue"

defineOptions({
  name: "ImageViewBlock",
})

const props = defineProps<NodeViewProps>()
const MAX_HEIGHT = 1080
const MIN_HEIGHT = 48
const MIN_WIDTH = 48

interface ImageState {
  src: string
  isServerUploading: boolean
  imageLoaded: boolean
  error: boolean
  naturalSize: ElementDimensions
}

function normalizeUploadResponse(res: UploadReturnType) {
  if (typeof res === "string" || !res) {
    return {
      src: res || "",
      id: nanoid(),
    }
  }
  const { src, id, airalogyId, filename } = res
  return {
    src,
    id,
    airalogyId,
    filename,
    alt: filename,
  }
}

const containerRef = ref<HTMLDivElement | null>(null)
const activeResizeHandle = ref<"left" | "right" | null>(null)
const uploadAttemptedRef = ref(false)

const imageState = reactive<ImageState>({
  src: props.node.attrs.src,
  isServerUploading: false,
  imageLoaded: false,
  error: false,
  naturalSize: {
    width: props.node.attrs.width || MIN_WIDTH,
    height: props.node.attrs.height || MIN_HEIGHT,
  },
})

const aspectRatio = computed(() => {
  const ratio = imageState.naturalSize.width / imageState.naturalSize.height
  return Number.isFinite(ratio) ? ratio : 1
})

const containerMaxWidth = ref(Infinity)

const maxWidth = computed(() => Math.min(MAX_HEIGHT * aspectRatio.value, containerMaxWidth.value))

const { currentWidth, currentHeight, dimensions, initiateResize, isResizing } = useDragResize({
  initialWidth: props.node.attrs.width ?? imageState.naturalSize.width,
  initialHeight: props.node.attrs.height ?? imageState.naturalSize.height,
  contentWidth: imageState.naturalSize.width,
  contentHeight: imageState.naturalSize.height,
  gridInterval: 0.1,
  onDimensionsChange: ({ width, height }) => {
    props.updateAttributes({ width, height })
  },
  minWidth: MIN_WIDTH,
  minHeight: MIN_HEIGHT,
  maxWidth,
  containerMaxWidth,
})

const shouldMerge = computed(() => currentWidth.value <= 180)

const { isLink, onCopy, onCopyId, onCopyLink, onDownload } = useImageActions(computed(() => ({
  editor: props.editor,
  node: props.node,
  src: imageState.src,
  onViewClick: () => {},
})))

function handleImageLoad(event: Event) {
  const img = event.target as HTMLImageElement
  const newNaturalSize = {
    width: img.naturalWidth || MIN_WIDTH,
    height: img.naturalHeight || MIN_HEIGHT,
  }

  imageState.naturalSize = newNaturalSize
  imageState.imageLoaded = true
  imageState.error = false

  // Update container max width to ensure we have the latest value
  updateContainerMaxWidth()

  // Calculate the optimal width - either natural width or container width
  const optimalWidth = Math.min(newNaturalSize.width, containerMaxWidth.value)
  const optimalHeight = (optimalWidth / newNaturalSize.width) * newNaturalSize.height

  props.updateAttributes({
    width: optimalWidth,
    height: optimalHeight,
    alt: img.alt,
    title: img.title,
    src: img.src,
  })

  // Update the dimensions reactive ref
  dimensions.value = {
    width: optimalWidth,
    height: optimalHeight,
  }
}

function handleImageError() {
  if (imageState.src?.startsWith("airalogy.id")) {
    return
  }
  imageState.error = true
  imageState.imageLoaded = false
}

function handleResizeStart(handle: "left" | "right", event: PointerEvent) {
  activeResizeHandle.value = handle
  initiateResize(handle)(event)
}

function handleResizeEnd() {
  activeResizeHandle.value = null
}

function updateContainerMaxWidth() {
  if (!containerRef.value)
    return

  const el = (props.editor as any).contentComponent.vnode.el
  if (!el)
    return

  const editorWidth = el.clientWidth
  if (editorWidth) {
    containerMaxWidth.value = editorWidth
  }
  else {
    const computedWidth = Number.parseFloat(getComputedStyle(el).getPropertyValue("width"))
    if (Number.isFinite(computedWidth) && computedWidth > 0) {
      containerMaxWidth.value = computedWidth
    }
    else {
      const inlineWidth = el.style.width
      containerMaxWidth.value = inlineWidth ? Number.parseFloat(inlineWidth) : currentWidth.value
    }
  }
}

function getCachedAttachment(airalogyId: string) {
  const imageExtension = props.editor.options.extensions.find(ext => ext.name === "airalogyImage")
  const { resolveFile } = (imageExtension?.options || {}) as CustomImageOptions
  if (resolveFile) {
    return resolveFile(airalogyId)
  }
  return null
}

watch(() => props.node.attrs.airalogyId, async (airalogyId) => {
  try {
    if (!airalogyId) {
      return
    }

    const attachment = await getCachedAttachment(airalogyId)
    if (attachment) {
      const resolvedSrc = typeof attachment.src === "string" ? attachment.src : ""
      const { id } = attachment

      if (!resolvedSrc) {
        return
      }

      imageState.src = resolvedSrc
      imageState.isServerUploading = false
      imageState.imageLoaded = true
      imageState.error = false

      props.updateAttributes({
        src: resolvedSrc,
        id,
      })
    }
  }
  catch (error) {
    console.error("Failed to fetch attachment:", error)
    imageState.error = true
    imageState.imageLoaded = false
  }
}, { immediate: true })

async function convertToBase64AndUpdateState(src: string): Promise<boolean> {
  try {
    const base64 = await blobUrlToBase64(src)
    imageState.src = base64
    imageState.error = false
    imageState.isServerUploading = false
    imageState.imageLoaded = true
    props.updateAttributes({ src: base64 })
    return true
  }
  catch (error) {
    console.error("Failed to convert to base64:", error)
    imageState.error = true
    imageState.isServerUploading = false
    imageState.imageLoaded = false
    return false
  }
}

// Handle blob URLs
async function handleBlobImage() {
  const { src, airalogyId, fileName = "image.png" } = props.node.attrs

  // If we have an airalogyId, we assume the image is already uploaded/handled by cache logic
  // and we don't need to re-upload even if src is a blob (which might be stale)
  if (airalogyId) {
    return
  }

  // Check if the source is a blob URL and we haven't processed it yet
  if (!src || !src.startsWith("blob:") || uploadAttemptedRef.value) {
    return
  }

  // Mark upload as attempted to prevent duplicate processing
  uploadAttemptedRef.value = true

  // Find the image extension and get the upload function
  const imageExtension = props.editor.options.extensions.find(ext => ext.name === "airalogyImage")
  const { uploadFn } = (imageExtension?.options || {}) as CustomImageOptions

  if (!uploadFn) {
    await convertToBase64AndUpdateState(src)
    return
  }

  try {
    // If upload function exists, prepare for server upload
    imageState.isServerUploading = true
    imageState.error = false

    // Get the blob from the URL
    const file = await blobUrlToFile(src, fileName)

    // Upload using the extension's upload function
    const res = await uploadFn(file, props.editor as Editor, imageExtension?.options)
    const normalized = normalizeUploadResponse(res)

    // Update state with the normalized data
    if (!normalized.src) {
      throw new Error("No source URL returned from upload")
    }

    imageState.src = normalized.src
    imageState.isServerUploading = false

    // Update attributes with the complete normalized data
    props.updateAttributes(normalized)
  }
  catch (error) {
    console.error("Failed to upload image:", error)
    // Fallback to base64 when upload fails
    await convertToBase64AndUpdateState(src)
  }
}

watch(() => props.node.attrs.src, handleBlobImage)

onMounted(async () => {
  await nextTick()
  updateContainerMaxWidth()

  window.addEventListener("resize", updateContainerMaxWidth)

  // Call the blob handler
  await handleBlobImage()
})

onUnmounted(() => {
  window.removeEventListener("resize", updateContainerMaxWidth)
})
</script>

<style scoped></style>
