<template>
  <div class="profile__panel">
    <div class="profile__avatar">
      <n-avatar
        :size="287"
        round
        :src="userInfo?.avatar_url || '/images/avatar_default.svg'"
      />
    </div>

    <template v-if="userInfo">
      <div class="profile__info mt-4">
        <h1 class="profile__username">
          {{ userInfo?.name }}
        </h1>
        <div class="profile__userid">
          {{ userInfo?.username }}
        </div>
        <div v-if="!isCurrentUser" class="profile__alias">
          <span v-if="userAlias" class="profile__alias-text">
            {{ $t("common.userAliasLabel") }}: {{ userAlias }}
          </span>
          <n-button size="tiny" quaternary @click="openUserAliasDialog">
            {{ $t("common.setUserAlias") }}
          </n-button>
        </div>
      </div>

      <div v-if="userInfo?.bio" class="profile__bio mt-4">
        <n-p>{{ userInfo.bio }}</n-p>
      </div>

      <div v-if="userInfo?.email" class="profile__contacts">
        <div class="profile__contact">
          <n-icon size="24">
            <icon-ion-mail-outline />
          </n-icon>
          <span>Email: <a :href="`mailto:${userInfo.email}`">{{ userInfo.email }}</a></span>
        </div>
      </div>
    </template>
    <div v-else class="mt-12">
      <n-skeleton text :repeat="2" />
      <n-skeleton text style="width: 60%" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { setUserAlias } from "@/service/api/users"
import UpdateAliasModal from "@/views/labs/modules/lab/UpdateAliasModal.vue"
import { useClosableMessage } from "@airalogy/composables"
import { $t } from "@airalogy/shared/locales"
import { useDialog } from "naive-ui"
import { useProfileStore } from "../hooks/useProfileStore"

const { userInfo, isCurrentUser } = useProfileStore()!
const dialog = useDialog()
const message = useClosableMessage()

const userAlias = computed(() => userInfo.value?.user_alias || "")

function openUserAliasDialog() {
  if (!userInfo.value?.id) {
    return
  }

  const aliasRef = ref<InstanceType<typeof UpdateAliasModal>>()
  const dialogInstance = dialog.info({
    title: $t("common.setUserAlias"),
    content: () =>
      h(UpdateAliasModal, {
        ref: aliasRef,
        alias: userAlias.value,
        label: $t("common.userAliasLabel"),
        placeholder: $t("common.userAliasPlaceholder"),
        requiredMessage: $t("common.userAliasRequired"),
        required: false,
      }),
    positiveText: "Confirm",
    negativeText: "Cancel",
    showIcon: false,
    onPositiveClick: async () => {
      dialogInstance.loading = true
      try {
        const alias = await aliasRef.value?.getAlias()
        const trimmedAlias = (alias as string || "").trim()
        await setUserAlias({ target_user_id: userInfo.value!.id, alias: trimmedAlias })
        userInfo.value!.user_alias = trimmedAlias
        message.success("Alias updated successfully")
      }
      catch (e) {
        message.error((e as Error).message)
        return false
      }
      finally {
        dialogInstance.loading = false
      }
    },
  })
}
</script>

<style lang="sass" scoped>
.profile
  &__panel
    display: flex
    flex-direction: column
    background: #fff
  &__avatar
    width: 287px
    height: 287px
    margin: 0 auto
    display: flex
    justify-content: center
    align-items: center

    :deep(.n-avatar)
      border: 1px solid #eee

  &__info
    display: flex
    flex-direction: column

  &__username
    font-size: 24px
    font-weight: 500
    color: #333333
    margin-bottom: 2px
    line-height: 34px

  &__userid
    font-size: 20px
    color: #666666
    margin-bottom: 16px
    line-height: 28px

  &__alias
    display: flex
    align-items: center
    gap: 8px
    margin-top: 6px

  &__alias-text
    font-size: 14px
    color: #667085

  &__bio
    font-size: 16px
    line-height: 1.5
    color: #333333
    margin: 0

  &__contacts
    display: flex
    flex-direction: column
    gap: 12px

  &__contact
    display: flex
    align-items: center
    gap: 6px
    color: #666666
    font-size: 16px

    :deep(.n-icon)
      color: #666666
</style>
