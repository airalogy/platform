<template>
  <n-dropdown
    :show="isShow" :options="addOptions" placement="bottom-start" :render-label="renderLabel"
    @clickoutside="handleClickOutside"
  >
    <n-button
      :theme-overrides="buttonThemeOverrides"
      class="ml-5 h-[36px] rounded-2 px-3"
      icon-placement="right"
      :aria-label="$t('common.new')"
      :title="$t('common.new')"
      @click="showDropdown"
    >
      <add-icon class="mr-3" />
      <template #icon>
        <dropdown-icon filled :expended="isShow" />
      </template>
    </n-button>
  </n-dropdown>
</template>

<script setup lang="ts">
import type { DropdownMixedOption, DropdownOption } from "naive-ui/es/dropdown/src/interface"
import { useRouterPush } from "@/composables/useRouterPush"
import { useInstanceStore } from "@/store/modules/instance"
import CreateLabModal from "@/views/labs/modules/lab/create-lab-modal.vue"
import AddProtocolModal from "@/views/project-protocols/modules/add-protocol-modal.vue"
import SelectProtocolModal from "@/views/project-protocols/modules/select-protocol-modal.vue"
import CreateProjectModal from "@/views/projects/modules/create-project-modal.vue"
import { useBoolean } from "@airalogy/composables"
import { $t } from "@airalogy/shared/locales"
import { computed } from "vue"
import { buttonThemeOverrides } from "../global-header/constants"

defineOptions({ name: "GlobalAddNew" })

const { bool: isShow, setFalse: hideDropdown, setTrue: showDropdown } = useBoolean()

const { bool: isModalOpen, setFalse: closeModal, setTrue: openModal } = useBoolean()

const instanceStore = useInstanceStore()
const addOptions = computed<DropdownMixedOption[]>(() => ([
  { label: $t("common.newRecord"), key: "new-record" },
  { label: $t("common.newProtocol"), key: "new-protocol" },
  { label: $t("common.newProject"), key: "new-project" },
  ...(!instanceStore.isSingleLab ? [{ label: $t("common.newLab"), key: "new-lab" }] : []),
]))

const { routerPushByKey } = useRouterPush()

type DropdownKey = "new-project" | "new-protocol" | "new-lab" | "new-protocol" | "new-record"

function renderLabel(option: DropdownOption) {
  const key = option.key as DropdownKey
  const label = option.label as string

  // if (key === "new-protocol") {
  //   return h(SelectProtocolModal, {
  //     "title": "Add Protocol",
  //     "showIcon": false,
  //     "buttonProps": {
  //       text: true,
  //       type: "default",
  //       class: "!color-base-text h-full w-full justify-start",
  //     },
  //     "trigger": label,
  //     "mode": "protocol",
  //     "onModal:open": () => openModal(),
  //     "onModal:close": () => {
  //       hideDropdown()
  //       closeModal()
  //     },
  //     "onModal:select-protocol": async (payload) => {
  //       const { labUid, projectUid, protocolUid = "", protocolVersion = "" } = payload

  //       await routerPushByKey("protocol-editor", {
  //         params: { labUid, projectUid, protocolUid, protocolVersion },
  //       })
  //     },
  //   })
  // }

  if (key === "new-record") {
    return h(SelectProtocolModal, {
      "title": $t("common.addRecord"),
      "showIcon": false,
      "buttonProps": {
        text: true,
        type: "default",
        class: "!color-base-text h-full w-full justify-start",
      },
      "trigger": label,
      "mode": "record",
      "onModal:open": () => openModal(),
      "onModal:close": () => {
        hideDropdown()
        closeModal()
      },
      "onModal:select-protocol": async (payload) => {
        const { labUid, projectUid, protocolUid = "", protocolVersion = "" } = payload

        await routerPushByKey("add-protocol-record", {
          params: { labUid, projectUid, protocolUid, protocolVersion },
        })
      },
    })
  }

  if (key === "new-project") {
    return h(CreateProjectModal, {
      "showIcon": false,
      "buttonProps": {
        text: true,
        type: "default",
        class: "!color-base-text h-full w-full justify-start",
      },
      "trigger": label,
      "onModal:open": () => openModal(),
      "onModal:close": () => {
        hideDropdown()
        closeModal()
      },
      "onModal:new-project": async (project: Api.Project.MyProjectInfo) => {
        const { lab_uid: labUid, uid: projectUid } = project

        await routerPushByKey("project-protocols", {
          params: { labUid, projectUid },
        })
      },
    })
  }
  if (key === "new-lab") {
    return h(CreateLabModal, {
      "showIcon": false,
      "buttonProps": {
        text: true,
        class: "!color-base-text h-full w-full justify-start",
      },
      "trigger": label,
      "onModal:open": () => openModal(),
      "onModal:close": () => {
        hideDropdown()
        closeModal()
      },
      "onModal:new-lab": async (item: Api.Lab.LabInfo) => {
        const { uid: labUid } = item

        await routerPushByKey("lab-projects", { params: { labUid } })
      },
    })
  }
  if (key === "new-protocol") {
    return h(AddProtocolModal, {
      "showIcon": false,
      "buttonProps": {
        text: true,
        class: "!color-base-text h-full w-full justify-start",
      },
      "trigger": label,
      "onModal:open": () => openModal(),
      "onModal:close": () => {
        hideDropdown()
        closeModal()
      },
      "onModal:new-protocol": async (payload: {
        labUid: string
        id: string
        labId: string
        projectUid: string
        name: string
        uid: string
      }) => {
        const { uid, projectUid, labUid } = payload

        await routerPushByKey("protocol-info", {
          params: {
            labUid,
            protocolUid: uid,
            projectUid,
          },
        })
      },
    })
  }

  return h("span", null, { default: () => option.label })
}

function handleClickOutside() {
  if (isModalOpen.value) {
    return
  }

  hideDropdown()
}
</script>
