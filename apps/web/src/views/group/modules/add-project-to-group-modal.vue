<template>
  <n-button v-bind="props.buttonProps" @click.stop="showModal">
    <template v-if="props.showIcon" #icon>
      <add-circle-outline />
    </template>
    {{ props.trigger }}
  </n-button>
  <n-modal
    :show="isShown"
    preset="card"
    :title="$t('page.group.addProjectToGroup')"
    :bordered="false"
    size="huge"
    class="w-160"
    :mask-closable="false"
    @update:show="handleSetShow"
  >
    <n-form ref="formRef" :model="model" :rules="rules" size="large" class="mb-5">
      <n-form-item :label="$t('page.group.addProjectModal.targetGroupLabel')" path="targetGroupId">
        <n-select
          v-model:value="model.targetGroupId"
          :options="groupList"
          :placeholder="$t('page.group.addProjectModal.targetGroupPlaceholder')"
          filterable
          required
          @update:value="handleGroupChange"
        />
      </n-form-item>

      <n-form-item v-if="model.targetGroupId" :label="$t('page.group.addProjectModal.projectLabel')" path="projectIdList">
        <n-transfer
          v-model:value="model.projectIdList"
          :options="transferOptions"
          :filter="filterProjects"
          filterable
        />
      </n-form-item>
    </n-form>
    <div class="flex items-center justify-end">
      <n-button size="medium" class="mr-4" :disabled="loading" @click="handleCancel">
        {{ $t("common.cancel") }}
      </n-button>
      <n-button
        size="medium"
        type="primary"
        :disabled="loading || !model.targetGroupId || model.projectIdList.length === 0"
        :loading="loading"
        @click="handleConfirm"
      >
        {{ $t("common.confirm") }}
      </n-button>
    </div>
  </n-modal>
</template>

<script setup lang="ts">
import type { SelectOption, TransferOption } from "naive-ui"
import { useFormRules, useLoading, useNaiveForm, useShowModal } from "@/composables"
import { addGroupsProjects, fetchGroupsList } from "@/service/api/groups"
import { fetchProjectList } from "@/service/api/projects"
import { useClosableMessage } from "@airalogy/composables"
import { $t } from "@airalogy/shared/locales"
import AddCircleOutline from "~icons/ion/add-circle-outline"
import { type ButtonProps, NButton } from "naive-ui/es/button"
import { ProjectRole } from "../../../enum"

interface IProps {
  showIcon?: boolean
  buttonProps?: ButtonProps & { class?: string }
  compact?: boolean
  trigger?: string
  id: string | number
  labInfo?: Api.Lab.LabInfo | null
  groupInfo?: Api.Groups.MyGroupsInfo | null
}

const props = withDefaults(defineProps<IProps>(), {
  showIcon: true,
  trigger: $t("page.group.addProjectToGroup"),
  buttonProps: () => ({ class: "ml-2" }),
  compact: true,
  labInfo: null,
  groupInfo: null,
})

const emits = defineEmits<IEmits>()

interface FormModel {
  targetGroupId: string | null
  projectIdList: string[]
}

interface IEmits {
  (e: "modal:new-project", val: SelectOption[]): void
  (e: "modal:close"): void
  (e: "modal:open"): void
}
const { defaultRequiredRule } = useFormRules()
const { formRef, validate } = useNaiveForm()
const message = useClosableMessage()
const { isShown, showModal, hideModal, setModalStatus } = useShowModal()

const rules: Record<keyof FormModel, App.Global.FormRule[]> = {
  targetGroupId: [defaultRequiredRule],
  projectIdList: [defaultRequiredRule],
}

const model = ref<FormModel>({
  targetGroupId: null,
  projectIdList: [],
})
const { loading, startLoading, endLoading } = useLoading()

const groupList = ref<SelectOption[]>([])
const projectList = ref<SelectOption[]>([])
const transferOptions = ref<TransferOption[]>([])

function handleCancel() {
  hideModal()
}

function handleSetShow(val: boolean) {
  setModalStatus(val)
}

// Fetch available groups in the lab
async function fetchLabGroups() {
  if (!props.labInfo?.id) {
    return
  }

  startLoading()
  try {
    const result = await fetchGroupsList({ labId: props.labInfo.id, page: 1, pageSize: 100 })
    if (result) {
      groupList.value = result.groups.map(({ name, id, uid }) => ({
        label: name || uid,
        value: id,
      }))
    }
  }
  catch (error) {
    message.error("Failed to fetch groups")
  }
  finally {
    endLoading()
  }
}

// Fetch available projects in the lab
async function handleFetchProjectList() {
  if (!props.labInfo?.id) {
    return
  }

  startLoading()
  try {
    const result = await fetchProjectList({ labId: props.labInfo.id, page: 1, pageSize: 999 })
    if (result) {
      projectList.value = result.projects.map(
        ({ name, uid, id }) => ({
          label: name || uid,
          value: id,
          role: 2,
        }),
      )

      transferOptions.value = result.projects.map(
        ({ name, uid, id }) => ({
          label: name || uid,
          value: id,
          disabled: false,
        }),
      )
    }
  }
  catch (error) {
    message.error("Failed to fetch projects")
  }
  finally {
    endLoading()
  }
}

// Handle group selection change
function handleGroupChange(groupId: string | null) {
  if (groupId) {
    model.value.projectIdList = []
  }
}

// Filter function for transfer component
function filterProjects(pattern: string, option: TransferOption) {
  return option.label?.toString().toLowerCase().includes(pattern.toLowerCase())
}

async function handleConfirm() {
  await validate()

  const groupId = model.value.targetGroupId
  if (!groupId) {
    return
  }

  startLoading()

  const { projectIdList } = model.value

  const projectsToAdd = projectIdList.map(id => ({
    project_id: id,
    role: ProjectRole.RECORDER as const,
  }))

  const response = await Promise.allSettled(
    projectsToAdd.map((project) => {
      return addGroupsProjects(groupId, project)
    }),
  )

  endLoading()

  const successList = response
    .map((res, idx) => {
      if (res.status === "rejected" || !res.value) {
        return null
      }

      const { data, error } = res.value

      if (data) {
        const projectId = projectIdList[idx]
        return transferOptions.value.find(it => it.value === projectId)
      }

      if (error) {
        message.error(error.message)
      }

      return null
    })
    .filter(Boolean) as TransferOption[]

  if (successList.length > 0) {
    const selectedGroupName = groupList.value.find(g => g.value === groupId)?.label
    message.success(`Successfully added ${successList.length} project${successList.length > 1 ? "s" : ""} to group ${selectedGroupName}`)

    emits("modal:new-project", successList as SelectOption[])
    hideModal()
  }
}

watch(
  () => isShown.value,
  async (shown) => {
    if (shown) {
      emits("modal:open")
      model.value = {
        targetGroupId: null,
        projectIdList: [],
      }

      await Promise.all([
        fetchLabGroups(),
        handleFetchProjectList(),
      ])
    }
    else {
      emits("modal:close")
    }
  },
)
</script>

<style scoped lang="sass">
:deep(.n-base-selection)
  --n-height: 40px!important
  --n-color: #F7F8F9!important
  border-radius: 8px

:deep(.n-transfer)
  min-height: 320px

  .n-transfer-list
    min-height: 320px
    width: 280px

    &__header
      padding: 8px 12px

    &-item
      padding: 6px 12px
</style>
