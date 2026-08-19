<template>
  <div class="activity-card">
    <div class="activity-card__badge">
      <div class="badge badge--green aira-type-label">
        <span>{{ props.badgeText }}</span>
      </div>
    </div>

    <div class="activity-card__content">
      <div class="activity-card__user-info">
        <img class="activity-card__avatar" :src="props.avatarSrc" :alt="`${props.username}'s avatar`">
        <div class="min-w-0">
          <div class="activity-card__user">
            <span class="activity-card__username aira-type-item-title">{{ props.username }}</span>
            <span class="activity-card__action aira-type-body">{{ props.action }}</span>
          </div>
          <div class="activity-card__time aira-type-meta">
            {{ props.timeAgo }}
          </div>
        </div>
      </div>
      <div class="activity-card__path aira-type-item-title">
        {{ props.path }}
      </div>
      <p class="activity-card__description aira-type-body aira-text-muted">
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
  @apply relative border border-solid border-[#EAECF0] rounded-8px bg-white p-4 shadow-[0px_6px_18px_rgba(43,54,94,0.06)] sm:p-5

.activity-card__badge
  @apply mb-3 inline-flex

.badge
  @apply inline-flex items-center justify-center rounded-full px-4 py-1.5

.badge--green
  @apply bg-[#1BA37B] text-white

.activity-card__user-info
  @apply my-1 flex min-w-0 items-center gap-3

.activity-card__avatar
  @apply h-10 w-10 shrink-0 rounded-full object-cover

.activity-card__content
  @apply flex min-w-0 flex-col gap-2

.activity-card__user
  @apply flex min-w-0 flex-wrap items-baseline gap-x-1.5 gap-y-0

.activity-card__username
  @apply shrink-0

.activity-card__action
  @apply min-w-0

.activity-card__path
  @apply mt-2 break-words

.activity-card__description
  @apply my-1 break-words
</style>
