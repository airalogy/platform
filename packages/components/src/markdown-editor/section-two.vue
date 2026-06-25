<template>
  <div class="menu-section flex items-center gap-0.5">
    <component
      :is="spec.component"
      v-for="(spec, i) in visibleItems"
      :key="`menu-section-two-${i}`"
      :enable-tooltip="enableTooltip"
      v-bind="spec.componentProps"
      v-on="spec.componentEvents || {}"
    />
  </div>
</template>

<script setup lang="tsx">
import type { Editor } from "@tiptap/vue-3"
import type { Component } from "vue"

interface Props {
  editor: Editor
}

const props = defineProps<Props>()
const enableTooltip = inject("enableTooltip", true)

// Define items with their order
const textAndListItems = [
  "bold",
  "italic",
  "strike",
  "codeBlock",
  "fontSize",
  // "textColor",
  // "highlight",
  "bulletList",
  "orderedList",
  "taskList",
  "indent",
  "outdent",
] as const

interface MenuButtonSpec {
  component: Component
  componentProps?: Record<string, any>
  componentEvents?: any
  name: string
}

function generateCommandButtonComponentSpecs(): MenuButtonSpec[] {
  const extensionManager = props.editor.extensionManager

  return textAndListItems
    .map((name): MenuButtonSpec | MenuButtonSpec[] | null => {
      const extension = extensionManager.extensions.find(ext => ext.name === name)
      if (!extension)
        return null

      const { renderer } = extension.options as {
        renderer?: (props: any) => {
          component: Component
          componentProps?: Record<string, any>
          componentEvents?: any
        }
      }

      if (!renderer)
        return null

      const menuBtnComponentSpec = renderer({
        editor: props.editor,
        extension,
      })

      return Array.isArray(menuBtnComponentSpec)
        ? menuBtnComponentSpec.map(spec => ({ name, ...spec }))
        : { name, ...menuBtnComponentSpec }
    })
    .filter((spec): spec is MenuButtonSpec | MenuButtonSpec[] => spec !== null)
    .flat()
}

const visibleItems = computed(() => generateCommandButtonComponentSpecs())
</script>
