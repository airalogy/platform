import type { IRecordDataKey } from "@airalogy/shared"
import type { MentionNodeAttrs } from "@airalogy/shared/chat/mention"
import { arrow, autoUpdate, flip, inline, type Middleware, shift, useFloating, type VirtualElement } from "@floating-ui/vue"
import { type MaybeRefOrGetter, useDebounceFn, useEventListener } from "@vueuse/core"
import { computed, type ComputedRef, nextTick, onUnmounted, ref, type Ref, toValue, watch } from "vue"

// Types
export interface SelectionState {
  range: Range
  text: string
  rect: DOMRect
}

export interface FloatingConfig {
  strategy: "fixed" | "absolute"
  placement: "top" | "bottom"
  padding: number
  middleware: Middleware[]
}

export interface UseBubbleMenuOptions {
  containerRef: MaybeRefOrGetter<HTMLElement | null | undefined>
  bubbleMenuRef: MaybeRefOrGetter<HTMLElement | null | undefined>
  allowDisplayRef: Ref<boolean>
  arrowRef?: MaybeRefOrGetter<HTMLElement | null | undefined>
  enabled?: MaybeRefOrGetter<boolean>
  hideDelay?: number
  displayDelay?: number
  placement?: "top" | "bottom"
  padding?: number
  updateSection?: () => SelectionState | null
}

export interface UseBubbleMenuReturn {
  isVisible: Ref<boolean>
  currentData: Ref<any>
  selectedText: ComputedRef<string>
  update: () => Promise<void>
  reset: () => void
  showBubbleMenuAtElement: (element: HTMLElement) => void
}

// Utilities
function createVirtualElement(rect: DOMRect, range: Range, contextElement: HTMLElement): VirtualElement {
  return {
    getBoundingClientRect: () => rect,
    contextElement,
    getClientRects: () => range.getClientRects(),
  }
}

// Composables
function useSelectionManager(containerRef: MaybeRefOrGetter<HTMLElement | null | undefined>, updateSectionMethod?: () => SelectionState | null) {
  const currentSelection = ref<SelectionState | null>(null)

  function getSelectionState(): SelectionState | null {
    if (updateSectionMethod) {
      return updateSectionMethod()
    }

    const selection = window.getSelection()
    if (!selection?.rangeCount)
      return null

    const range = selection.getRangeAt(0)
    if (!range || range.collapsed)
      return null

    const text = selection.toString().trim()
    if (!text)
      return null

    return { range, text, rect: range.getBoundingClientRect() }
  }

  function isSelectionWithinContainer(range: Range): boolean {
    const container = toValue(containerRef)
    return container ? container.contains(range.commonAncestorContainer) : false
  }

  function updateCurrentSelection() {
    currentSelection.value = getSelectionState()
  }

  return {
    currentSelection,
    getSelectionState,
    isSelectionWithinContainer,
    updateCurrentSelection,
  }
}

function useVirtualElementManager(containerRef: MaybeRefOrGetter<HTMLElement | null | undefined>) {
  const virtualElement = ref<VirtualElement | null>(null)

  function updateVirtualElement(selectionState: SelectionState) {
    const container = toValue(containerRef)
    if (!container)
      return

    virtualElement.value = createVirtualElement(selectionState.rect, selectionState.range, container)
  }

  function setVirtualElementFromDOMElement(element: HTMLElement) {
    const container = toValue(containerRef)
    if (!container)
      return

    virtualElement.value = createVirtualElement(
      element.getBoundingClientRect(),
      { getClientRects: () => element.getClientRects() } as Range,
      container,
    )
  }

  return {
    virtualElement,
    updateVirtualElement,
    setVirtualElementFromDOMElement,
  }
}

function useFloatingManager(
  virtualElement: Ref<VirtualElement | null>,
  bubbleMenuRef: MaybeRefOrGetter<HTMLElement | null | undefined>,
  arrowRef: MaybeRefOrGetter<HTMLElement | null | undefined>,
  options: Pick<UseBubbleMenuOptions, "placement" | "padding">,
) {
  const config: FloatingConfig = {
    strategy: "fixed",
    placement: options.placement ?? "top",
    padding: options.padding ?? 8,
    middleware: [
      inline(),
      shift({ padding: options.padding ?? 8 }),
      flip({
        fallbackPlacements: [options.placement === "top" ? "bottom" : "top"],
        fallbackStrategy: "bestFit",
      }),
      arrow({ element: arrowRef, padding: 5 }),
    ],
  }

  const floatingElement = computed(() => toValue(bubbleMenuRef) ?? null)
  const { floatingStyles, middlewareData, update } = useFloating(virtualElement, floatingElement, {
    strategy: config.strategy,
    placement: config.placement,
    whileElementsMounted: autoUpdate,
    middleware: config.middleware,
  })

  watch([floatingStyles, middlewareData], ([styles, data]) => {
    const bubbleMenu = toValue(bubbleMenuRef)
    if (!bubbleMenu)
      return

    const arrowElement = toValue(arrowRef)
    if (arrowElement && data.arrow) {
      const { x: arrowX, y: arrowY } = data.arrow
      Object.assign(arrowElement.style, {
        position: "absolute",
        left: arrowX ? `${arrowX}px` : "",
        top: arrowY ? `${arrowY}px` : "",
      })
    }

    Object.assign(bubbleMenu.style, styles)
  }, { flush: "post" })

  return { update }
}

function useEventHandlers(
  options: {
    containerRef: MaybeRefOrGetter<HTMLElement | null | undefined>
    bubbleMenuRef: MaybeRefOrGetter<HTMLElement | null | undefined>
    enabled: MaybeRefOrGetter<boolean>
    onUpdate: () => Promise<void>
    onSelectionChange: () => void
    isVisible: Ref<boolean>
    selectedText: ComputedRef<string>
  },
) {
  const isMouseOverMenu = ref(false)
  const { onUpdate, onSelectionChange, selectedText, isVisible, bubbleMenuRef } = options

  if (window) {
    useEventListener(window.document, "selectionchange", onSelectionChange, { passive: true })
    useEventListener(window.document, "mouseup", onUpdate, { passive: true })
  }

  useEventListener(bubbleMenuRef, "mouseenter", () => {
    isMouseOverMenu.value = true
  })

  useEventListener(bubbleMenuRef, "mouseleave", () => {
    isMouseOverMenu.value = false
    if (!selectedText.value) {
      isVisible.value = false
    }
  })

  useEventListener(window, "scroll", onUpdate, { capture: true, passive: true })
  useEventListener(window, "resize", onUpdate, { passive: true })

  return { isMouseOverMenu }
}

// Main composable
export function useBubbleMenu({
  containerRef,
  bubbleMenuRef,
  allowDisplayRef,
  arrowRef,
  enabled = true,
  placement = "top",
  padding = 8,
  updateSection,
}: UseBubbleMenuOptions): UseBubbleMenuReturn {
  const isVisible = ref(false)
  const isUpdating = ref(false)
  const currentData = ref(null)

  const {
    currentSelection,
    getSelectionState,
    isSelectionWithinContainer,
    updateCurrentSelection,
  } = useSelectionManager(containerRef, updateSection)

  const {
    virtualElement,
    updateVirtualElement,
    setVirtualElementFromDOMElement,
  } = useVirtualElementManager(containerRef)

  const { update: updateFloating } = useFloatingManager(virtualElement, bubbleMenuRef, arrowRef, { placement, padding })

  const selectedText = computed(() => currentSelection.value?.text ?? "")
  const debouncedUpdate = useDebounceFn(update, 16)

  const { isMouseOverMenu } = useEventHandlers({
    containerRef,
    bubbleMenuRef,
    enabled,
    onUpdate: debouncedUpdate,
    onSelectionChange: handleSelectionChange,
    isVisible,
    selectedText,
  })

  function resetState() {
    if (isMouseOverMenu.value)
      return

    isVisible.value = false
    virtualElement.value = null
    currentSelection.value = null
  }

  async function update() {
    if (isUpdating.value)
      return
    isUpdating.value = true

    try {
      const container = toValue(containerRef)
      const bubbleMenu = toValue(bubbleMenuRef)
      const isEnabled = toValue(enabled)

      if (!container || !bubbleMenu || !isEnabled) {
        resetState()
        return
      }

      const selectionState = getSelectionState()
      if (!selectionState || !isSelectionWithinContainer(selectionState.range)) {
        resetState()
        return
      }

      currentSelection.value = selectionState
      updateVirtualElement(selectionState)
      updateFloating()

      if (!isMouseOverMenu.value) {
        await nextTick()
        isVisible.value = true
      }
    }
    finally {
      isUpdating.value = false
    }
  }

  function handleSelectionChange() {
    resetState()
    updateCurrentSelection()
  }

  onUnmounted(resetState)

  function showBubbleMenuAtElement(element: HTMLElement) {
    const container = toValue(containerRef)
    if (!container)
      return

    setVirtualElementFromDOMElement(element)

    void nextTick(async () => {
      const isEnabled = toValue(enabled)
      if (isEnabled) {
        await updateFloating()
        isVisible.value = true
      }
    })
  }

  return {
    isVisible: computed(() => isVisible.value && allowDisplayRef.value),
    selectedText,
    currentData,
    update,
    reset: resetState,
    showBubbleMenuAtElement,
  }
}

export type BubbleMenuEventName = "sendToChat" | "addToChat" | "triggerChatAction" | "triggerBubbleMenu"
export interface AddToChatPayload {
  prop: string
  scope: IRecordDataKey
  value: string
  type: "string" | "number" | "boolean" | "object" | "array"
  mentionAttrs: MentionNodeAttrs
}
export type BubbleMenuEventPayload = { event: "sendToChat" | "addToChat", value: string | AddToChatPayload } | { dom: HTMLElement | null, data: any } | AddToChatPayload | undefined | string
