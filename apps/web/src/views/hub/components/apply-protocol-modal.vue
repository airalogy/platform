<template>
  <n-button v-if="props.showTrigger" v-auth v-bind="props.buttonProps" @click.stop="showModal">
    <template v-if="props.showIcon" #icon>
      <n-icon v-bind="props.iconProps">
        <icon-local-reuse />
      </n-icon>
    </template>
    {{ props.trigger }}
  </n-button>
  <n-modal
    :show="isShown"
    preset="card"
    :title="props.title"
    :bordered="false"
    size="huge"
    class="min-w-160 w-70vw"
    content-class="!px-0"
    footer-class="flex items-center justify-end gap-4"
    :mask-closable="false"
    @update:show="handleSetShow"
    @after-leave="restoreForm"
  >
    <n-form
      ref="formRef"
      :model="model"
      :rules="rules"
      size="large"
      class="max-h-70vh overflow-y-auto px-8"
    >
      <slot name="prefix" />
      <n-form-item label="Based project" path="combinedId" required>
        <n-cascader
          v-model:value="model.combinedId"
          :options="options"
          placeholder="Choose a base project"
          check-strategy="child"
          required
          :theme-overrides="{ columnWidth: 'fit-content', menuBorderRadius: '10px' }"
          @update:value="handleRestoreValidation"
          @update-show="fetchLabs"
        >
          <template #empty>
            <n-empty description="No Project" />
          </template>
        </n-cascader>
      </n-form-item>
      <n-form-item label="Protocol display name" path="name">
        <n-input
          v-model:value="model.name"
          type="text"
          :maxlength="30"
          required
          placeholder="Enter protocol display name"
          :allow-input="(value: string) => !value.includes('.')"
          @update:value="handleUpdateUid"
        />
      </n-form-item>
      <n-form-item label="Protocol id" path="uid">
        <common-id-input
          v-model="model.uid"
          type="protocol"
          :lab-uid="currentLab?.uid"
          :project-uid="currentProject?.uid"
          :show-prefix="!!model.combinedId"
          :disabled="!model.combinedId"
          :check-loading="checkLoading"
          @update:value="handleUpdateName"
          @check="handleValidateName"
        />
      </n-form-item>
      <slot name="suffix" />
    </n-form>
    <template #footer>
      <n-button size="medium" :disabled="loading" @click="handleCancel">
        Cancel
      </n-button>
      <n-button
        size="medium"
        type="primary"
        :disabled="loading"
        :loading="loading"
        @click="handleConfirm"
      >
        {{ props.label }}
      </n-button>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import type { ProjectCascaderOption as Option } from "@/components/apply-steps/project-options"
import type { ProtocolModels } from "@airalogy/shared/types"
import type { ButtonProps, IconProps } from "naive-ui"
import { groupProjectsByLabOptions } from "@/components/apply-steps/project-options"
import { createDisplayNameValidator, createUidValidator, useFormRules, useLoading, useNaiveForm, useShowModal } from "@/composables"
import { postReuseProtocol } from "@/service/api/project-protocols"
import { fetchProjectList } from "@/service/api/projects"
import { postCheckProtocolIdDuplicate } from "@/service/api/protocol"
import { convertDisplayname } from "@/utils/convertDisplayname"
import commonIdInput from "@airalogy/components/src/common/common-id-input.vue"
import { useClosableMessage } from "@airalogy/composables"

const props = withDefaults(defineProps<IProps>(), {
  showIcon: true,
  trigger: "Apply Protocol",
  buttonProps: () => ({}),
  label: "Apply Protocol",
  show: false,
  options: () => [],
  checkDuplicate: true,
})

const emit = defineEmits<IEmits>()

interface IProps {
  showIcon?: boolean
  iconProps?: IconProps
  buttonProps?: ButtonProps & { class?: string }
  trigger?: string
  protocolId: string
  label?: string
  title?: string
  showTrigger?: boolean
  show?: boolean
  options?: Option[]
  checkDuplicate?: boolean
}

interface FormModel {
  name: string | null
  uid: string | null
  combinedId: string | null
}

interface IEmits {
  (e: "modal:apply-protocol", val: ProtocolModels.ProtocolInfo): void
  (e: "modal:close"): void
  (e: "modal:open"): void
  (e: "update:model", val: FormModel): void
}

const { isShown, showModal, hideModal, setModalStatus } = useShowModal(props.show)
const { defaultRequiredRule } = useFormRules()
const { formRef, validate, restoreValidation } = useNaiveForm()
const message = useClosableMessage()

const defaultOptions = ref<Option[] | null>(props.options.length ? props.options : null)
const options = ref<Option[]>(props.options)
const hasFetched = ref(false)

const { loading, startLoading, endLoading } = useLoading()
const {
  loading: checkLoading,
  startLoading: startCheckLoading,
  endLoading: endCheckLoading,
} = useLoading()

const rules: Record<keyof FormModel, App.Global.FormRule[]> = {
  name: createDisplayNameValidator("Protocol display name"),
  uid: createUidValidator({ fieldName: "Protocol ID", checkDuplicate }),
  combinedId: [defaultRequiredRule],
}

const model = ref<FormModel>({
  name: null,
  uid: null,
  combinedId: null,
})

const currentLab = computed(() => {
  const [labUid] = model.value.combinedId?.split("|") || []
  return options.value.find(it => it.value === labUid) as Option | undefined
})

const currentProject = computed(() => {
  const combinedId = model.value.combinedId
  const targetProject = currentLab.value
    ?.children
    ?.find(it => it.value === combinedId)
  return targetProject as Option | undefined
})

async function fetchLabs(show: boolean) {
  if (!show || hasFetched.value) {
    return
  }

  try {
    const data = await fetchProjectList({
      permissionAction: "create_protocol",
      page: 1,
      pageSize: 9999,
    })

    if (data) {
      const filteredOptions = groupProjectsByLabOptions(data.projects)

      if (filteredOptions.length > 0) {
        options.value = filteredOptions
      }
      else if (defaultOptions.value && defaultOptions.value.length > 0) {
        options.value = defaultOptions.value
      }
    }
    await nextTick(() => {
      hasFetched.value = true
    })
  }
  catch (e) {
    message.error((e as Error).message)
  }
}

const shouldUpdateUid = ref(true)

async function checkDuplicate(payload: { uid: string }) {
  const labUid = currentLab.value?.uid
  const projectUid = currentProject.value?.uid
  if (!labUid || !projectUid) {
    return {
      data: { valid: false, message: "Please select a lab and project" },
    }
  }
  if (!props.checkDuplicate) {
    return { data: { valid: true } }
  }

  const res = await postCheckProtocolIdDuplicate({
    labUid,
    projectUid,
    uid: payload.uid,
  })

  return res
}

async function handleUpdateUid(displayName: string) {
  if (model.value.uid && !shouldUpdateUid.value)
    return
  else if (!model.value.uid)
    shouldUpdateUid.value = true

  const name = await convertDisplayname(displayName)
  model.value.uid = name
}

function handleUpdateName(val: string) {
  if (shouldUpdateUid.value) {
    shouldUpdateUid.value = false
  }
}

async function handleValidateName() {
  if (!model.value.uid || !model.value.combinedId) {
    return
  }

  startCheckLoading()
  try {
    await validate(
      (errors) => {
        if (!errors) {
          message.success("Protocol id is available.")
        }
      },
      (rule) => {
        return rule?.key === "check:duplicate"
      },
    )
  }
  catch (e) {
    // NOPE
  }
  finally {
    endCheckLoading()
  }
}

function handleCancel() {
  hideModal()
}

async function handleConfirm() {
  try {
    startLoading()

    await validate()
    const { name, uid } = model.value
    const labId = currentLab.value?.id
    const projectId = currentProject.value?.id

    if (!labId) {
      message.error("Invalid lab selection")
      endLoading()
      return
    }

    if (!name || !uid || !labId || !projectId) {
      message.error("Invalid form data")
      endLoading()
      return
    }

    const data = await postReuseProtocol({
      sourceProtocolId: props.protocolId,
      targetProjectUUID: projectId,
      name,
      uid,
    })

    if (data) {
      message.success(`Successfully applied protocol to project ${currentProject.value?.label}`)
      emit("modal:apply-protocol", { lab_uid: currentLab.value?.uid, project_uid: currentProject.value?.uid, ...data })
      hideModal()
    }
  }
  finally {
    endLoading()
  }
}

function handleSetShow(val: boolean) {
  setModalStatus(val)
}

function restoreForm() {
  model.value = {
    name: null,
    uid: null,
    combinedId: null,
  }

  hasFetched.value = false
}

function handleRestoreValidation() {
  restoreValidation("combinedId")
}

watch(
  () => isShown.value,
  (shown) => {
    if (shown) {
      emit("modal:open")
    }
    else {
      emit("modal:close")
    }
  },
)

defineExpose({
  showModal,
  hideModal,
})
</script>
