<template>
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
    @click.stop="handleEditProject"
  >
    <template #icon>
      <edit-icon />
    </template>
  </n-button>
</template>

<script setup lang="ts">
import { useRouterPush } from "@/composables"

import { NButton } from "naive-ui/es/button"
import { useOrProvideLabInfoStore } from "../../views/labs/hooks/useLabsInfoStore"

interface IProps {
  item?: Api.Lab.LabInfo | Api.Project.MyProjectInfo | (Api.Groups.GroupsInfo & { lab_uid: string }) | null
  type: "lab" | "group" | "project"
}

const props = withDefaults(defineProps<IProps>(), {
  item: null,
})

const { labInfo, fetchLabInfoByUid } = useOrProvideLabInfoStore(null)
const { routerPushByKey } = useRouterPush()

async function handleEditProject() {
  const { type, item } = props
  if (type === "lab") {
    const { uid } = item as Api.Lab.LabInfo

    routerPushByKey("lab-settings", {
      params: {
        labUid: uid,
      },
    })
  }
  if (type === "project") {
    const { lab_uid, uid } = item as Api.Project.MyProjectInfo

    routerPushByKey("project-settings", {
      params: {
        labUid: lab_uid,
        projectUid: uid,
      },
    })
  }
  if (type === "group") {
    const { id, lab_uid } = item as Api.Groups.GroupsInfo & { lab_uid: string }
    if (!labInfo.value) {
      await fetchLabInfoByUid(lab_uid)
      await nextTick()
    }

    if (labInfo.value) {
      routerPushByKey("lab-group-settings", {
        params: {
          labUid: labInfo.value.uid,
          groupId: id,
        },
      })
    }
  }
}
</script>

<style scoped lang="sass">
:deep(.n-base-selection-tags)
  justify-content: flex-start!important
  align-items: start!important
  flex-direction: column!important
</style>
