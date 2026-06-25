<template>
  <n-popconfirm
    v-model:visible="editLinkDialogVisible"
    :title="$t('editor.extensions.Link.edit.control.title')"
    :append-to-body="true"
  >
    <n-form :model="linkAttrs" label-position="right" size="small">
      <n-form-item :label="$t('editor.extensions.Link.edit.control.href')" prop="href">
        <n-input v-model="linkAttrs.href" autocomplete="off" />
      </n-form-item>

      <n-form-item prop="openInNewTab">
        <n-checkbox v-model="linkAttrs.openInNewTab">
          {{ $t("editor.extensions.Link.edit.control.open_in_new_tab") }}
        </n-checkbox>
      </n-form-item>
    </n-form>

    <template #trigger>
      <div>
        <menu-bar-item
          :command="openEditLinkDialog"
          :enable-tooltip="enableTooltip"
          :tooltip="$t('editor.extensions.Link.edit.tooltip')"
          :icon="Edit"
        />
      </div>
    </template>
    <template #action>
      <n-button size="small" round @click="closeEditLinkDialog">
        {{ $t("editor.extensions.Link.edit.control.cancel") }}
      </n-button>

      <n-button type="primary" size="small" round @mousedown.prevent @click="updateLinkAttrs">
        {{ $t("editor.extensions.Link.edit.control.confirm") }}
      </n-button>
    </template>
  </n-popconfirm>
</template>

<script setup lang="ts">
import type { Editor } from "@tiptap/vue-3"

import MenuBarItem from "@airalogy/components/markdown-editor/menu-bar-item.vue"

import { $t } from "@airalogy/shared/locales"
import Edit from "~icons/tabler/edit"

interface ILinkAttrs {
  href: string
  target?: string | null
  rel?: string | null
  class?: string | null
}

interface IProps {
  editor: Editor
  initLinkAttrs: ILinkAttrs
}

const props = defineProps<IProps>()

const enableTooltip = inject("enableTooltip", true)

const linkAttrs = ref<ILinkAttrs & { openInNewTab: boolean }>({
  openInNewTab: true,
  ...props.initLinkAttrs,
})

const editLinkDialogVisible = ref(false)

function openEditLinkDialog() {
  editLinkDialogVisible.value = true
}

function closeEditLinkDialog() {
  editLinkDialogVisible.value = false
}

function updateLinkAttrs() {
  props.editor.commands.setLink(linkAttrs.value)

  closeEditLinkDialog()
}
</script>
