<template>
  <section class="hero">
    <div class="hero__content">
      <h1 class="hero__title">
        Airalogy
      </h1>
      <p class="hero__description">
        The world's first universal platform for research digitization, automation, and acceleration.
      </p>
      <div class="hero__buttons">
        <n-button type="primary" icon-placement="right" @click="toLogin()">
          Get Started
          <template #icon>
            <n-icon>
              <icon-local-arrow-outline-right />
            </n-icon>
          </template>
        </n-button>
        <n-button @click="toLogin()">
          Explore Protocols
        </n-button>
      </div>
    </div>

    <div class="hero__cards">
      <activity-card
        class="hero__card z-20 w-full md:ml-auto md:w-80"
        badge-text="Activities"
        username="Alice"
        action="updates a protocol"
        time-ago="9 min ago"
        path="Airalogy / Drug Discovery / CCK8 Protocol"
        description="Objective: Evaluate the inhibitory effect of a drug on tumor cell proliferation using the CCK-8 ..."
      />

      <organization-card
        class="hero__card mr-auto mt-4 w-full md:w-80 md:-mt-4"
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
  @apply w-full p-6 flex flex-col md:flex-row md:px-0 justify-between overflow-hidden
  background: url('/images/hero_placeholder.png') no-repeat right bottom / contain

.hero__content
  @apply my-auto w-full md:w-1/2 text-center md:text-left

.hero__title
  @apply text-12 font-600 text-[#333333]

.hero__description
  @apply text-6 font-400 text-[#666666] opacity-80

.hero__buttons
  @apply flex items-center gap-16px justify-center mt-4 mb-5 md:justify-start

.hero__cards
  @apply flex flex-col w-full px-6 md:p-10 md:w-11/24 items-center md:items-end
  min-width: min(30rem, 100%)

.hero__card
  &:hover
    @apply scale-105 transition-all duration-300
</style>
