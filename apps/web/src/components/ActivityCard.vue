<template>
  <div class="activity-card">
    <div class="activity-card__badge">
      <div class="badge badge--green">
        <span>{{ props.badgeText }}</span>
      </div>
    </div>

    <div class="activity-card__content">
      <div class="activity-card__user-info">
        <img :src="props.avatarSrc" :alt="`${props.username}'s avatar`">
        <div>
          <div class="activity-card__user">
            <span class="activity-card__username">{{ props.username }}</span>
            <span class="activity-card__action">{{ props.action }}</span>
          </div>
          <div class="activity-card__time">
            {{ props.timeAgo }}
          </div>
        </div>
      </div>
      <div class="activity-card__path">
        {{ props.path }}
      </div>
      <p class="activity-card__description">
        {{ props.description }}
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
interface Props {
  badgeText: string
  avatarSrc?: string
  username: string
  action: string
  timeAgo: string
  path: string
  description: string
}

const props = withDefaults(defineProps<Props>(), {
  badgeText: "Activities",
  avatarSrc: "/images/avatar.svg",
  username: "John Doe",
  action: "updated",
  timeAgo: "1 hour ago",
})
</script>

<style scoped lang="sass">
.activity-card
  @apply bg-white border border-solid border-[#EAECF0] rounded-8px shadow-[0px_6px_18px_rgba(43,54,94,0.06)] p-20px relative

.activity-card__badge
  @apply inline-flex mb-10px

.badge
  @apply inline-flex items-center justify-center px-17px py-6px rounded-34px text-14px font-400

.badge--green
  @apply bg-[#1BA37B] text-white

.activity-card__user-info
  @apply flex items-center gap-10px my-1

.activity-card__content
  @apply flex flex-col gap-5px

.activity-card__user
  @apply flex gap-5px

.activity-card__username
  @apply text-13px font-500 text-[#333333]

.activity-card__action
  @apply text-13px font-400 text-[#333333]

.activity-card__time
  @apply text-10px font-400 text-[#666666]

.activity-card__path
  @apply text-13px font-500 text-[#333333] mt-5px

.activity-card__description
  @apply text-11px font-400 text-[#666666] my-5px
</style>
