import type { ComputedRef, Ref } from "vue"
import { useFormRules, useNaiveForm } from "@/composables"
import { useClosableMessage, useLoading } from "@airalogy/composables"
import { isEqual } from "lodash-es"
import { useDialog } from "naive-ui"

export interface BaseFormModel {
  name?: string
  displayName?: string
  description?: string
  type?: Api.Lab.GroupType
  logo?: string
}

export interface SettingsFormMessages {
  noChangesTitle?: string
  noChangesDescription?: string
  updateError?: string
  updateSuccess?: string
  closeText?: string
  cancelText?: string
}

export interface SettingsFormOptions {
  messages?: SettingsFormMessages
}

export function useSettingsForm<T extends BaseFormModel>(
  initValue: ComputedRef<T>,
  onSubmit: (model: T) => Promise<{ data?: any, error?: any }>,
  onSuccess?: () => void,
  onError?: (error: any) => void,
  options?: SettingsFormOptions,
) {
  const { defaultRequiredRule } = useFormRules()
  const { formRef, validate } = useNaiveForm()
  const { loading: submitting, startLoading: startSubmit, endLoading: endSubmit } = useLoading()
  const dialog = useDialog()
  const message = useClosableMessage()
  const messages = options?.messages || {}

  const model = ref({ ...initValue.value }) as Ref<T>
  const isDirty = computed(() => !isEqual(model.value, initValue.value))

  // Common validation rules
  const getBaseRules = (entityName: string = "Item") => ({
    name: [
      defaultRequiredRule,
      {
        min: 1,
        max: 40,
        message: `${entityName} name must be between 1 and 40 characters long`,
        trigger: ["change", "blur"],
      },
      {
        pattern: /^[\w\s-]*$/,
        message: `${entityName} name can only contain letters, numbers, spaces, and hyphens`,
        trigger: ["change", "blur"],
      },
      {
        validator: (rule: any, value: string) => {
          if (/^[_\s-]|[_\s-]$/.test(value)) {
            return new Error(`${entityName} name should not start or end with special characters`)
          }
          if (/[_\s-]{2,}/.test(value)) {
            return new Error("Special characters cannot appear consecutively")
          }
          return true
        },
        trigger: ["change", "blur"],
      },
    ],
    displayName: [
      defaultRequiredRule,
      {
        min: 1,
        max: 40,
        message: `${entityName} display name must be between 1 and 40 characters long`,
        trigger: ["change", "blur"],
      },
      {
        validator: (rule: any, value: string) => {
          if (/^[_-]|[_-]$/.test(value)) {
            return new Error(`${entityName} display name should not start or end with a hyphen`)
          }
          if (/[_-]{2,}/.test(value)) {
            return new Error("Hyphens cannot appear consecutively")
          }
          return true
        },
        trigger: ["change", "blur"],
      },
    ],
    type: [defaultRequiredRule],
  })

  function restoreModel() {
    model.value = { ...initValue.value }
    formRef.value?.restoreValidation()
  }

  async function handleCancel() {
    await nextTick(() => {
      restoreModel()
    })
  }

  async function handleConfirm(entityName: string = "Information") {
    await validate()

    const isNotChanged = isEqual(model.value, initValue.value)

    if (isNotChanged) {
      dialog.warning({
        title: messages.noChangesTitle || "No Changes Detected",
        content: messages.noChangesDescription || `${entityName} has not been modified.`,
        closable: false,
        positiveText: messages.closeText || "Close",
        positiveButtonProps: { size: "medium" },
        negativeText: messages.cancelText || "Cancel",
        negativeButtonProps: { size: "medium" },
        onPositiveClick: () => {
          if (onSuccess)
            onSuccess()
        },
      })
      return
    }

    startSubmit()

    try {
      const { data, error } = await onSubmit(model.value as T)

      if (error) {
        if (onError)
          onError(error)
        else message.error(messages.updateError || `Failed to update ${entityName.toLowerCase()}. Please try again.`)
      }
      else {
        message.success(messages.updateSuccess || `${entityName} updated successfully.`)
        if (onSuccess)
          onSuccess()
      }
    }
    catch (error) {
      if (onError)
        onError(error)
      else message.error(messages.updateError || `Failed to update ${entityName.toLowerCase()}. Please try again.`)
    }
    finally {
      endSubmit()
    }
  }

  // Watch for changes to initValue and update model
  watch(initValue, (val) => {
    if (val) {
      model.value = { ...val } as T
      formRef.value?.restoreValidation()
    }
  }, { immediate: true })

  return {
    model,
    formRef,
    submitting,
    isDirty,
    getBaseRules,
    restoreModel,
    handleCancel,
    handleConfirm,
    validate,
  }
}
