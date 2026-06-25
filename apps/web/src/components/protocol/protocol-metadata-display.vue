<template>
  <div v-if="hasMaintainers" class="space-y-4">
    <!-- Disciplines -->
    <div v-if="!excludeFields?.includes('disciplines') && metadata.disciplines?.length">
      <div class="mb-1 text-gray-600">
        {{ $t("common.disciplines") }}
      </div>
      <div class="flex flex-wrap gap-1">
        <n-tag v-for="discipline in metadata.disciplines" :key="discipline" size="small">
          {{ discipline }}
        </n-tag>
      </div>
    </div>

    <!-- Keywords -->
    <div v-if="!excludeFields?.includes('keywords') && metadata.keywords?.length">
      <div class="mb-1 text-gray-600">
        {{ $t("common.keywords") }}
      </div>
      <div class="flex flex-wrap gap-1">
        <n-tag v-for="keyword in metadata.keywords" :key="keyword" size="small">
          {{ keyword }}
        </n-tag>
      </div>
    </div>

    <!-- Authors -->
    <div v-if="!excludeFields?.includes('authors') && metadata.authors?.length">
      <div class="mb-1 text-gray-600">
        {{ $t("common.authors") }}
      </div>
      <div v-for="(author, index) in metadata.authors" :key="`author-${index}`" class="mt-2 border-l-2 border-gray-200 pl-3">
        <n-grid :cols="2" :x-gap="8" :y-gap="4">
          <n-grid-item>
            <div class="text-gray-500">
              {{ $t("common.name") }}
            </div>
          </n-grid-item>
          <n-grid-item>
            <div class="text-right">
              {{ author.name }}
            </div>
          </n-grid-item>

          <n-grid-item v-if="author.email">
            <div class="text-gray-500">
              {{ $t("common.email") }}
            </div>
          </n-grid-item>
          <n-grid-item v-if="author.email">
            <div class="text-right">
              {{ author.email }}
            </div>
          </n-grid-item>

          <n-grid-item v-if="author.airalogy_user_id">
            <div class="text-gray-500">
              {{ $t("common.user") }}
            </div>
          </n-grid-item>
          <n-grid-item v-if="author.airalogy_user_id">
            <div class="flex items-center justify-end gap-2 text-sm">
              <router-link
                v-if="getUsername(author.airalogy_user_id)"
                class="inline-flex items-center gap-2 hover:router-link"
                :to="{ name: 'user-profile', params: { username: getUsername(author.airalogy_user_id) } }"
                target="_blank"
                rel="noopener noreferrer"
              >
                <n-avatar
                  v-if="userMap[author.airalogy_user_id]?.avatar_url"
                  :src="userMap[author.airalogy_user_id]?.avatar_url"
                  size="small"
                  :theme-overrides="{ color: 'transparent' }"
                />
                <span>
                  {{ getUsername(author.airalogy_user_id) }}
                </span>
              </router-link>
              <template v-else>
                <n-avatar
                  v-if="userMap[author.airalogy_user_id]?.avatar_url"
                  :src="userMap[author.airalogy_user_id]?.avatar_url"
                  size="small"
                  :theme-overrides="{ color: 'transparent' }"
                />
                <span v-if="userNameMap[author.airalogy_user_id]" class="font-mono">
                  {{ userNameMap[author.airalogy_user_id] }}
                </span>
                <span v-else class="font-mono">
                  {{ author.airalogy_user_id }}
                </span>
              </template>
            </div>
          </n-grid-item>
        </n-grid>
      </div>
    </div>

    <!-- Maintainers -->
    <div v-if="!excludeFields?.includes('maintainers') && metadata.maintainers?.length">
      <div class="mb-1 text-gray-600">
        {{ $t("common.maintainers") }}
      </div>
      <div v-for="(maintainer, index) in metadata.maintainers" :key="`maintainer-${index}`" class="mt-2 border-l-2 border-gray-200 pl-3">
        <n-grid :cols="2" :x-gap="8" :y-gap="4">
          <n-grid-item>
            <div class="text-gray-500">
              {{ $t("common.name") }}
            </div>
          </n-grid-item>
          <n-grid-item>
            <div class="text-right">
              {{ maintainer.name }}
            </div>
          </n-grid-item>

          <n-grid-item v-if="maintainer.email">
            <div class="text-gray-500">
              {{ $t("common.email") }}
            </div>
          </n-grid-item>
          <n-grid-item v-if="maintainer.email">
            <div class="text-right">
              {{ maintainer.email }}
            </div>
          </n-grid-item>

          <n-grid-item v-if="maintainer.airalogy_user_id">
            <div class="text-gray-500">
              {{ $t("common.user") }}
            </div>
          </n-grid-item>
          <n-grid-item v-if="maintainer.airalogy_user_id">
            <div class="flex items-center justify-end gap-2 text-sm">
              <router-link
                v-if="getUsername(maintainer.airalogy_user_id)"
                class="inline-flex items-center gap-2 hover:router-link"
                :to="{ name: 'user-profile', params: { username: getUsername(maintainer.airalogy_user_id) } }"
                target="_blank"
                rel="noopener noreferrer"
              >
                <n-avatar
                  v-if="userMap[maintainer.airalogy_user_id]?.avatar_url"
                  :src="userMap[maintainer.airalogy_user_id]?.avatar_url"
                  size="small"
                  :theme-overrides="{ color: 'transparent' }"
                />
                <span>
                  {{ getUsername(maintainer.airalogy_user_id) }}
                </span>
              </router-link>
              <template v-else>
                <n-avatar
                  v-if="userMap[maintainer.airalogy_user_id]?.avatar_url"
                  :src="userMap[maintainer.airalogy_user_id]?.avatar_url"
                  size="small"
                  :theme-overrides="{ color: 'transparent' }"
                />
                <span v-if="userNameMap[maintainer.airalogy_user_id]" class="font-mono">
                  {{ userNameMap[maintainer.airalogy_user_id] }}
                </span>
                <span v-else class="font-mono">
                  {{ maintainer.airalogy_user_id }}
                </span>
              </template>
            </div>
          </n-grid-item>
        </n-grid>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { resolveAiralogyUser } from "@/utils/user"
import { $t } from "@airalogy/shared/locales"
import { NAvatar, NGrid, NGridItem, NTag } from "naive-ui"

interface ProtocolPerson {
  name: string
  email?: string
  airalogy_user_id?: string
}

interface ProtocolMetadata {
  name?: string
  license?: string
  disciplines?: string[]
  keywords?: string[]
  authors?: ProtocolPerson[]
  maintainers?: ProtocolPerson[]
}

interface Props {
  metadata: ProtocolMetadata
  excludeFields?: string[]
}

const props = defineProps<Props>()
const userMap = reactive<Record<string, Api.Profile.User>>({})
const userNameMap = reactive<Record<string, string>>({})
const hasMaintainers = computed(() => {
  if (!props.metadata) {
    return false
  }

  const { maintainers, disciplines, keywords, authors } = props.metadata

  return maintainers || authors || disciplines || keywords
})

async function fetchUsersById(ids: string[]) {
  const uniqueIds = Array.from(new Set(ids.filter(Boolean)))
  if (!uniqueIds.length) {
    return
  }

  await Promise.all(
    uniqueIds.map(async (id) => {
      if (userMap[id]) {
        return
      }
      try {
        const { user, normalizedId } = await resolveAiralogyUser(id)
        if (normalizedId) {
          userNameMap[id] = normalizedId
        }
        if (user) {
          userMap[id] = user
        }
      }
      catch (e) {
        // ignore lookup errors
      }
    }),
  )
}

function getUsername(id?: string) {
  if (!id) {
    return ""
  }
  const mapped = userMap[id]?.username
  if (mapped) {
    return mapped
  }
  const fallback = userNameMap[id]
  if (fallback && !/^\d+$/.test(fallback)) {
    return fallback
  }
  return ""
}

watch(
  () => [props.metadata?.authors, props.metadata?.maintainers],
  async () => {
    const authorIds = props.metadata?.authors?.map(a => a.airalogy_user_id || "") || []
    const maintainerIds = props.metadata?.maintainers?.map(m => m.airalogy_user_id || "") || []
    await fetchUsersById([...authorIds, ...maintainerIds])
  },
  { immediate: true, deep: true },
)
</script>
