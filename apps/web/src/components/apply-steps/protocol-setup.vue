<template>
  <n-form
    v-if="selectedOption === 'existing'"
    ref="formRef"
    :model="model"
    :rules="rules"
    size="medium"
    class="w-full space-y-4"
  >
    <step-header
      :step="1"
      :title="formText.selectAnotherProtocol"
      :has-selected="!!selectedNode"
      :on-reset="handleResetProject"
      path="projectId"
    >
      <template #selected>
        <selection-display :items="selectionDisplayList" class="p-3" />
      </template>

      <template #content>
        <project-selector
          class="p-3"
          :protocol-info="props.protocolInfo"
          @update:lab="handleLabUpdate"
          @update:project="handleProjectUpdate"
          @update:node="handleNodeUpdate"
        />
      </template>
    </step-header>

    <step-header
      :step="2"
      :title="formText.applyToProject"
    >
      <n-form-item :show-label="false" path="projectId" required :show-feedback="false">
        <project-selector
          class="p-3"
          :protocol-info="props.protocolInfo"
          target="project"
          :default-project="defaultProject"
          :default-lab="defaultLab"
          :disable-default="props.disableDefault"
          @update:lab="handleTargetLabUpdate"
          @update:project="handleTargetProjectUpdate"
        />
      </n-form-item>
    </step-header>
    <step-header
      v-if="props.mode === 'fork'"
      :step="3"
      :title="protocolDetailsTitle"
      :has-selected="false"
      :disable-collapse="true"
    >
      <template #content>
        <div class="p-3">
          <protocol-details
            v-if="selectedNode"
            :lab-uid="selectedLab?.uid"
            :project-uid="selectedProject?.uid"
          />
          <n-empty v-else :description="formText.noProtocolSelected" />
        </div>
      </template>
    </step-header>
    <step-header
      v-else
      :step="3"
      :title="formText.newProtocolDetails"
      :on-reset="handleResetProject"
    >
      <div class="p-4">
        <n-form-item :label="formText.protocolDisplayNameLabel" path="protocolName" class="w-full">
          <n-input
            v-model:value="model.protocolName"
            type="text"
            :maxlength="30"
            required
            :placeholder="formText.protocolDisplayNamePlaceholder"
            :allow-input="(value: string) => !value.includes('.')"
            @update:value="handleUpdateDisplayName"
          />
        </n-form-item>
        <n-form-item :label="formText.protocolIdLabel" path="protocolUid" class="w-full">
          <common-id-input
            v-model="model.protocolUid"
            type="protocol"
            :lab-uid="targetLab?.uid || model.labUid || undefined"
            :project-uid="targetProject?.uid || model.projectUid || undefined"
            :show-prefix="isTargetProjectSelected"
            :disabled="!isTargetProjectSelected"
            :check-loading="checkLoading"
            @update:value="handleUpdateName"
            @check="handleValidateProtocolName"
          />
        </n-form-item>
      </div>
    </step-header>
  </n-form>

  <protocol-upload-form
    v-else-if="selectedOption === 'upload-zip'"
    v-model:model="uploadModel"
    :protocol-data="protocolData"
    :upload-type="selectedOption"
    :protocol-info="props.protocolInfo"
    :project-info="props.projectInfo"
    :lab-uid="selectedLab?.uid || uploadModel.labUid"
    :project-uid="selectedProject?.uid || uploadModel.projectUid"
    :check-id="!props.protocolInfo"
    :skip-upload="props.skipUpload"
    :disable-default="props.disableDefault"
    @update:form-ref="handleFormRefUpdate"
    @loaded:content="handleContentLoaded"
    @remove="handleRemoveContent"
  />
</template>

<script setup lang="ts">
import type { UploadContent } from "@airalogy/components/src/monaco-editor/types/upload"
import type { ProtocolModels } from "@airalogy/shared/types/models"
import type { Lab, Project } from "./project-selector.vue"
import type { SelectionItem } from "./selection-display.vue"
import { createDisplayNameValidator, createUidValidator, useFormRules, useLoading } from "@/composables"
import { $t } from "@/locales"
import { postCheckProtocolIdDuplicate } from "@/service/api/protocol"
import { handleContentLoaded as handleProtocolContentLoaded } from "@airalogy/components/src/monaco-editor/utils/protocolContentLoader"
import { formatPydanticError } from "@airalogy/shared/utils/errorFormatter.js"
import { type FormInst, useMessage } from "naive-ui"
import { convertDisplayname } from "../../utils/convertDisplayname"
import { useApplyProtocol } from "./composables/useApplyProtocolState"
import ProjectSelector from "./project-selector.vue"
import ProtocolDetails from "./protocol-details.vue"
import SelectionDisplay from "./selection-display.vue"
import StepHeader from "./step-header.vue"

interface Props {
  headers?: Headers
  mode: "fork" | "reuse"
  protocolInfo?: ProtocolModels.ProjectProtocolInfo | null
  projectInfo?: Api.Project.MyProjectInfo | null
  skipUpload?: boolean
  disableDefault?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  protocolInfo: undefined,
  mode: "reuse",
  projectInfo: undefined,
  skipUpload: false,
  disableDefault: true,
})

const { selectedOption, model, uploadModel, protocolData, packageContent } = useApplyProtocol()
const { defaultRequiredRule } = useFormRules()

const formRef = inject<Ref<FormInst | null>>("apply-protocol-form", ref(null))
const selectedNode = ref<ProtocolModels.ProjectProtocolInfo | null>(null)
const selectedLab = ref<Lab | null>(null)
const selectedProject = ref<Project | null>(null)

const defaultProject = computed(() => props.protocolInfo?.project || props.projectInfo)
const defaultLab = computed(() => {
  const { protocolInfo, projectInfo } = props
  if (protocolInfo?.lab) {
    return protocolInfo.lab
  }
  if (projectInfo) {
    const { lab_uid, lab_name, lab_id } = projectInfo
    if (lab_uid) {
      return {
        uid: lab_uid,
        name: lab_name,
        id: lab_id,
      }
    }
  }
  return null
})
const formText = computed(() => ({
  selectAnotherProtocol: $t("page.protocol.apply.setupForm.selectAnotherProtocol"),
  applyToProject: $t("page.protocol.apply.setupForm.applyToProject"),
  protocolDetailsFork: $t("page.protocol.apply.setupForm.protocolDetailsFork"),
  protocolDetailsReuse: $t("page.protocol.apply.setupForm.protocolDetailsReuse"),
  noProtocolSelected: $t("page.protocol.apply.setupForm.noProtocolSelected"),
  newProtocolDetails: $t("page.protocol.apply.setupForm.newProtocolDetails"),
  protocolDisplayNameLabel: $t("page.protocol.apply.setupForm.protocolDisplayNameLabel"),
  protocolDisplayNamePlaceholder: $t("page.protocol.apply.setupForm.protocolDisplayNamePlaceholder"),
  protocolIdLabel: $t("page.protocol.apply.setupForm.protocolIdLabel"),
  protocolIdValid: $t("page.protocol.apply.setupForm.protocolIdValid"),
}))

const protocolDetailsTitle = computed(() => {
  return props.mode === "fork"
    ? formText.value.protocolDetailsFork
    : formText.value.protocolDetailsReuse
})

const targetLab = ref<Lab | null>(null)
const targetProject = ref<Project | null>(null)
const isTargetProjectSelected = computed(() => {
  return Boolean((targetLab.value?.uid || model.value.labUid) && (targetProject.value?.uid || model.value.projectUid))
})

const rules = computed(() => ({
  projectId: [defaultRequiredRule],
  protocolId: [defaultRequiredRule],
  protocolUid: createUidValidator({
    fieldName: formText.value.protocolIdLabel,
    checkDuplicate: postCheckProtocolIdDuplicate,
    duplicateCheckArgs: () => ({
      labUid: targetLab.value?.uid || model.value.labUid,
      projectUid: targetProject.value?.uid || model.value.projectUid,
    }),
    payloadKey: "uid",
  }),
  protocolName: createDisplayNameValidator(formText.value.protocolDisplayNameLabel),
}))

const selectionDisplayList = computed<SelectionItem[]>(() => {
  const display: SelectionItem[] = []

  if (selectedLab.value) {
    display.push({
      label: selectedLab.value.name,
      value: selectedLab.value.uid,
      id: selectedLab.value.id,
      showValue: true,
      type: "lab",
    })
  }

  if (selectedProject.value) {
    display.push({
      label: selectedProject.value.name,
      value: selectedProject.value.uid,
      id: selectedProject.value.id,
      showValue: true,
      type: "project",
    })
  }

  if (selectedNode.value) {
    display.push({
      label: selectedNode.value.name,
      value: selectedNode.value.uid,
      id: String(selectedNode.value.id),
      showValue: true,
      type: "name",
    })

    const { airalogy_id } = selectedNode.value

    // display.push({
    //   label: `v${current_node_version}`,
    //   value: `v${current_node_version}`,
    //   type: "version",
    //   showValue: false,
    // })

    // const protocolUid = `airalogy.id.lab.${lab_uid}.project.${project_uid}.unit.${uid}.ver.${current_node_version}`
    /**
     * airalogy.id.protocol.<uuid>
     * airalogy.id.record.<uuid>
     */
    display.push({
      label: airalogy_id,
      value: airalogy_id,
      id: airalogy_id,
      type: "id",
    })
  }

  return display
})

function handleFormRefUpdate(formInst: FormInst | null) {
  formRef.value = formInst
}

async function validate() {
  await formRef.value?.validate?.()
}

function handleLabUpdate(lab: Lab | null) {
  selectedLab.value = lab
}

function handleProjectUpdate(project: Project | null) {
  selectedProject.value = project
}

function handleNodeUpdate(node: ProtocolModels.ProjectProtocolInfo | null) {
  selectedNode.value = node
  if (node) {
    model.value.protocolId = node.id

    if (props.mode === "reuse") {
      model.value.protocolUid = node.uid
      model.value.version = "0.0.1"
      model.value.protocolName = node.name
    }
  }
}

function handleTargetLabUpdate(lab: Lab | null) {
  targetLab.value = lab
  model.value.labUid = lab?.uid || null
}

function handleTargetProjectUpdate(project: Project | null) {
  targetProject.value = project
  model.value.projectUid = project?.uid || null
  model.value.projectId = project?.id || null
}

function handleResetProject() {
  selectedLab.value = null
  selectedProject.value = null
  selectedNode.value = null

  model.value.protocolId = null

  if (props.mode === "reuse") {
    model.value.protocolUid = null
    model.value.protocolName = ""
  }
}

function handleContentLoaded(data: UploadContent) {
  handleProtocolContentLoaded(data, uploadModel, protocolData, packageContent)
}

function handleRemoveContent(path: string) {
  const { content } = packageContent.value || {}
  if (!content || !path) {
    return
  }
  const targetIndex = content.items.findIndex(it => it.path === path)
  if (targetIndex !== -1) {
    packageContent.value!.content.items.splice(targetIndex, 1)
    packageContent.value!.updated = true
  }
}
const shouldUpdateName = ref(true)

async function handleUpdateDisplayName(displayName: string) {
  if (model.value.protocolUid && !shouldUpdateName.value) {
    return
  }
  else if (!model.value.protocolUid) {
    shouldUpdateName.value = true
  }

  const name = await convertDisplayname(displayName)

  model.value.protocolUid = name
}

function handleUpdateName(val: string) {
  if (shouldUpdateName.value) {
    shouldUpdateName.value = false
  }
}

const { loading: checkLoading, startLoading: startCheckLoading, endLoading: endCheckLoading } = useLoading()
const message = useMessage()

async function handleValidateProtocolName() {
  const labUid = targetLab.value?.uid || model.value.labUid
  const projectUid = targetProject.value?.uid || model.value.projectUid

  if (!model.value.protocolUid || !labUid || !projectUid) {
    return
  }

  startCheckLoading()

  try {
    const { data, error } = await postCheckProtocolIdDuplicate({
      uid: model.value.protocolUid,
      labUid,
      projectUid,
    })

    if (error) {
      const data = error.response?.data as any
      if (data?.detail) {
        throw data.detail
      }
      else {
        const errorMessage = formatPydanticError(data.detail as any, {})
        throw errorMessage
      }
    }
    if (!data.valid) {
      // eslint-disable-next-line no-throw-literal
      throw { ...data, renderMessageKey: "protocol_id_duplicate" }
    }

    message.success(formText.value.protocolIdValid)
  }
  catch (e) {
    message.error((e as Error).message)
  }
  finally {
    endCheckLoading()
  }
}

watch(defaultLab, (lab) => {
  if (!lab) {
    return
  }

  targetLab.value = {
    id: lab.id,
    uid: lab.uid,
    name: lab.name,
  }
  model.value.labUid = lab.uid || null
}, { immediate: true })

watch(defaultProject, (project) => {
  if (!project) {
    return
  }

  targetProject.value = {
    id: project.id,
    uid: project.uid,
    name: project.name,
  }
  model.value.projectUid = project.uid || null
  model.value.projectId = project.id || null
}, { immediate: true })

defineExpose({
  validate,
})
</script>
