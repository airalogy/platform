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
      <wrapper-item v-if="hasStarredItems" title="Starred Items" content-class="!p-4">
        <n-list>
          <n-list-item v-for="item in starredFolders" :key="item.folder.id">
            <n-collapse accordion>
              <n-collapse-item :title="getDisplayFolderName(item.folder)" :name="item.folder.id">
                <n-list>
                  <n-list-item v-for="star in item.stars" :key="star.id">
                    <router-link
                      v-if="getStarRoute(star)"
                      :to="getStarRoute(star)!"
                      class="mb-2 block break-words text-[#333] hover:router-link"
                    >
                      {{ star.resource_summary }}
                    </router-link>
                    <p v-else class="mb-2 break-words">
                      {{ star.resource_summary }}
                    </p>
                    <div v-if="starUsers.has(star.resource_id)" class="flex items-center gap-2">
                      <n-text depth="3">
                        Starred by:
                      </n-text>
                      <n-avatar-group
                        :options="starUsers.get(star.resource_id)?.map(u => ({ name: u.name, src: u.avatar_url || '/images/avatar_default.svg' }))"
                        :size="24"
                        :max="5"
                      />
                    </div>
                  </n-list-item>
                </n-list>
              </n-collapse-item>
            </n-collapse>
          </n-list-item>
        </n-list>
      </wrapper-item>

      <n-empty v-if="!hasStarredItems && !isLoadingStarred" description="No starred items found" />
    </div>
  </div>
</template>

<script lang="ts" setup>
import type { RouteLocationRaw } from "vue-router"
import { getStarUsers, StarResourceType, type StarResponse, type StarUser } from "@/service/api/star"
import { $t } from "@airalogy/shared/locales"
import { createReusableTemplate } from "@vueuse/core"
import { useProfileStore } from "../hooks/useProfileStore"

defineOptions({ name: "ProfileStarred", inheritAttrs: false })

const [DefineWrapperItem, WrapperItem] = createReusableTemplate<{
  title: string
  handleViewAll?: () => void
  contentClass?: string
}>()

const {
  userInfo,
  isLoadingStarred,
  starredFolders,
  fetchUserStarredData,
} = useProfileStore()!

const starUsers = ref<Map<string, StarUser[]>>(new Map())

const hasStarredItems = computed(() => {
  return starredFolders.value.length > 0 && starredFolders.value.some(it => it.stars.length > 0)
})

function normalizeFolderName(name?: string | null) {
  return String(name || "").trim().toLocaleLowerCase()
}

function isDefaultFolderName(name?: string | null) {
  const normalized = normalizeFolderName(name)
  return normalized === "default"
    || normalized === "default folder"
    || normalized === "默认收藏夹"
    || normalized === normalizeFolderName($t("common.defaultFolder"))
}

function getDisplayFolderName(folder?: { name?: string | null, is_default?: boolean }) {
  if (!folder) {
    return ""
  }

  if (folder.is_default || isDefaultFolderName(folder.name)) {
    return $t("common.defaultFolder")
  }
  return folder.name || ""
}

function getStarRoute(star: StarResponse): RouteLocationRaw | null {
  const {
    resource_type: resourceType,
    resource_id: resourceId,
    lab_uid: labUid,
    project_uid: projectUid,
    protocol_uid: protocolUid,
    question_id: questionId,
  } = star

  if (!labUid || !projectUid || !protocolUid) {
    return null
  }

  if (resourceType === StarResourceType.Protocol) {
    return {
      name: "protocol-info",
      params: { labUid, projectUid, protocolUid },
    }
  }

  if (resourceType === StarResourceType.Question) {
    return {
      name: "protocol-discussion-detail",
      params: { labUid, projectUid, protocolUid, questionId: questionId || resourceId },
    }
  }

  if (resourceType === StarResourceType.Answer && questionId) {
    return {
      name: "protocol-discussion-detail",
      params: { labUid, projectUid, protocolUid, questionId },
    }
  }

  return null
}

async function fetchStarUsers() {
  if (!hasStarredItems.value)
    return
  try {
    const allStars = starredFolders.value.flatMap(folder => folder.stars)
    const promises = allStars.map(star =>
      getStarUsers({
        resource_type: star.resource_type,
        resource_id: star.resource_id,
        page_size: 5,
      }),
    )
    const results = await Promise.all(promises)
    const newStarUsers = new Map<string, StarUser[]>()
    allStars.forEach((star, index) => {
      if (results[index]?.users) {
        newStarUsers.set(star.resource_id, results[index]!.users)
      }
    })
    starUsers.value = newStarUsers
  }
  catch (error) {
    console.error("Failed to fetch star users:", error)
  }
}

watch(
  () => userInfo.value?.id,
  async (id) => {
    if (id) {
      await fetchUserStarredData()
      await fetchStarUsers()
    }
  },
  { immediate: true },
)
</script>

<style lang="sass" scoped></style>
