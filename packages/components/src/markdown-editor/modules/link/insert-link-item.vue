<template>
  <menu-bar-item
    :is-active="editor.isActive('link')"
    :command="openAddLinkDialog"
    :enable-tooltip="enableTooltip"
    :tooltip="$t('editor.extensions.Link.add.tooltip')"
    :icon="Link"
  >
    <template #default="{ isActive, handleClick, themeOverrides, icon, label }">
      <n-popconfirm
        v-model:show="addLinkDialogVisible"
        :title="$t('editor.extensions.Link.add.control.title')"
        content-class="w-80"
        placement="bottom"
        :show-icon="false"
      >
        <n-form :model="linkAttrs" label-placement="top" size="small" class="w-full" :show-feedback="false">
          <n-form-item :label="$t('editor.extensions.Link.add.control.href')" path="href" class="my-2">
            <n-input v-model="linkAttrs.href" autocomplete="off" type="textarea" autosize class="w-full" placeholder="Enter link here" />
          </n-form-item>
          <n-form-item :label="$t('editor.extensions.Link.add.control.name')" path="name" class="my-2">
            <n-input v-model="linkAttrs.name" autocomplete="off" type="textarea" autosize class="w-full" placeholder="Enter link display name here" />
          </n-form-item>

          <n-form-item :label="$t('editor.extensions.Link.add.control.open_in_new_tab')" path="openInNewTab">
            <n-switch v-model="linkAttrs.openInNewTab" />
          </n-form-item>
        </n-form>

        <template #trigger>
          <n-button
            quaternary
            :type="isActive ? 'primary' : 'default'"
            size="medium"
            :theme-overrides="themeOverrides"
            class="w-full justify-start"
            @click="handleClick"
          >
            <template v-if="icon" #icon>
              <n-icon :component="icon" />
            </template>
            <span v-if="label">{{ label }}</span>
          </n-button>
        </template>
        <template #action>
          <n-button size="small" @click="closeAddLinkDialog">
            {{ $t("editor.extensions.Link.add.control.cancel") }}
          </n-button>

          <n-button type="primary" size="small" @mousedown.prevent @click="addLink">
            {{ $t("editor.extensions.Link.add.control.confirm") }}
          </n-button>
        </template>
      </n-popconfirm>
    </template>
  </menu-bar-item>
</template>

<script setup lang="ts">
import type { Editor } from "@tiptap/core"
import MenuBarItem from "@airalogy/components/markdown-editor/menu-bar-item.vue"

import { $t } from "@airalogy/shared/locales"

import Link from "~icons/tabler/link"

defineOptions({ name: "InsertLinkItem" })

const props = defineProps<IProps>()

interface IProps {
  editor: Editor
}

const enableTooltip = inject("enableTooltip", true)
const linkAttrs = ref({
  href: "",
  name: "",
  openInNewTab: true,
})

const addLinkDialogVisible = ref(false)

watch(addLinkDialogVisible, () => {
  linkAttrs.value = { href: "", name: "", openInNewTab: true }
})

function openAddLinkDialog() {
  addLinkDialogVisible.value = true
}

function closeAddLinkDialog() {
  addLinkDialogVisible.value = false
}

function addLink() {
  if (linkAttrs.value.openInNewTab) {
    props.editor.commands.setLink({
      href: linkAttrs.value.href,
      target: "_blank",
    })
  }
  else {
    props.editor.commands.setLink({ href: linkAttrs.value.href })
  }

  closeAddLinkDialog()
}
</script>
