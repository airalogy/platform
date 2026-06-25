<template>
  <div>
    <n-button
      :bordered="false"
      class="scale-80"
      :theme-overrides="{
        colorHover: 'rgba(36,82,148,0.1)',
        colorPressed: 'rgba(36,82,148,0.2)',
        colorFocus: 'rgba(36,82,148,0.1)',
        textColor: '#A1A4AF',
        textColorHover: '#6A6C73',
        textColorPressed: '#6A6C73',
        textColorFocus: '#6A6C73',
        rippleColor: '#245294',
      }"
      v-bind="props.buttonProps"
      @click.stop="showModal"
    >
      <template #icon>
        <edit-icon />
      </template>
    </n-button>
    <n-modal
      :show="isShown"
      preset="card"
      size="huge"
      class="w-160"
      header-class="border-b !py-5 !px-6"
      content-class="!px-6 !py-6"
      :mask-closable="false"
      @update:show="setModalStatus"
    >
      <template #header>
        Edit protocol
      </template>
      <div class="max-h-80vh w-full overflow-x-visible overflow-y-auto">
        <n-form ref="formRef" :model="model" :rules="rules" size="large">
          <n-form-item label="Upload logo" path="logo">
            <form-upload-file :upload-props="{ accept: 'image/*' }" />
          </n-form-item>
          <n-form-item label="Research name" path="name">
            <n-input
              v-model:value="model.name"
              type="text"
              :maxlength="30"
              required
              placeholder="Enter protocol name"
            />
          </n-form-item>
          <n-form-item label="Description" path="description">
            <n-input
              v-model:value="model.description"
              type="textarea"
              :maxlength="128"
              :autosize="true"
              :max-rows="10"
              show-count
              placeholder="Describe the research"
            />
          </n-form-item>
          <!-- <n-form-item label="Select type" path="type">
            <n-radio-group v-model:value="model.type">
              <n-radio
                v-for="typeItem in researchTypeList"
                :key="typeItem.value"
                :value="typeItem.value"
                size="small"
                class="capitalize first:mr-4"
              >
                {{ typeItem.label }}
              </n-radio>
            </n-radio-group>
          </n-form-item> -->
        </n-form>
        <div class="flex items-center justify-end">
          <n-button size="medium" class="mr-4" :disabled="submitting" @click="handleCancel">
            Cancel
          </n-button>
          <n-button
            size="medium"
            type="primary"
            :disabled="loading"
            :loading="submitting"
            @click="handleConfirm"
          >
            Confirm
          </n-button>
        </div>
      </div>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import type { ProtocolModels } from "@airalogy/shared/types"
import type { ButtonProps } from "naive-ui/es/button"
import type { SelectOption } from "naive-ui/es/select"

import { useBoolean, useFormRules, useLoading, useNaiveForm, useShowModal } from "@/composables"
import { putProtocolInfo } from "@/service/api/project-protocols"
import { useClosableMessage } from "@airalogy/composables"

interface IProps {
  buttonType?: "text" | "ghost"
  showIcon?: boolean
  buttonProps?: ButtonProps & { class?: string }
  item?: ProtocolModels.ProjectProtocolInfo | null
}
const props = withDefaults(defineProps<IProps>(), {
  buttonType: "ghost",
  showIcon: false,
  buttonProps: () => ({}),
  item: null,
})

const emits = defineEmits<IEmits>()
interface FormModel {
  name: string | null
  description: string | null
  type: "private" | "public"
  members: string | null
}
const { isShown, showModal, hideModal, setModalStatus } = useShowModal()
const { bool: isShowMenu, setFalse: hideMenu, setTrue: showMenu } = useBoolean()
const { defaultRequiredRule } = useFormRules()
const { formRef, validate } = useNaiveForm()

// const researchTypeList: { label: string, value: FormModel["type"] }[] = [
//   { label: "private", value: "private" },
//   { label: "public", value: "public" },
// ]

interface IEmits {
  (e: "modal:edit-research", val: Api.Project.MyProjectInfo): void
  (e: "modal:close"): void
  (e: "modal:open"): void
}

const rules: Partial<Record<keyof FormModel, App.Global.FormRule[]>> = {
  name: [defaultRequiredRule],
  type: [defaultRequiredRule],
}

const memberOptions = ref<SelectOption[]>([])
const { loading, startLoading, endLoading } = useLoading()

const model = ref<FormModel>({
  name: props.item?.name || null,
  description: (props.item as any)?.description || null,
  type: "private",
  members: null,
})

function handleClearOption() {
  hideMenu()
  setTimeout(() => (memberOptions.value = []), 200)
}

function restoreModel() {
  model.value = {
    name: props.item?.name || null,
    description: (props.item as any)?.description || null,
    type: "private",
    members: null,
  }

  memberOptions.value = []

  formRef.value?.restoreValidation()
}

const { loading: submitting, startLoading: startSubmit, endLoading: endSubmit } = useLoading()
async function handleCancel() {
  hideModal()

  await nextTick(() => {
    restoreModel()
  })
}

const message = useClosableMessage()
async function handleConfirm() {
  await validate()
  const protocolId = props.item?.id

  if (!protocolId) {
    message.error("research id is null")
    return
  }

  startSubmit()
  const { description, members, name, type } = model.value
  try {
    const { data, error } = await putProtocolInfo(protocolId, {
      description: description || undefined,
      name: name || undefined,
    })
    if (error) {
      // NOPE
    }
    else {
      message.success(`Successfully updated research ${name}`)

      emits("modal:edit-research", data)
      hideModal()
      await nextTick(() => {
        restoreModel()
      })
    }
  }
  catch (e) {
    message.error((e as Error).message)
  }
  finally {
    endSubmit()
  }
}

watch(
  () => isShown.value,
  (shown) => {
    if (shown) {
      emits("modal:open")
    }
    else {
      emits("modal:close")
    }
  },
)
</script>

<style scoped lang="sass">
:deep(.n-base-selection-tags)
  justify-content: flex-start!important
  align-items: start!important
  flex-direction: column!important
</style>
