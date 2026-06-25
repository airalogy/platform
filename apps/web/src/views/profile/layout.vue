<template>
  <global-layout>
    <div class="profile__container">
      <base-profile />
      <div class="profile__divider" />
      <profile-content-layout v-if="tabs.length > 1" :tabs-props="tabsProps" :tabs="tabs" class="profile__content flex-1" />
      <global-content v-else container-class="profile__content flex-1" />
    </div>
  </global-layout>
</template>

<script setup lang="ts">
import type { TabPaneProps, TabsProps } from "naive-ui"
import GlobalLayout from "@/layouts/global-layout/index.vue"
import GlobalContent from "@/layouts/modules/global-content/index.vue"
import { getUserByUsername } from "@/service/api/users"
import { $t } from "@airalogy/shared/locales"
import { useRouterPush } from "../../composables/useRouterPush"
import { useAuthStore } from "../../store/modules/auth"
import { useProvideProfileStore } from "./hooks/useProfileStore"
import BaseProfile from "./modules/base-profile.vue"
import ProfileContentLayout from "./modules/content-layout.vue"

defineOptions({ name: "ProfileLayout" })

const route = useRoute()
const userStore = useAuthStore()
const username = computed(() => route.params.username as string)

const { fetchUserInfo, userInfo, isCurrentUser } = useProvideProfileStore(null)!

const tabsProps = ref<TabsProps>({
  type: "segment",
})

const tabs = ref<any>([
  {
    name: "user-profile",
    tab: $t("page.profile.summary"),
  },
  // {
  //   name: "profile-questions",
  //   tab: "Questions",
  // },
  // {
  //   name: "profile-answers",
  //   tab: "Answers",
  // },
  {
    name: "profile-protocols",
    tab: $t("page.profile.protocols"),
  },
  {
    name: "profile-records",
    tab: $t("page.recordDiary.tab"),
  },
] as (TabPaneProps & { name: App.Global.TabKey })[])

const { routerPushByKey } = useRouterPush()
onMounted(async () => {
  if (username.value) {
    const user = await fetchUserInfo({ username: username.value })
    if (!user) {
      routerPushByKey("not-found")
      return
    }

    await nextTick(() => {
      if (isCurrentUser.value) {
        tabs.value.push({
          name: "profile-starred",
          tab: $t("page.profile.starred"),
        }, {
          name: "profile-settings",
          tab: $t("page.profile.settings"),
        })
      }
    })
  }
})

watch(username, (val) => {
  useTitle(`${val} · Profile · Airalogy`)
}, { immediate: true })

onUnmounted(async () => {
  await getUserByUsername.clear()
})
</script>

<style lang="sass" scoped>
.profile
  &__container
    display: flex
    width: 100%
    min-width: 0
    min-height: calc(100vh - 70px)
    padding: 24px 0
    background: #fff
  &__content
    min-width: 0
    max-width: 100%
  &__divider
    width: 1px
    background: #E5E6EB
    margin: 0 32px

:deep(.profile__content)
  .n-tabs,
  .n-tab-pane
    min-width: 0
    max-width: 100%

:deep(.n-tabs)
  .n-tabs-nav
    background: none
    border-bottom: none

  .n-tab
    background: none
    border: none
    padding: 10px 20px
    font-size: 16px
    color: #666666
    cursor: pointer
    transition: color 0.3s

    &--active
      color: #333333
      font-weight: bold
      border-bottom: 2px solid var(--wck-qds)

  .n-tab-pane
    padding: 20px 0

.stats
  display: flex
  gap: 40px
  margin-bottom: 24px
  padding-bottom: 16px
  border-bottom: 1px solid #E5E6EB

  &__item
    display: flex
    align-items: center
    gap: 8px
    position: relative

  &__label
    font-size: 18px
    color: #666666

  &__badge
    background: #E7EFFF
    color: #333333
    padding: 0 7px
    height: 20px
    border-radius: 10px
    font-size: 14px
    display: flex
    align-items: center
</style>
