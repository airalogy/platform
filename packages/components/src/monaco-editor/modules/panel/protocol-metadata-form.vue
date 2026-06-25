<template>
  <n-collapse v-model:expanded-names="expandedNames" :theme-overrides="{ itemMargin: '8px 0 0 0', titlePadding: '8px 0 0 0' }" display-directive="show">
    <!-- Basic Info Section -->
    <n-collapse-item title="Basic Information" name="basic-info" default-expanded>
      <template #header-extra>
        <n-tooltip trigger="hover">
          <template #trigger>
            <n-icon size="16" class="cursor-help text-gray-400">
              <icon-tabler-info-circle />
            </n-icon>
          </template>
          Basic information about the protocol, including identifiers and version
        </n-tooltip>
      </template>

      <n-grid :cols="2" item-responsive>
        <n-form-item-gi span="2 800:1" v-bind="props.itemProps" required label="Protocol ID" :path="getPath('id')">
          <n-tooltip trigger="hover">
            <template #trigger>
              <div class="w-full flex items-center">
                <n-input v-model:value="formData.id" :size="props.size" placeholder="e.g. airalogy_protocol" :disabled="props.disableDefault && !!props.protocolInfo" />
                <n-icon size="16" class="ml-auto cursor-help text-gray-400">
                  <icon-tabler-info-circle />
                </n-icon>
              </div>
            </template>
            Unique identifier for this protocol in the Airalogy Protocol ID space. Should be a UUID or a custom snake_case string.
          </n-tooltip>
        <!-- <common-id-input v-model="formData.id" type="protocol" :size="props.size" placeholder="e.g. airalogy_protocol" /> -->
        </n-form-item-gi>

        <n-form-item-gi span="2 800:1" v-bind="props.itemProps" required label="Version" :path="getPath('version')">
          <common-version-input
            v-model="formData.version"
            :size="props.size"
            placeholder="e.g. 0.0.1"
            tooltip="Protocol version in x.y.z format. Default is 0.0.1."
            trigger="hover"
            placement="top"
          >
            <n-icon size="16" class="ml-auto cursor-help text-gray-400">
              <icon-tabler-info-circle />
            </n-icon>
          </common-version-input>
        </n-form-item-gi>

        <n-form-item-gi v-if="!skipGlobalId" :span="2" v-bind="props.itemProps" label="Global ID (Auto-generated)" :path="getPath('airalogy_protocol_id')">
          <n-tooltip trigger="hover">
            <template #trigger>
              <div class="w-full flex items-center gap-2 border border-gray-300 rounded-md bg-gray-50 px-3 py-2">
                <n-icon size="18" class="text-gray-400">
                  <icon-ion-lock-closed-outline />
                </n-icon>
                <span class="flex-1 truncate text-sm text-gray-600 font-mono">
                  {{ formData.airalogy_protocol_id || 'Auto-generated from Protocol ID and Version' }}
                </span>
                <n-icon size="16" class="flex-shrink-0 cursor-help text-gray-400">
                  <icon-tabler-info-circle />
                </n-icon>
              </div>
            </template>
            Full protocol ID in the format: airalogy.id.lab.[lab_id].project.[project_id].protocol.[protocol_id].v.[version]. This field is auto-generated based on Protocol ID and Version.
          </n-tooltip>
        </n-form-item-gi>
      </n-grid>
      <n-form-item v-bind="props.itemProps" required label="Name" :path="getPath('name')">
        <n-tooltip trigger="hover">
          <template #trigger>
            <div class="w-full flex items-center">
              <n-input v-model:value="formData.name" :size="props.size" placeholder="e.g. Protocol Name" />
              <n-icon size="16" class="ml-1 cursor-help text-gray-400">
                <icon-tabler-info-circle />
              </n-icon>
            </div>
          </template>
          Descriptive name for this protocol. If not specified, it will be auto-generated from the markdown title.
        </n-tooltip>
      </n-form-item>

      <n-form-item v-bind="props.itemProps" label="License" :path="getPath('license')">
        <n-tooltip trigger="hover">
          <template #trigger>
            <div class="w-full flex items-center">
              <n-select
                v-model:value="formData.license"
                :options="licenseOptions"
                filterable
                tag
                :size="props.size"
                placeholder="Select or enter a license"
              />
              <n-icon size="16" class="ml-1 cursor-help text-gray-400">
                <icon-tabler-info-circle />
              </n-icon>
            </div>
          </template>
          Optional license for the protocol. Helps users understand usage restrictions.
        </n-tooltip>
      </n-form-item>
    </n-collapse-item>

    <!-- Description Section -->
    <n-collapse-item title="Description" name="description">
      <template #header-extra>
        <n-tooltip trigger="hover">
          <template #trigger>
            <n-icon size="16" class="cursor-help text-gray-400">
              <icon-tabler-info-circle />
            </n-icon>
          </template>
          Provide a clear description of what this protocol does and its key features
        </n-tooltip>
      </template>

      <n-form-item v-bind="props.itemProps" path="description">
        <n-tooltip trigger="focus" placement="top-start">
          <template #trigger>
            <n-input
              v-model:value="formData.description"
              type="textarea"
              placeholder="Describe this protocol"
              :autosize="{ minRows: 3, maxRows: 6 }"
              maxlength="200"
              show-count
            />
          </template>
          Provide a clear description of what this protocol does and its key features
        </n-tooltip>
      </n-form-item>
    </n-collapse-item>

    <!-- Authors Section -->
    <n-collapse-item title="Authors" name="authors">
      <template #header-extra>
        <n-tooltip trigger="hover">
          <template #trigger>
            <n-icon size="16" class="cursor-help text-gray-400">
              <icon-tabler-info-circle />
            </n-icon>
          </template>
          List of protocol authors with their contact information
        </n-tooltip>
      </template>

      <div v-for="(author, index) in formData.authors" :key="`author-${index}`" class="mb-4 border border-gray-200 rounded-md">
        <div class="mb-2 w-full flex items-center justify-between">
          <div class="px-4 text-sm font-medium">
            Author #{{ index + 1 }}
          </div>
          <n-button :size="props.size" type="error" quaternary @click="removeAuthor(index)">
            <template #icon>
              <n-icon :size="16">
                <icon-ion-trash-outline />
              </n-icon>
            </template>
          </n-button>
        </div>

        <n-form-item v-bind="props.itemProps" :path="getPath(`authors[${index}].name`)" :rule-path="getPath(`authors.name`)" label="Name">
          <n-input v-model:value="author.name" :size="props.size" placeholder="Author name" class="mr-4" />
        </n-form-item>

        <n-form-item v-bind="props.itemProps" :path="getPath(`authors[${index}].email`)" :rule-path="getPath(`authors.email`)" label="Email">
          <n-input v-model:value="author.email" :size="props.size" placeholder="Author email" class="mr-4" />
        </n-form-item>

        <n-form-item v-bind="props.itemProps" :path="getPath(`authors[${index}].airalogy_user_id`)" :rule-path="getPath(`authors.airalogy_user_id`)" label="User ID">
          <n-input v-model:value="author.airalogy_user_id" :size="props.size" placeholder="e.g. airalogy.id.user.alice" class="mr-4" />
        </n-form-item>
      </div>

      <n-button size="small" type="primary" class="mb-4" @click="addAuthor">
        <template #icon>
          <n-icon :size="16">
            <icon-ion-add />
          </n-icon>
        </template>
        Add Author
      </n-button>
    </n-collapse-item>

    <!-- Maintainers Section -->
    <n-collapse-item title="Maintainers" name="maintainers">
      <template #header-extra>
        <n-tooltip trigger="hover">
          <template #trigger>
            <n-icon size="16" class="cursor-help text-gray-400">
              <icon-tabler-info-circle />
            </n-icon>
          </template>
          List of protocol maintainers responsible for updates and maintenance
        </n-tooltip>
      </template>

      <div v-for="(maintainer, index) in formData.maintainers" :key="`maintainer-${index}`" class="mb-4 border border-gray-200 rounded-md">
        <div class="mb-2 w-full flex items-center justify-between">
          <div class="px-4 text-sm font-medium">
            Maintainer #{{ index + 1 }}
          </div>
          <n-button :size="props.size" type="error" quaternary @click="removeMaintainer(index)">
            <template #icon>
              <n-icon :size="16">
                <icon-ion-trash-outline />
              </n-icon>
            </template>
          </n-button>
        </div>

        <n-form-item v-bind="props.itemProps" :path="getPath(`maintainers[${index}].name`)" :rule-path="getPath(`maintainers.name`)" label="Name">
          <n-input v-model:value="maintainer.name" :size="props.size" placeholder="Maintainer name" class="mr-4" />
        </n-form-item>

        <n-form-item v-bind="props.itemProps" :path="getPath(`maintainers[${index}].email`)" :rule-path="getPath(`maintainers.email`)" label="Email">
          <n-input v-model:value="maintainer.email" :size="props.size" placeholder="Maintainer email" class="mr-4" />
        </n-form-item>

        <n-form-item v-bind="props.itemProps" :path="getPath(`maintainers[${index}].airalogy_user_id`)" :rule-path="getPath(`maintainers.airalogy_user_id`)" label="User ID">
          <n-input v-model:value="maintainer.airalogy_user_id" :size="props.size" placeholder="e.g. airalogy.id.user.alice" class="mr-4" />
        </n-form-item>
      </div>

      <n-button size="small" type="primary" class="mb-4" @click="addMaintainer">
        <template #icon>
          <n-icon :size="16">
            <icon-ion-add />
          </n-icon>
        </template>
        Add Maintainer
      </n-button>
    </n-collapse-item>

    <!-- Disciplines Section -->
    <n-collapse-item title="Disciplines" name="disciplines" required>
      <template #header-extra>
        <n-tooltip trigger="hover">
          <template #trigger>
            <n-icon size="16" class="cursor-help text-gray-400">
              <icon-tabler-info-circle />
            </n-icon>
          </template>
          Scientific disciplines related to this protocol. At least one discipline is required. The first discipline is considered the primary one.
        </n-tooltip>
      </template>

      <n-form-item v-bind="props.itemProps" :path="getPath('disciplines')" :show-label="false" required>
        <n-dynamic-tags
          v-model:value="formData.disciplines"
          :max="10"
          :input-props="{ placeholder: 'e.g. biology' }"
        />
      </n-form-item>
    </n-collapse-item>

    <!-- Keywords Section -->
    <n-collapse-item title="Keywords" name="keywords">
      <template #header-extra>
        <n-tooltip trigger="hover">
          <template #trigger>
            <n-icon size="16" class="cursor-help text-gray-400">
              <icon-tabler-info-circle />
            </n-icon>
          </template>
          Optional keywords to help with protocol discovery and categorization
        </n-tooltip>
      </template>

      <n-form-item v-bind="props.itemProps" label="Keywords" path="keywords" :show-label="false">
        <n-dynamic-tags
          v-model:value="formData.keywords"
          :max="20"
          :input-props="{
            placeholder: 'e.g. cell viability',
          }"
        />
      </n-form-item>
    </n-collapse-item>

    <!-- Raw TOML Preview -->
    <n-collapse-item title="Preview TOML" name="toml-preview">
      <template #header-extra>
        <div class="mt-2 flex items-center justify-between">
          <n-button size="small" quaternary :theme-overrides="{ heightSmall: '21px' }" @click.stop="handleEdit">
            <template #icon>
              <n-icon :size="16">
                <icon-ion-pencil-outline />
              </n-icon>
            </template>
            {{ isEditing ? "Save" : "Edit" }}
          </n-button>
          <div v-if="diffContent.length > 0" class="flex gap-2 text-sm">
            <span class="text-green-600">
              +{{ diffContent.filter(p => p.added).reduce((acc, p) => acc + (p.count || 0), 0) }}
            </span>
            <span class="text-red-500">
              -{{ diffContent.filter(p => p.removed).reduce((acc, p) => acc + (p.count || 0), 0) }}
            </span>
          </div>
        </div>
      </template>
      <template v-if="isEditing">
        <n-input v-model:value="tomlRef" :size="props.size" type="textarea" autosize class="font-mono" />
      </template>
      <template v-else>
        <div v-if="parseError" class="whitespace-pre-wrap rounded-md bg-red-50 p-2 text-xs text-red-500 font-mono">
          {{ parseError }}
        </div>
        <div v-if="diffContent.length > 0" class="max-h-50vh overflow-auto border rounded-md py-2">
          <div v-for="(part, index) in diffContent" :key="index">
            <pre
              v-if="part.value.trim()"
              class="diff-wrapper"
              :class="{
                'diff-added': part.added,
                'diff-removed': part.removed,
                'diff-unchanged': !part.added && !part.removed,
              }"
            ><code>{{ part.value }}</code></pre>
          </div>
        </div>
        <div v-else class="whitespace-pre-wrap rounded-md bg-gray-100 p-2 font-mono">
          {{ generatedToml }}
        </div>
      </template>
    </n-collapse-item>
  </n-collapse>
</template>

<script setup lang="ts">
import type { ProtocolInfo, ProtocolMetaData } from "@airalogy/shared/types/models/protocol"
import type { FormInst, FormItemProps } from "naive-ui"
import CommonVersionInput from "@airalogy/components/common/common-version-input.vue"

import { useBoolean, useClosableMessage, useTomlEditor } from "@airalogy/composables"
import { licenseOptions } from "@airalogy/shared/constants/licenses"
import IconIonAdd from "~icons/ion/add"
import IconIonLockClosedOutline from "~icons/ion/lock-closed-outline"
import IconIonPencilOutline from "~icons/ion/pencil-outline"
import IconIonTrashOutline from "~icons/ion/trash-outline"
import { parse } from "smol-toml"

interface IProps {
  modelValue: ProtocolMetaData
  parseError?: string
  originalToml: string
  aimdContent?: string
  itemProps?: FormItemProps
  size?: "small" | "medium" | "large"
  pathPrefix?: string
  checkLoading?: boolean
  checkId?: boolean
  labUid?: string | null
  projectUid?: string | null
  protocolInfo?: ProtocolInfo | null
  skipUpload?: boolean
  disableDefault?: boolean
  skipGlobalId?: boolean
}

const props = withDefaults(defineProps<IProps>(), {
  pathPrefix: "",
  parseError: "",
  originalToml: "",
  aimdContent: "",
  itemProps: () => ({
    labelStyle: "font-size: 14px",
    labelPlacement: "left",
    labelWidth: "120px",
  }),
  checkId: true,
  labUid: null,
  projectUid: null,
  protocolInfo: null,
  skipUpload: false,
  disableDefault: true,
  skipGlobalId: false,
})

const emit = defineEmits<{
  (e: "update:modelValue", value: ProtocolMetaData): void
  (e: "update:toml", toml: string): void
  (e: "save"): void
  (e: "reset"): void
  (e: "openInEditor", filename: string): void
}>()

// Use a reactive copy of the form data
const formData = reactive<ProtocolMetaData>({ ...props.modelValue })

const expandedNames = ref<string[]>(["basic-info", "authors", "maintainers", "disciplines", "keywords", "toml-preview"])
// Create ref for original TOML
const originalTomlRef = ref(props.originalToml)
const tomlRef = ref(props.originalToml)

// Watch for changes to props.originalToml
watch(() => props.originalToml, (newValue) => {
  originalTomlRef.value = newValue
})

// Use the TOML editor composable
const {
  generatedToml,
  diffContent,
} = useTomlEditor(formData, originalTomlRef, computed(() => props.aimdContent))

function getPath(path: string) {
  const { pathPrefix } = props
  return pathPrefix ? `${pathPrefix}.${path}` : path
}

// Helper functions for form manipulation
function addAuthor() {
  formData.authors.push({
    name: "",
    email: "",
    airalogy_user_id: "",
  })
  updateModelValue()
}

function removeAuthor(index: number) {
  formData.authors.splice(index, 1)
  updateModelValue()
}

function addMaintainer() {
  formData.maintainers.push({
    name: "",
    email: "",
    airalogy_user_id: "",
  })
  updateModelValue()
}

function removeMaintainer(index: number) {
  formData.maintainers.splice(index, 1)
  updateModelValue()
}

// Auto-generate protocol ID when id or version changes
watch([() => formData.id, () => formData.version, () => props.labUid, () => props.projectUid], ([id, version, labUid, projectUid]) => {
  if (id && version && labUid && projectUid) {
    formData.airalogy_protocol_id = `airalogy.id.lab.${labUid}.project.${projectUid}.protocol.${id}.v.${version}`
  }
  else {
    formData.airalogy_protocol_id = ""
  }

  updateModelValue()
}, { immediate: true })

// Watch for external changes to the model value
watch(() => props.modelValue, (newValue) => {
  Object.assign(formData, newValue)
}, { deep: true })

// Update model value when form data changes
function updateModelValue() {
  emit("update:modelValue", formData)
}

// Watch all form data changes and emit updates
watch(formData, () => {
  updateModelValue()
}, { deep: true })

const { bool: isEditing, toggle: toggleEditing } = useBoolean(false)

const message = useClosableMessage()
async function handleEdit() {
  if (!expandedNames.value.includes("toml-preview")) {
    expandedNames.value.push("toml-preview")
    await nextTick()
  }

  if (isEditing.value) {
    try {
      // Parse the edited TOML back into an object and update formData
      const parsedData = parse(tomlRef.value) as any

      // Extract protocol data from parsed TOML
      const protocol = parsedData.airalogy_protocol || {}

      // Update the formData with parsed values
      Object.assign(formData, {
        id: protocol.id || formData.id,
        version: protocol.version || formData.version,
        // airalogy_protocol_id: protocol.airalogy_protocol_id || formData.airalogy_protocol_id,
        name: protocol.name || formData.name,
        license: protocol.license || formData.license,
        authors: Array.isArray(protocol.authors) ? protocol.authors : formData.authors,
        maintainers: Array.isArray(protocol.maintainers) ? protocol.maintainers : formData.maintainers,
        disciplines: Array.isArray(protocol.disciplines) ? protocol.disciplines : formData.disciplines,
        keywords: Array.isArray(protocol.keywords) ? protocol.keywords : formData.keywords,
      })

      emit("update:modelValue", formData)
    }
    catch (error) {
      message.error(`Failed to parse TOML: ${(error as Error).message}`)
      return
    }
  }
  else {
    tomlRef.value = generatedToml.value || props.originalToml
  }

  await nextTick()
  toggleEditing()
}

const formRef = inject<Ref<FormInst | null>>("protocol-form-ref", ref(null))

async function handleCheckProtocolIdDuplicate() {
  if (!formRef?.value) {
    return
  }

  formRef.value.validate(() => {}, (rule) => {
    return rule?.key === "check-airalogy-protocol-id"
  })
}

watch(generatedToml, (newVal) => {
  emit("update:toml", newVal)
}, { immediate: true, flush: "sync" })
</script>

<style scoped lang="sass">
// Diff highlighting styles
pre
  &.diff-wrapper
    @apply whitespace-pre-wrap pl-10 relative
  &.diff-added
    @apply bg-green-50 text-green-800
    &::before
      content: "+"
      @apply text-green-600 absolute left-5 top-0 -translate-x-1/2

  &.diff-removed
    @apply bg-red-50 text-red-800
    &::before
      content: "-"
      @apply text-red-600 absolute left-5 top-0 -translate-x-1/2

  &.diff-unchanged
    @apply bg-white
</style>
