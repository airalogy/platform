<template>
  <n-form>
    <n-form-item label="Based project" path="projectId" required>
      <n-cascader
        v-model:value="model.combinedId"
        :options="options"
        placeholder="Choose a base project"
        check-strategy="child"
        :on-load="handleLoad"
        required
        remote
        :theme-overrides="{ columnWidth: '250px', menuBorderRadius: '10px' }"
        @update-show="fetchLabs"
      />
    </n-form-item>
  </n-form>
</template>

<script setup lang="ts">
import type { CascaderOption } from "naive-ui"
import { fetchProjectList } from "@/service/api/projects"
import { fetchUserLabs } from "@/service/api/users"
import { useAuthStore } from "@/store/modules/auth"
import { useClosableMessage } from "@airalogy/composables"

interface IProps {
  labId?: number
  projectId?: number
}

const props = defineProps<IProps>()

const model = ref()
const defaultOptions = ref<CascaderOption[] | null>(null)
const options = ref<CascaderOption[]>([])
const message = useClosableMessage()

const authStore = useAuthStore()
const hasFetched = ref(false)

async function handleLoad(option: CascaderOption) {
  const { value } = option

  try {
    const data = await fetchProjectList({
      labId: value as string,
      page: 1,
      pageSize: 9999,
    })
    if (data) {
      const children = data.projects.map(({ id, uid, name }) => {
        return { label: `${name} (${uid})`, value: `${value}_${id}`, depth: 2, isLeaf: true }
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
async function fetchLabs(show: boolean) {
  if (!show || hasFetched.value) {
    return
  }

  // TODO: order and pagination
  try {
    const data = await fetchUserLabs(authStore.userInfo.id, {
      page: 1,
      pageSize: 9999,
    })

    if (data) {
      const filteredOptions = data.labs.map((it) => {
        const { name, id, uid } = it

        return { label: `${name} (${uid})`, value: id, depth: 1, isLeaf: false }
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
</script>

<style scoped></style>
