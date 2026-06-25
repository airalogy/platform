<template>
  <n-button v-bind="props.buttonProps" @click.stop="showModal">
    <template v-if="props.showIcon" #icon>
      <add-research-icon v-if="compact" />
      <add-circle-outline v-else />
    </template>
    <span v-if="showTrigger">
      {{ triggerLabel }}
    </span>
  </n-button>
  <n-modal
    :show="isShown"
    preset="card"
    :title="modalTitle"
    :bordered="false"
    size="huge"
    class="min-w-160 w-70vw"
    content-class="max-h-80vh overflow-y-auto"
    :mask-closable="false"
    @update:show="handleSetShow"
    @after-leave="handleAfterLeave"
    @before-enter="showSteps"
  >
    <protocol-steps v-if="shouldShowSteps" ref="protocolStepsRef" :protocol-info="protocolInfo" :project-info="props.project" @cancel="handleCancel" @success="handleSuccess" />
  </n-modal>
</template>

<script setup lang="ts">
import type { ProtocolModels } from "@airalogy/shared/types"
import type { CascaderOption } from "naive-ui"
import ProtocolSteps from "@/components/apply-steps/protocol-steps.vue"

import { useBoolean, useShowModal } from "@/composables"
import { $t } from "@/locales"
import AddCircleOutline from "~icons/ion/add-circle-outline"
import { type ButtonProps, NButton } from "naive-ui/es/button"
import { useProvideProtocolInfoStore } from "../hooks/useProtocolInfoStore"

interface IProps {
  showIcon?: boolean
  buttonProps?: ButtonProps & { class?: string }
  compact?: boolean
  showTrigger?: boolean
  trigger?: string
  project?: Api.Project.MyProjectInfo | null
  showSelect?: boolean
}
const props = withDefaults(defineProps<IProps>(), {
  showIcon: true,
  showTrigger: true,
  buttonProps: () => ({}),
  compact: true,
  lab: null,
  project: null,
  showSelect: true,
})

const emits = defineEmits<IEmits>()
const triggerLabel = computed(() => props.trigger ?? $t("common.new"))
const modalTitle = computed(() => $t("page.protocol.apply.modalTitle"))

const protocolStepsRef = ref<InstanceType<typeof ProtocolSteps> | null>(null)

interface FormModel {
  uid: string | null
  name: string | null
  combinedId: string | null
  protocol: number
}

export interface IEmits {
  (
    e: "modal:new-protocol",
    val: {
      id: string
      uid: string
      labUid: string
      labId: string
      projectUid: string
      name: string
    },
  ): void
  (e: "modal:close"): void
  (e: "modal:open"): void
}
const { isShown, showModal, hideModal, setModalStatus } = useShowModal()
const { bool: shouldShowSteps, setTrue: showSteps, setFalse: hideSteps } = useBoolean(true)

const { protocolInfo } = useProvideProtocolInfoStore(null)

const initModel: FormModel = {
  uid: null,
  name: null,
  combinedId: null,
  protocol: 1,
}

const model = ref<FormModel>({ ...initModel })

const defaultOptions = ref<CascaderOption[] | null>(null)
const options = ref<CascaderOption[]>([])

function handleCancel() {
  hideModal()
}

function handleSuccess(res?: ProtocolModels.ProtocolResponseInfo | null) {
  if (res) {
    // const { uid: projectUid, lab_uid: labUid, lab_name: labName, name: projectName, id: projectId, lab_id: labId } = props.project || {}
    const { uid, id, name, lab_uid: labUid, lab_id: labId, project_uid: projectUid, project_id: projectId } = res

    protocolInfo.value = { ...res, lab: { id: labId, uid: labUid! }, project: { id: projectId, uid: projectUid! } } as any

    emits("modal:new-protocol", { id, uid, labUid: labUid!, labId: labId!, projectUid: projectUid!, name: name! })
  }
  // hideModal()
}

const hasFetched = ref(false)

function handleSetShow(val: boolean) {
  setModalStatus(val)
}

function handleAfterLeave() {
  hideSteps()
  restoreForm()
}

watch(
  () => isShown.value,
  (shown) => {
    if (shown) {
      setDefaultValue(props.project)
      showSteps()
      emits("modal:open")
    }
    else {
      hasFetched.value = false
      restoreForm()
      emits("modal:close")
    }
  },
)

function setDefaultValue(project: Api.Project.MyProjectInfo | null) {
  if (!project) {
    return
  }

  const { lab_name, group_name, lab_uid, name, id, uid, lab_id } = project
  // const { uid: labUid = "" } = lab || {}
  // const defaultVal = `${lab_uid}_${id}`
  const defaultVal = `${lab_uid}|${uid}`

  defaultOptions.value = [
    {
      label: `${lab_name || group_name}(${lab_uid})`,
      value: lab_uid,
      depth: 1,
      isLeaf: false,
      id: lab_id,
      uid: lab_uid,
      children: [{ label: `${name}(${uid})`, value: defaultVal, depth: 2, isLeaf: true, id, uid }],
    },
  ]

  if (options.value && options.value.length === 0) {
    options.value = defaultOptions.value
  }

  model.value.combinedId = defaultVal
}

function restoreForm() {
  model.value = { ...initModel }
}

watch(
  () => props.project,
  (project) => {
    setDefaultValue(project)
  },
  { immediate: true },
)
</script>

<style scoped lang="sass">
:deep(.n-base-selection)
  --n-height: 40px!important
  --n-color: #F7F8F9!important
  border-radius: 8px
</style>
