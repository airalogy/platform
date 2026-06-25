<template>
  <div>
    <n-spin :show="loading" class="w-full">
      <project-list v-if="!loading && Array.isArray(list) && list.length > 0" :list="list" />
      <div v-else-if="!loading" class="absolute-center">
        <create-project-modal @modal:new-project="handleAddProject" />
      </div>
    </n-spin>
  </div>
</template>

<script setup lang="ts">
import { useLoading, useShowModal } from "@/composables"
import { fetchProjectList } from "@/service/api/projects"
import { useRouterPush } from "../../composables/useRouterPush"
import CreateProjectModal from "./modules/create-project-modal.vue"
import ProjectList from "./modules/project-list.vue"

defineOptions({
  name: "ResearchProtocol",
})

const emits = defineEmits<IEmits>()

interface IEmits {
  (e: "modal:show"): void
}

const list = ref<Api.Project.ProjectItem[]>([])
const { loading, startLoading, endLoading } = useLoading()
const { isShown: isNewLabShown, hideModal } = useShowModal()
const route = useRoute()

async function fetchProjects() {
  startLoading()

  const { labId } = route.params
  if (!labId || Array.isArray(labId)) {
    return
  }

  try {
    const data = await fetchProjectList({ labId })
    if (data && Array.isArray(data)) {
      list.value = data
    }
  }
  catch (e) {
    // NOPE
  }
  finally {
    endLoading()
  }
}

const { routerPushByKey } = useRouterPush()
async function handleAddProject(val: Api.Project.MyProjectInfo) {
  const { lab_uid, uid } = val

  if (!lab_uid || !uid) {
    return
  }

  await routerPushByKey("project-protocols", { params: { labUid: lab_uid, projectUid: uid } })
}
onMounted(async () => {
  await fetchProjects()
})
</script>

<style scoped lang="sass">
@use "@styles/sass/list.sass" as *
</style>
