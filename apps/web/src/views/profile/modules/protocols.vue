<template>
  <div class="size-full">
    <define-wrapper-item v-slot="{ $slots, title, handleViewAll, contentClass }">
      <div class="mb-4">
        <div class="mb-4 flex items-center gap-2 text-lg font-medium">
          {{ title }}
          <n-button
            v-if="handleViewAll"
            quaternary
            icon-placement="right"
            size="small"
            class="ml-1"
            @click="handleViewAll"
          >
            View All
            <template #icon>
              <n-icon size="12">
                <icon-ion-ios-arrow-forward />
              </n-icon>
            </template>
          </n-button>
        </div>
        <n-card class="w-full" size="small" :content-class="contentClass || '!p-1' ">
          <component :is="$slots.default" />
        </n-card>
      </div>
    </define-wrapper-item>

    <div class="size-full" v-bind="$attrs">
      <wrapper-item v-if="airalogyEduProtocols.length > 0" title="Airalogy Edu" content-class="!p-4">
        <div v-if="isLoading" class="flex justify-center py-4">
          <n-spin size="medium" />
        </div>

        <project-protocol-list
          :list="airalogyEduProtocols"
          :show-actions="false"
          :show-private="showPrivate"
        />
      </wrapper-item>

      <wrapper-item title="All Protocols" content-class="!p-4">
        <div v-if="isLoading" class="flex justify-center py-4">
          <n-spin size="medium" />
        </div>

        <div v-else-if="userProtocolList && userProtocolList.length > 0">
          <project-protocol-list
            :list="userProtocolList"
            :show-actions="false"
            :show-private="showPrivate"
          />
        </div>

        <n-empty v-else description="No protocols found" />
      </wrapper-item>
    </div>
  </div>
</template>

<script lang="ts" setup>
import type { ProjectProtocolInfo } from "@airalogy/shared/types/models/protocol"
import { useAuthStore } from "@/store/modules/auth"
import ProjectProtocolList from "@/views/project/modules/project-protocol-list.vue"
import { createReusableTemplate } from "@vueuse/core"
import { fetchProtocols } from "../../../service/api/project-protocols"
import { useProfileStore } from "../hooks/useProfileStore"

defineOptions({ name: "ProfileProtocols", inheritAttrs: false })

const [DefineWrapperItem, WrapperItem] = createReusableTemplate<{
  title: string
  handleViewAll?: () => void
  contentClass?: string
}>()

const {
  userInfo,
  userProtocolList,
  userProtocolCount,
  fetchUserProtocolsData,
} = useProfileStore()!

const airalogyEduProtocols = ref<ProjectProtocolInfo[]>([])

// Workaround for missing property in the store
const isLoading = ref(false)

const authStore = useAuthStore()

const showPrivate = computed(() => {
  return authStore.userInfo.id === userInfo.value?.id
})

// We'll use the original watch but add our own loading state
watch(
  () => userInfo.value?.id,
  async (id) => {
    if (id) {
      isLoading.value = true
      try {
        await fetchUserProtocolsData(id)
      }
      finally {
        isLoading.value = false
      }
    }
  },
  { immediate: true },
)
onMounted(async () => {
  try {
    const res = await fetchProtocols({
      projectUid: "nlp",
      labUid: "edu",
      page: 1,
      pageSize: 9999,
    })
    if (res.data) {
      airalogyEduProtocols.value = res.data.protocols
    }
  }
  catch (e) {

  }
})
</script>

<style lang="sass" scoped></style>
