<template>
  <n-button v-bind="props.buttonProps" @click.stop="showModal">
    <template v-if="props.showIcon" #icon>
      <add-research-icon v-if="compact" />
      <add-circle-outline v-else />
    </template>
    <span v-if="showTrigger">
      {{ props.trigger }}
    </span>
  </n-button>
  <n-modal
    :show="isShown"
    preset="card"
    :title=" props.title"
    :bordered="false"
    size="huge"
    class="min-w-160 w-70vw"
    :mask-closable="false"
    @update:show="handleSetShow"
    @after-leave="restoreForm"
  >
    <n-form
      ref="formRef"
      :model="model"
      :rules="rules"
      size="large"
      class="max-h-70vh overflow-y-auto"
    >
      <n-form-item label="Select lab and project" path="combinedId" required>
        <n-cascader
          ref="cascadeRef"
          v-model:value="model.combinedId"
          :options="options"
          placeholder="Choose a lab and project"
          check-strategy="child"
          :on-load="handleLoad"
          required
          remote
          :theme-overrides="{ columnWidth: 'fit-content', menuBorderRadius: '10px' }"
          @update-show="fetchLabs"
        >
          <template #empty>
            <n-empty description="No Project" />
          </template>
        </n-cascader>
      </n-form-item>

      <!-- Protocol Selection Table -->
      <n-form-item label="Select protocol" path="protocolId" required>
        <n-data-table
          v-if="model.combinedId"
          v-model:checked-row-keys="checkedRowKeys"
          class="mt-2 h-fit w-full"
          :columns="columns"
          :data="protocolsData"
          :loading="protocolsLoading"
          :pagination="pagination"
          :row-key="(row: ProtocolModels.ProjectProtocolInfo) => row.id"
          :row-props="rowProps"
          @update:checked-row-keys="handleRowKeysChange"
          @update:page="handlePageChange"
        />
        <n-empty v-else description="Please select a lab and project first" class="min-h-30 w-full select-none justify-center" />
      </n-form-item>
    </n-form>
    <div class="mt-3 flex items-center justify-end">
      <n-button size="medium" class="mr-4" :disabled="loading" @click="handleCancel">
        Cancel
      </n-button>
      <n-button
        size="medium"
        type="primary"
        :disabled="loading || !model.protocolId"
        :loading="loading"
        @click="handleConfirm"
      >
        Confirm
      </n-button>
    </div>
  </n-modal>
</template>

<script setup lang="ts">
import type { ProtocolModels } from "@airalogy/shared/types"
import type { ButtonProps } from "naive-ui/es/button"
import type { CascaderInst } from "naive-ui/es/cascader"
import { useFormRules, useLoading, useNaiveForm, useShowModal } from "@/composables"
import { fetchProtocols as getProtocols } from "@/service/api/project-protocols"
import { fetchProjectList } from "@/service/api/projects"
import { fetchUserLabs } from "@/service/api/users"
import { useAuthStore } from "@/store/modules/auth"
import { useClosableMessage } from "@airalogy/composables"
import { formatDate } from "@airalogy/shared/utils"
import AddCircleOutline from "~icons/ion/add-circle-outline"
import { type CascaderOption, type DataTableColumns, NText } from "naive-ui"

interface IProps {
  showIcon?: boolean
  buttonProps?: ButtonProps & { class?: string }
  compact?: boolean
  showTrigger?: boolean
  trigger?: string
  project?: Api.Project.MyProjectInfo | null
  title?: string
  mode?: "record" | "protocol"
}

const props = withDefaults(defineProps<IProps>(), {
  showIcon: true,
  trigger: "Select Protocol",
  showTrigger: true,
  buttonProps: () => ({}),
  compact: true,
  project: null,
  mode: "record",
})

const emits = defineEmits<{
  (e: "modal:select-protocol", payload: EmitPayload): void
  (e: "modal:close"): void
  (e: "modal:open"): void
}>()

interface FormModel {
  combinedId: string | null
  protocolId: string | null
}

interface EmitPayload {
  labUid: string
  projectUid: string
  protocolName: string
  protocolId: string
  labId: string
  projectId: string
  protocolUid: string
  protocolVersion?: string
}

const { defaultRequiredRule } = useFormRules()
const { formRef, validate } = useNaiveForm()
const message = useClosableMessage()
const { isShown, showModal, hideModal, setModalStatus } = useShowModal()

const cascadeRef = ref<CascaderInst | null>(null)
const authStore = useAuthStore()

const initModel: FormModel = {
  combinedId: null,
  protocolId: null,
}

const model = ref<FormModel>({ ...initModel })
const defaultOptions = ref<CascaderOption[] | null>(null)
const options = ref<CascaderOption[]>([])
const unitOptions = ref<{ label: string, value: string, id: string }[]>([])
const protocolsData = ref<ProtocolModels.ProjectProtocolInfo[]>([])
const checkedRowKeys = ref<(string | number)[]>([])

// Pagination for the data table
const pagination = reactive({
  page: 1,
  pageSize: 5,
  itemCount: 0,
  onChange: (page: number) => {
    pagination.page = page
  },
  onUpdatePageSize: (pageSize: number) => {
    pagination.pageSize = pageSize
    pagination.page = 1
  },
})

const currentLabUid = computed(() => {
  const [labUid] = model.value.combinedId?.split("|") || []
  return labUid
})

const currentProjectId = computed(() => {
  if (!model.value.combinedId)
    return null

  const [labUid] = model.value.combinedId.split("|") || []
  const targetProject = options.value
    .find(it => it.value === labUid)
    ?.children
    ?.find(it => it.value === model.value.combinedId)

  return targetProject?.id as string
})

const rules = computed(() => ({
  combinedId: [defaultRequiredRule],
  protocolId: [defaultRequiredRule],
}))

const { loading, startLoading, endLoading } = useLoading()
const { loading: protocolsLoading, startLoading: startProtocolsLoading, endLoading: endProtocolsLoading } = useLoading()

// Define columns for the data table
const columns = computed((): DataTableColumns<ProtocolModels.ProjectProtocolInfo> => [
  {
    type: "selection",
    multiple: false,
  },
  {
    title: "Name",
    key: "name",
    minWidth: 150,
    render: row => h(NText, null, { default: () => row.name }),
  },
  {
    title: "ID",
    key: "id",
    render: row => h(NText, null, { default: () => row.airalogy_id }),
  },
  {
    title: "Records",
    key: "records_count",
    width: 100,
    render: row => h(NText, null, { default: () => row.records_count || 0 }),
  },
  {
    title: "Created",
    key: "createdAt",
    width: 150,
    render: (row) => {
      if (row.created_at) {
        return h(NText, null, { default: () => formatDate(row.created_at, "date-time") })
      }
      return ""
    },
  },
])

// Row props for the data table
function rowProps(row: ProtocolModels.ProjectProtocolInfo) {
  return {
    style: "cursor: pointer",
    onClick: () => {
      // Toggle selection when row is clicked
      if (checkedRowKeys.value.includes(row.id)) {
        checkedRowKeys.value = []
        model.value.protocolId = null
      }
      else {
        checkedRowKeys.value = [row.id]
        model.value.protocolId = row.uid
      }
    },
  }
}

function handleRowKeysChange(keys: (string | number)[]) {
  // For single selection, only keep the last selected key
  if (keys.length > 1) {
    checkedRowKeys.value = [keys[keys.length - 1]]
  }
  else {
    checkedRowKeys.value = keys
  }

  // Update the form model to match the selected unit
  if (checkedRowKeys.value.length > 0) {
    const selectedProtocol = protocolsData.value.find(unit => unit.id === checkedRowKeys.value[0])
    if (selectedProtocol) {
      model.value.protocolId = selectedProtocol.uid
    }
  }
  else {
    model.value.protocolId = null
  }
}

function handlePageChange(page: number) {
  pagination.page = page
  fetchProtocols()
}

function handleCancel() {
  hideModal()
}

async function handleConfirm() {
  await validate()

  if (!model.value.combinedId || !model.value.protocolId) {
    message.error("Please select a lab, project and unit")
    return
  }

  startLoading()
  try {
    const [labUid] = model.value.combinedId.split("|") || []
    const targetLab = options.value.find(it => it.value === labUid)
    const targetProject = targetLab?.children?.find(it => it.value === model.value.combinedId)
    const selectedProtocolId = checkedRowKeys.value[0]
    const selectedProtocol = protocolsData.value.find(unit => unit.id === selectedProtocolId)

    if (!targetLab || !targetProject || !selectedProtocol) {
      message.error("Failed to find selected protocol information")
      return
    }
    const { uid, id, name, latest_version: protocolVersion } = selectedProtocol

    emits("modal:select-protocol", {
      labUid: targetLab.value as string,
      labId: targetLab.id as string,
      projectUid: targetProject.uid as string,
      projectId: targetProject.id as string,
      protocolUid: uid,
      protocolId: id,
      protocolName: name,
      protocolVersion,
    })

    hideModal()
  }
  catch (e) {
    message.error((e as Error).message)
  }
  finally {
    endLoading()
  }
}

async function handleLoad(option: CascaderOption) {
  const { value, id: labId } = option

  try {
    const data = await fetchProjectList({
      labId: labId as string,
      page: 1,
      pageSize: 9999,
    })
    if (data) {
      const children = data.projects.map(({ uid, name, id }) => {
        return {
          label: `${name} (${uid})`,
          value: `${value}|${id}`,
          depth: 2,
          isLeaf: true,
          uid,
          id,
        }
      })
      await nextTick(() => {
        option.children = children
      })
    }
  }
  catch (e) {
    message.error((e as Error).message)
  }
}

async function fetchProtocols() {
  if (!currentProjectId.value)
    return

  startProtocolsLoading()
  try {
    const response = await getProtocols({
      projectId: currentProjectId.value,
      page: pagination.page,
      pageSize: pagination.pageSize,
    })

    console.log("Protocols data:", response?.data)

    if (response?.data) {
      protocolsData.value = response.data.protocols
      pagination.itemCount = response.data.total_count

      // Also maintain the old structure for backward compatibility
      unitOptions.value = response.data.protocols.map(unit => ({
        label: `${unit.name} (${unit.uid})`,
        value: unit.uid,
        id: unit.id,
      }))

      // Clear selection when loading new units
      checkedRowKeys.value = []
      model.value.protocolId = null
    }
  }
  catch (e) {
    message.error((e as Error).message)
  }
  finally {
    endProtocolsLoading()
  }
}

const hasFetched = ref(false)

async function fetchLabs(show: boolean) {
  if (!show || hasFetched.value) {
    return
  }

  try {
    const data = await fetchUserLabs(authStore.userInfo.id, {
      page: 1,
      pageSize: 9999,
    })

    if (data) {
      const filteredOptions = data.labs.map((it) => {
        const { name, id, uid } = it
        return { label: `${name} (${uid})`, value: uid, depth: 1, isLeaf: false, id }
      })

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

function handleSetShow(val: boolean) {
  setModalStatus(val)
}

watch(
  () => isShown.value,
  (shown) => {
    if (shown) {
      setDefaultValue(props.project)
      emits("modal:open")
    }
    else {
      hasFetched.value = false
      emits("modal:close")
    }
  },
)

watch(
  () => model.value.combinedId,
  () => {
    model.value.protocolId = null
    checkedRowKeys.value = []
    if (model.value.combinedId) {
      pagination.page = 1
      fetchProtocols()
    }
    else {
      protocolsData.value = []
      unitOptions.value = []
    }
  },
)

function setDefaultValue(project: Api.Project.MyProjectInfo | null) {
  if (!project)
    return

  const { lab_name, group_name, lab_uid, name, id, uid, lab_id } = project
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
  fetchProtocols()
}

function restoreForm() {
  model.value = { ...initModel }
  unitOptions.value = []
  protocolsData.value = []
  checkedRowKeys.value = []
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
