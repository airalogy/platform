<template>
  <n-card>
    <n-form :model="model">
      <n-form-item label="Protocol Records">
        <n-select
          v-model:value="model.rrec" :options="rrecOptions" :loading="loading" :clear-filter-after-select="true"
          placeholder="Enter Research Record id" remote clearable filterable multiple :show="isShowMenu" @search="handleSearch"
          @clear="handleClear" @update:value="handleValueChange"
        />
      </n-form-item>
      <!-- <n-form-item label="Date Range">
        <n-date-picker v-model="model.dateStart" placeholder="Start Date" />
        <span class="mx-4">-</span>
        <n-date-picker v-model="model.dateEnd" placeholder="End Date" />
      </n-form-item> -->

      <!-- <n-form-item label="Select Version">
        <n-select v-model="model.version" :options="versions" placeholder="Select Version" />
      </n-form-item> -->
      <!--
      <n-form-item label="Select Recent Versions">
        <n-select v-model="model.recentVersions" :disabled="Boolean(model.version)" :options="recentVersions"
          placeholder="Select Recent Versions" multiple>
        </n-select>
      </n-form-item> -->
      <markdown-editor v-model:text="model.comment" :post-add-attachments="postAddAttachments" />
    </n-form>
    <n-flex class="mt-4">
      <n-button type="primary" class="ml-auto" @click="handleConfirm">
        Confirm
      </n-button>
    </n-flex>
  </n-card>
</template>

<script setup lang="ts">
import type { SelectProps } from "naive-ui"
import type { SelectMixedOption } from "naive-ui/es/select/src/interface"
import { useBoolean, useLoading } from "@/composables"
import { postAddAttachments } from "@/service/api/attachments"

defineOptions({ name: "ChooseRrecModal", inheritAttrs: false })

const props = defineProps<IProps>()

const emit = defineEmits<IEmits>()

interface IProps {
  modelValue?: any
}

interface IEmits {
  (ev: "confirm"): void
  (ev: "update:rrec", val: any): void
  (ev: "update:modelValue", val: any): void
}
const { endLoading, loading, startLoading } = useLoading()
const { bool: isShowMenu, setFalse: hideMenu, setTrue: showMenu } = useBoolean()
interface ISelectParams {
  dateStart?: Date | null
  dateEnd?: Date | null
  version?: string | null
  recentVersions?: string[]
}

const model = useVModel(props, "modelValue", emit)

function handleConfirm() {
  emit("confirm")
}

const rrecIdList = ref<string[]>([])
const rrecOptions = ref<SelectMixedOption[]>([])

function handleClearOption() {
  hideMenu()
  setTimeout(() => (rrecOptions.value = []), 200)
}
function handleClear() {
  handleClearOption()
  rrecIdList.value = []
}

const selectedRRECList = ref<SelectMixedOption[]>([])
const handleValueChange: SelectProps["onUpdate:value"] = (
  _,
  option: { label: string, value: number, email: string, role: Api.Lab.LabRole }[],
) => {
  selectedRRECList.value = option
  handleClearOption()
}

const handleSearch = useDebounceFn(async (val: string) => {
  if (!val) {
    handleClearOption()
    return
  }

  startLoading()
  // const { id: userId } = authStore.userInfo
  try {
    const result = await new Promise((res) => {
      setTimeout(() => res({ data: [], total: 0 }), 1000)
    })
    //   if (result) {
    //     const { data } = result
    //     showMenu()
    //     if (Array.isArray(data)) {
    //       const defaultRole = props.type === "group" ? 2 : 3
    //       memberOptions.value = data
    //         .filter(({ id }) => id !== userId)
    //         .map(
    //           ({ name, username, id, email, avatar_url }): SelectOption => ({
    //             label: name || username,
    //             username,
    //             value: id,
    //             email,
    //             role: defaultRole,
    //             avatar: avatar_url,
    //           }),
    //         )
    //     }
    //   }
  }
  catch (e) {
    // NOPE
  }
  finally {
    endLoading()
  }
}, 500)

watchEffect((onCleanup) => {
  const cancelRequest = () => { }

  onCleanup(cancelRequest)
})

watch(
  () => model.value.rrec,
  (val) => {
    model.value.recentVersions = val?.metadata?.rn_ver
    model.value.recentVersions = val?.metadata?.rn_ver
  },
)
</script>

<style scoped lang="sass"></style>
