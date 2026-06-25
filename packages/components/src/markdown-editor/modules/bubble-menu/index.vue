<template>
  <bubble-menu v-if="editor" :editor="editor" :tippy-options="tippyOptions">
    <div
      :class="{ 'tiptap-editor__menu-bubble--active': bubbleMenuEnable }"
      class="tiptap-editor__menu-bubble"
    >
      <link-bubble-menu v-if="activeMenu === 'link'" :editor="editor!">
        <template #prepend>
          <div
            v-if="textMenuEnable"
            class="tiptap-editor__command-button"
            @mousedown.prevent
            @click="linkBack"
          >
            <n-icon :component="ArrowLeft" />
          </div>
        </template>
      </link-bubble-menu>

      <template v-else-if="activeMenu === 'default'">
        <component :is="item" v-for="(item, i) in menuItems" :key="`command-button${i}`" />
      </template>
    </div>
  </bubble-menu>
</template>

<script setup lang="ts">
import type { BubbleMenuPluginProps } from "@tiptap/extension-bubble-menu"
import type { Selection } from "@tiptap/pm/state"
import type { Editor } from "@tiptap/vue-3"
import type { ExtensionWithRenderer, RendererSpec } from "../../extensions"
import LinkBubbleMenu from "@airalogy/components/markdown-editor/modules/link/link-bubble-item.vue"
import { getMarkRange } from "@tiptap/core"

import { AllSelection, TextSelection } from "@tiptap/pm/state"
import { BubbleMenu } from "@tiptap/vue-3"
import ArrowLeft from "~icons/tabler/arrow-left"

defineOptions({ name: "MenuBubble" })

const props = withDefaults(defineProps<IProps>(), { menuBubbleOptions: () => ({}) })

interface IProps {
  editor: Editor | null
  menuBubbleOptions?: Record<string, any>
}

enum MenuType {
  NONE = "none",
  DEFAULT = "default",
  LINK = "link",
}

const activeMenu = ref(MenuType.NONE)
const isLinkBack = ref(false)
const enableTooltip = inject("enableTooltip", true)

const linkMenuEnable = computed((): boolean => {
  if (!props.editor) {
    return false
  }

  const { schema } = props.editor
  return !!schema.marks.link
})

const textMenuEnable = computed((): boolean => {
  if (!props.editor) {
    return false
  }

  const extensionManager = props.editor.extensionManager
  return extensionManager.extensions.some((extension) => {
    return extension.options.bubble
  })
})

const menuItems = shallowRef<Component[]>([])

const hasAvailableSpecs = computed(() =>
  (activeMenu.value !== MenuType.NONE && (activeMenu.value === MenuType.LINK || menuItems.value.length > 0)),
)

const bubbleMenuEnable = computed((): boolean => {
  const isEnabled = (linkMenuEnable.value || (textMenuEnable.value && hasAvailableSpecs.value))
  return isEnabled
})

const isLinkSelection = computed((): boolean => {
  if (!props.editor) {
    return false
  }

  const { state } = props.editor
  const { tr } = state
  const { selection } = tr

  return $_isLinkSelection(selection)
})

function linkBack() {
  setMenuType(MenuType.DEFAULT)
  isLinkBack.value = true
}

function setMenuType(type: MenuType) {
  activeMenu.value = type
}

function $_isLinkSelection(selection: Selection) {
  if (!props.editor) {
    return false
  }

  const { schema } = props.editor
  const linkType = schema.marks.link
  if (!linkType)
    return false
  if (!selection)
    return false

  const { $from, $to } = selection
  const range = getMarkRange($from, linkType)
  if (!range)
    return false

  return range.to === $to.pos
}

function $_getCurrentMenuType(): MenuType {
  if (!props.editor) {
    return MenuType.NONE
  }

  if (isLinkSelection.value)
    return MenuType.LINK
  if (
    props.editor.state.selection instanceof TextSelection
    || props.editor.state.selection instanceof AllSelection
  ) {
    return MenuType.DEFAULT
  }
  return MenuType.NONE
}

const isEditorBubbleActive = injectLocal("isEditorBubbleActive", ref(false))

const tippyOptions: BubbleMenuPluginProps["tippyOptions"] = {
  onShow: () => {
    if (!hasAvailableSpecs.value) {
      return false
    }

    isEditorBubbleActive.value = true
  },
  onHide: () => {
    isEditorBubbleActive.value = false
  },

  placement: "auto",
}

watch(
  () => props.editor?.state.selection,
  (selection) => {
    if (selection && $_isLinkSelection(selection)) {
      if (!isLinkBack.value) {
        setMenuType(MenuType.LINK)
      }
    }
    else {
      activeMenu.value = $_getCurrentMenuType()
      isLinkBack.value = false
    }
  },
)
const bubbleExtensions = computed(() => {
  if (!props.editor) {
    return []
  }

  return props.editor.extensionManager.extensions.filter(extension => extension.options.bubble) as ExtensionWithRenderer<any>[]
})

function generateCommandButtonComponent(item: RendererSpec): Component {
  const { component, componentProps, componentEvents } = item
  return () => h(component, {
    ...toValue(componentProps),
    ...toValue(componentEvents),
  })
}

function generateCommandButtonComponentSpecs(extensions: ExtensionWithRenderer<any>[]): Component [] {
  return extensions
    .map((extension): Component | Component[] | null => {
      const { renderer } = extension.options

      if (!renderer)
        return null

      const menuBtnComponentSpec = renderer({
        editor: props.editor!,
        extension,
      })

      return Array.isArray(menuBtnComponentSpec)
        ? menuBtnComponentSpec.map(generateCommandButtonComponent)
        : generateCommandButtonComponent(menuBtnComponentSpec)
    })
    .filter((spec): spec is Component | Component[] => spec !== null)
    .flat()
}

watch(() => bubbleExtensions.value, (extensions) => {
  if (!extensions.length) {
    return
  }

  menuItems.value = generateCommandButtonComponentSpecs(extensions)
}, { immediate: true })
</script>

<style lang="sass">
.tiptap-editor__menu-bubble
  z-index: 1100

.tiptap-editor__command-button
  display: flex
  align-items: center
  justify-content: center
  padding: 0.5rem
  cursor: pointer
  border-radius: 0.25rem
  transition: background-color 0.2s ease
  &:hover
    background-color: rgba(0, 0, 0, 0.05)
</style>
