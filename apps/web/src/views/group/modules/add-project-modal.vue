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
    title="Add project"
    :bordered="false"
    size="huge"
    class="w-160"
    :mask-closable="false"
    @update:show="handleSetShow"
  >
    <n-form ref="formRef" :model="model" :rules="rules" size="large" class="mb-5">
      <n-form-item label="Select project" path="projectIdList">
        <n-select
          v-model:value="model.projectIdList"
          :options="projectList"
          placeholder="Select at least one project"
          :render-tag="renderProjectTag"
          required
          remote
          multiple
          :consistent-menu-width="false"
          @update:value="handleProjectValueChange"
        />
      </n-form-item>
    </n-form>
    <div class="flex items-center justify-end">
      <n-button size="medium" class="mr-4" :disabled="loading" @click="handleCancel">
        Cancel
      </n-button>
      <n-button
        size="medium"
        type="primary"
        :disabled="loading"
        :loading="loading"
        @click="handleConfirm"
      >
        Confirm
      </n-button>
    </div>
  </n-modal>
</template>

<script setup lang="ts">
import type { ProjectType } from "@/enum"
import type { CascaderOption, SelectOption, SelectProps, SelectRenderTag } from "naive-ui"
import { useFormRules, useLoading, useNaiveForm, useShowModal } from "@/composables"
import { ProjectRole } from "@/enum"
import { addGroupsProjects } from "@/service/api/groups"
import { fetchProjectList } from "@/service/api/projects"
import GroupProjectTag from "@/views/labs/modules/group/group-project-tag.vue"
import { useClosableMessage } from "@airalogy/composables"
import AddCircleOutline from "~icons/ion/add-circle-outline"
import { type ButtonProps, NButton } from "naive-ui/es/button"

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
  trigger: "Add project",
  buttonProps: () => ({}),
  compact: true,
  labInfo: null,
  groupInfo: null,
})

const emits = defineEmits<IEmits>()

interface FormModel {
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
  projectIdList: [defaultRequiredRule],
}
const options = ref<CascaderOption[]>([])

const model = ref<FormModel>({
  projectIdList: [],
})
const { loading, startLoading, endLoading } = useLoading()
const projectList = ref<SelectOption[]>([])

function handleCancel() {
  hideModal()
}

function handleSetShow(val: boolean) {
  setModalStatus(val)
}

async function handleFetchProjectList(labId: string) {
  if (!labId) {
    return
  }

  const result = await fetchProjectList({ labId, page: 1, pageSize: 999 })
  if (result) {
    projectList.value = result.projects.map(
      ({ name, uid, id }): SelectOption => ({
        label: name || uid,
        value: id,
        role: ProjectRole.EXPLORER,
      }),
    )
  }
}

// const roleRef = ref<1 | 2>(2)
type ProjectOption = SelectOption & { role: ProjectRole, type: ProjectType, value: string }
const selectedProjects = ref<{ project_id: string, role: ProjectRole }[]>([])
const renderProjectTag: SelectRenderTag = ({ option, handleClose }) => {
  const { label, type, value } = option as ProjectOption
  return h(GroupProjectTag, {
    "name": label as string,
    "id": String(value),
    "topRole": ProjectRole.COLLABORATOR,
    "role": ProjectRole.EXPLORER,
    type,
    "onTag:close": () => {
      handleClose()
    },
    "onTag:select": () => {
      handleClose()
    },
    "onSelect:role": (payload: { role: Api.Project.ProjectRole, id: string }) => {
      const { role, id } = payload

      const target = selectedProjects.value.find(({ project_id }) => project_id === id)

      if (target) {
        target.role = role
      }
    },
  })
}
const handleProjectValueChange: SelectProps["onUpdate:value"] = (
  _,
  option: ProjectOption[],
) => {
  selectedProjects.value = option.map(({ value, role }) => ({ project_id: value, role }))
}

async function handleConfirm() {
  await validate()

  const groupId = props.id
  if (!groupId)
    return

  startLoading()

  const { projectIdList } = model.value

  const response = await Promise.allSettled(
    selectedProjects.value.map((project) => {
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
        return projectList.value.find(it => it.value === projectIdList[idx])
      }

      if (error) {
        message.error(error.message)
      }

      return null
    })
    .filter((it): it is SelectOption => Boolean(it))

  if (successList.length > 0) {
    message.success(`Successfully add project ${successList.map(({ label }) => label).join(",")}`)

    emits("modal:new-project", successList)
    hideModal()
  }
  else {
    //
  }
}

watch(
  () => isShown.value,
  async (shown) => {
    if (shown) {
      emits("modal:open")
      if (props.labInfo?.id) {
        await handleFetchProjectList(props.labInfo?.id)
      }
    }
    else {
      model.value = {
        projectIdList: [],
      }
      options.value = []
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
</style>
