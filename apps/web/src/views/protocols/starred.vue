<template>
  <n-spin :show="loading" class="w-full">
    <project-list v-if="!loading && Array.isArray(list) && list.length > 0" :list="list" />
  </n-spin>
</template>

<script setup lang="ts">
import { useLoading, useShowModal } from "@/composables"
import ProjectList from "./modules/project-list.vue"

defineOptions({
  name: "ProjectStarred",
})

const list = ref<Api.Project.ProjectItem[]>([])
const { loading, startLoading, endLoading } = useLoading()
const { isShown, showModal, hideModal } = useShowModal()

async function fetchProjectList() {
  startLoading()

  try {
    // const { data, error } = await request<Api.GetResponse<Api.Project.ProjectItem>>({
    //   url: "/projects/starred",
    //   params: { page_size: 10, page: 1 },
    // })
    // if (data && Array.isArray(data.data)) {
    //   list.value = data.data
    // }
  }
  catch (e) {
    // NOPE
  }
  finally {
    endLoading()
  }
}
onMounted(async () => {
  await fetchProjectList()
})
</script>

<style scoped lang="sass">
@use "@styles/sass/list.sass" as *
</style>
