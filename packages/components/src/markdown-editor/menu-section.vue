<template>
  <component :is="item" v-for="(item, i) in standaloneItems" :key="`menu-section-${i}`" />

  <template v-if="groupItems">
    <n-dropdown v-for="(item, i) in groupItems" :key="`menu-section-${i}`" :options="item.options" trigger="click">
      <div class="dropdown-trigger">
        <slot>
          <menu-bar-item
            :tooltip="item.tooltip || ''"
            :icon="item.icon"
            :label="item.label"
            :disabled="props.disabled"
            show-arrow
          />
        </slot>
      </div>
    </n-dropdown>
  </template>
</template>

<script setup lang="tsx">
import type { Editor } from "@tiptap/vue-3"
import type { DropdownOption } from "naive-ui"
import type { Component } from "vue"
import type { ExtensionRenderParams, ExtensionWithRenderer, MenuButtonSpec, VisibleItem } from "./extensions"
import type { MenuSectionConfig } from "./types/editor"
import { isEqual } from "lodash-es"
import MenuBarItem from "./menu-bar-item.vue"

interface Props {
  editor: Editor
  items: MenuSectionConfig["items"]
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  items: () => [],
  disabled: false,
})

const enableTooltip = inject("enableTooltip", true)

const extensions = shallowRef<ExtensionWithRenderer<any>[]>([])

const standaloneItems = shallowRef<Component[]>([])
const groupItems = shallowRef<(MenuSectionConfig & { options: DropdownOption[] })[]>([])
// const dropdownOptions = shallowRef<DropdownOption[]>([])

function generateCommandButtonComponentSpec(info: VisibleItem, renderLabel?: ExtensionRenderParams["renderLabel"], eventHandlers?: MenuSectionConfig["eventHandlers"]): MenuButtonSpec | MenuButtonSpec[] | null {
  const { extension, item } = info

  const name = typeof item === "string" ? item : item.name
  const label = typeof item === "string" ? undefined : item.label

  const { renderer } = extension.options

  if (!renderer)
    return null

  const menuBtnComponentSpec = renderer({
    editor: props.editor,
    extension,
    renderLabel,
    disabled: props.disabled,
    eventHandlers,
  })

  return Array.isArray(menuBtnComponentSpec)
    ? menuBtnComponentSpec.map(spec => ({ name, label, spec }))
    : {
        spec: menuBtnComponentSpec,
        name,
        label,
      }
}

function renderSpec(itemSpec: MenuButtonSpec, otherProps: Record<string, any> = {}): Component {
  const { label, name, spec } = itemSpec
  const { component, componentProps, componentEvents } = spec

  return () => h(component, {
    label,
    name,
    ...toValue(componentProps),
    ...toValue(componentEvents),
    ...otherProps,
  })
}
// function generateDropdownOption(spec: MenuButtonSpec, key: string): DropdownOption | null {
//   if (!spec) {
//     return null
//   }

//   return {
//     type: "render",
//     key,
//     render: () => renderSpec(spec),
//   }
// }

function getItemExtension(item?: string | MenuSectionConfig): VisibleItem | null {
  const list = extensions.value
  if (!list || !item) {
    return null
  }

  const name = typeof item === "string" ? item : item.name

  const extension = list.find(extension => extension.name === name)
  if (!extension) {
    return null
  }

  return { extension, item }
}

watch(() => props.editor.extensionManager.extensions, (val) => {
  extensions.value = markRaw(toRaw(val)) as ExtensionWithRenderer<any>[]
}, { immediate: true })

watch(() => props.items, (val, oldVal) => {
  if (isEqual(val, oldVal)) {
    return
  }
  const standaloneResult: Component[] = []
  const groupResult: (MenuSectionConfig & { options: DropdownOption[] })[] = []
  val.forEach((config) => {
    if (typeof config === "string") {
      const info = getItemExtension(config)
      if (!info) {
        return
      }

      const spec = generateCommandButtonComponentSpec(info, undefined, info.extension.options.eventHandlers)
      if (!spec) {
        return
      }

      if (Array.isArray(spec)) {
        spec.forEach((spec) => {
          standaloneResult.push(renderSpec(spec))
        })
      }
      else {
        standaloneResult.push(renderSpec(spec))
      }
    }
    else if (config?.items) {
      const { items, name, label, tooltip, icon, renderLabel, eventHandlers } = config
      const options: DropdownOption[] = []
      const groupItem = { name, label, tooltip, options, icon }

      items.forEach((item) => {
        const info = getItemExtension(item)
        if (!info) {
          return
        }

        const spec = generateCommandButtonComponentSpec(info, renderLabel, eventHandlers)
        if (!spec) {
          return
        }

        if (Array.isArray(spec)) {
          spec.forEach((spec) => {
            options.push({
              type: "render",
              key: spec.name,
              render: renderSpec(spec, { triggerWrapperClass: "w-full", triggerClass: "w-full !justify-start" }),
            })
          })
        }
        else {
          options.push({
            type: "render",
            key: spec.name,
            render: renderSpec(spec, { triggerWrapperClass: "w-full", triggerClass: "w-full !justify-start" }),
          })
        }
      })
      groupResult.push(groupItem)
    }
  })

  standaloneItems.value = standaloneResult
  groupItems.value = groupResult
}, { immediate: true })
</script>

<style scoped lang="sass">
</style>
