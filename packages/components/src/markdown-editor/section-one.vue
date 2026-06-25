<template>
  <div class="flex items-center">
    <component
      :is="spec.component"
      v-for="(spec, i) in visibleItems"
      :key="`menu-section-one-${i}`"
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

const headingItems = ["heading"]

function generateCommandButtonComponentSpecs() {
  const extensionManager = props.editor.extensionManager
  const result: {
    component: Component
    componentProps?: Record<string, any>
    componentEvents?: any
    name: string
  }[] = []

  extensionManager.extensions.forEach((extension) => {
    const { name, options } = extension
    const { renderer } = options as {
      renderer: (props: any) => {
        component: Component
        componentProps?: Record<string, any>
        componentEvents?: any
      }
    }

    if (typeof renderer === "function" && headingItems.includes(name)) {
      const menuBtnComponentSpec = renderer({
        editor: props.editor,
        extension,
      })

      if (Array.isArray(menuBtnComponentSpec)) {
        result.push(...menuBtnComponentSpec)
      }
      else {
        result.push({ name, ...menuBtnComponentSpec })
      }
    }
  })

  return result
}

const visibleItems = computed(() => {
  return generateCommandButtonComponentSpecs()
})
</script>
