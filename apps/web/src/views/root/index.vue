<template>
  <section class="hero">
    <div class="hero__content">
      <h1 class="hero__title aira-type-display">
        Airalogy
      </h1>
      <p class="hero__description aira-text-secondary">
        The world's first universal platform for research digitization, automation, and acceleration.
      </p>
      <div class="hero__buttons">
        <n-button class="hero__button" type="primary" icon-placement="right" @click="toLogin()">
          Get Started
          <template #icon>
            <n-icon>
              <icon-local-arrow-outline-right />
            </n-icon>
          </template>
        </n-button>
        <n-button class="hero__button" @click="toLogin()">
          Explore Protocols
        </n-button>
      </div>
    </div>

    <div class="hero__cards">
      <activity-card
        class="hero__card hero__card--activity"
        badge-text="Activities"
        username="Alice"
        action="updates a protocol"
        time-ago="9 min ago"
        path="Airalogy / Drug Discovery / CCK8 Protocol"
        description="Objective: Evaluate the inhibitory effect of a drug on tumor cell proliferation using the CCK-8 ..."
      />

      <organization-card
        class="hero__card hero__card--organization"
        :labs="[
          {
            memberCount: 891,
            projectCount: 93,
            role: 'owner',
            logoSrc: '/images/logo1.svg',
            name: 'Airalogy',
          },
          {
            memberCount: 521,
            projectCount: 53,
            role: 'member',
            logoSrc: '/images/logo1.svg',
            name: 'Westlake University',
          },
        ]"
      />
    </div>
  </section>
</template>

<script setup lang="ts">
import ActivityCard from "@/components/ActivityCard.vue"
import OrganizationCard from "@/components/OrganizationCard.vue"
import { useRouterPush } from "@/composables"
import { useThemeStore } from "@airalogy/composables/theme"

const themeStore = useThemeStore()

const { toLogin } = useRouterPush()
onBeforeMount(() => {
  themeStore.content.containerContentClass = "min-h-70vh flex items-center"
})

onBeforeUnmount(() => {
  themeStore.content.containerContentClass = ""
})
</script>

<style scoped lang="sass">
.hero
  @apply relative w-full flex flex-col gap-10 overflow-hidden px-5 py-10 sm:px-8 sm:py-12 lg:flex-row lg:items-center lg:justify-between lg:gap-8 lg:px-6 lg:py-14 xl:gap-14
  background: url('/images/hero_placeholder.png') no-repeat right bottom / contain

.hero__content
  @apply relative z-10 mx-auto w-full max-w-2xl text-center lg:mx-0 lg:w-1/2 lg:max-w-xl lg:text-left xl:max-w-2xl

.hero__title
  font-size: clamp(2.75rem, 8vw, 4.5rem)
  line-height: 1.05
  letter-spacing: -0.035em

.hero__description
  @apply mx-auto mt-4 max-w-2xl font-400 lg:mx-0
  font-size: clamp(1.125rem, 2.4vw, 1.5rem)
  line-height: 1.45

.hero__buttons
  @apply mt-8 flex flex-col items-stretch justify-center gap-3 sm:flex-row sm:items-center lg:justify-start

.hero__button
  @apply h-11 w-full px-5 text-4 sm:w-auto

.hero__cards
  @apply relative z-10 mx-auto flex min-w-0 w-full max-w-2xl flex-col items-stretch lg:mx-0 lg:w-11/24 lg:max-w-[34rem]

.hero__card
  @apply w-full max-w-lg

  &:hover
    @apply transition-all duration-300

.hero__card--activity
  @apply z-20 self-end

.hero__card--organization
  @apply mt-4 self-start

@media (hover: hover) and (pointer: fine)
  .hero__card:hover
    @apply scale-[1.02]
</style>
