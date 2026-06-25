<template>
  <div
    v-show="isVisible"
    ref="bubbleMenuRef"
    class="selection-bubble-menu"
    :class="{ 'selection-bubble-menu--show': isVisible }"
  >
    <div class="selection-bubble-menu__content">
      <n-button-group>
        <n-button
          quaternary
          size="tiny"
          @click="handleSendToChat"
        >
          <template #icon>
            <n-icon><icon-tabler-message-plus /></n-icon>
          </template>
          {{ $t("chat.askAira") }}
        </n-button>
        <n-button
          quaternary
          size="tiny"
          @click="handleAddToChat"
        >
          <template #icon>
            <n-icon><icon-tabler-square-rounded-plus /></n-icon>
          </template>
          {{ $t("chat.addToChat") }}
        </n-button>
      </n-button-group>
    </div>
    <div ref="arrowRef" class="selection-bubble-menu__arrow" />
  </div>
</template>

<script lang="ts" setup>
import { type BubbleMenuEventName, type BubbleMenuEventPayload, type SelectionState, useBubbleMenu } from "@airalogy/composables"
import { bubbleMenuEventKey } from "@airalogy/shared/constants/eventKey"
import { $t } from "@airalogy/shared/locales"
import { NButton, NButtonGroup, NIcon } from "naive-ui"
import { ref } from "vue"

interface Props {
  containerRef: HTMLElement
  updateSection?: () => SelectionState | null
}

const props = defineProps<Props>()

const isEditorBubbleActive = injectLocal("isEditorBubbleActive", ref(false))

const allowDisplayRef = computed(() => !isEditorBubbleActive.value)
const bubbleMenuRef = ref<HTMLElement | null>(null)
const arrowRef = ref<HTMLElement | null>(null)
const bubbleMenuEventBus = useEventBus<BubbleMenuEventName, BubbleMenuEventPayload>(bubbleMenuEventKey)

const { isVisible, selectedText, showBubbleMenuAtElement, currentData } = useBubbleMenu({
  containerRef: () => props.containerRef,
  bubbleMenuRef,
  arrowRef,
  allowDisplayRef,
  updateSection: props.updateSection,
})

function handleChatAction(actionType: "sendToChat" | "addToChat") {
  const value = selectedText.value || currentData.value
  if (value) {
    bubbleMenuEventBus.emit("triggerChatAction", { event: actionType, value })
  }
}

function handleSendToChat() {
  handleChatAction("sendToChat")
}

function handleAddToChat() {
  handleChatAction("addToChat")
}

bubbleMenuEventBus.on((event, payload) => {
  if (event === "triggerBubbleMenu") {
    const { dom, data } = payload as { dom: HTMLElement | null, data: any }
    if (dom) {
      showBubbleMenuAtElement(dom)
      currentData.value = data
    }
    else {
      currentData.value = null
    }
  }
})
</script>

<style lang="sass">
.selection-bubble-menu
  position: fixed
  z-index: 1000
  opacity: 0
  pointer-events: none

  &--show
    opacity: 1
    transform: scale(1)
    pointer-events: auto

  &__content
    position: relative
    background: white
    padding: 4px 4px 2px
    border-radius: 6px
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1)
    border: 1px solid #eee

  &__arrow
    position: absolute
    width: 0
    height: 0
    border: 6px solid transparent

    // Default top placement
    border-top-color: #eee
    &::after
      content: ''
      position: absolute
      top: -7px
      left: -6px
      border: 6px solid transparent
      border-top-color: white

    // Handle bottom placement
    [style*="--placement: bottom"] &
      border-top-color: transparent
      border-bottom-color: #eee
      &::after
        top: -5px
        border-top-color: transparent
        border-bottom-color: white
</style>
