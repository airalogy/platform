<template>
  <n-list>
    <template v-if="protocolInfo">
      <discussion-list-item
        v-for="item in props.list"
        :key="item.id"
        :item="item"
        :navigate-params="navigateParams"
      />
    </template>
    <template v-else>
      <n-skeleton v-for="item in 5" :key="item" />
    </template>
  </n-list>
</template>

<script lang="ts" setup>
// import { getUserInfoById } from "@/service/api/users"
import { useProtocolInfoStore } from "../../hooks/useProtocolInfoStore"
import DiscussionListItem from "./components/discussion-list-item.vue"

interface IProps {
  list: Api.Discussion.QuestionItem[]
  protocolId: string
}

const props = defineProps<IProps>()

const { protocolInfo } = useProtocolInfoStore()! || {}

const navigateParams = computed(() => {
  if (!protocolInfo.value) {
    return {} as Record<string, string>
  }
  const { lab, project, uid } = protocolInfo.value

  return {
    labUid: lab.uid,
    projectUid: project.uid,
    protocolUid: uid,
  } as Record<string, string>
})

// const listWithUser = computedAsync<
//   (Api.Discussion.QuestionItem & { user?: Api.Profile.User | null })[]
// >(async () => {
//       const result = await Promise.allSettled(
//         props.list.map(item => (item.user_id ? getUserInfoById(item.user_id) : null)),
//       )

//       return props.list.map((item, index) => {
//         const res = result[index]
//         if (res.status === "fulfilled") {
//           return { ...item, user: res.value?.data }
//         }

//         return { ...item, user: null }
//       })
//     }, props.list)
</script>

<style scoped lang="sass">
.article-number
  font-size: 12px
:deep(.n-list-item__main)
  max-width: 100%
</style>
