<template>
  <div class="footer-container">
    <div class="list__title header-title md:mb-2.5">
      {{ props.title }}
    </div>
    <div class="content-container link__list">
      <template v-for="item in props.list" :key="item.name">
        <a
          v-if="item.external && typeof item.to === 'string'"
          :href="item.to"
          target="_blank"
          rel="noreferrer"
        >
          <img v-if="item.icon" :src="item.icon" :alt="`${item.name} icon`" class="link__icon">
          {{ item.name }}
        </a>
        <router-link v-else :to="item.to">
          <img v-if="item.icon" :src="item.icon" :alt="`${item.name} icon`" class="link__icon">
          {{ item.name }}
        </router-link>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { RouteLocationRaw } from "vue-router"

interface IProps {
  title: string
  list: { name: string, to: RouteLocationRaw, external?: boolean, icon?: string }[]
}
const props = withDefaults(defineProps<IProps>(), {
  title: "GO",
  list: () => [],
})
</script>

<style scoped lang="sass">
@use "@styles/sass/list.sass" as *

.footer-container
  background: #2B2B38
  color: white
  @apply flex flex-shrink-0 flex-basis-full flex-row pl-4 lg:flex-basis-1/6 md:flex-col md:flex-basis-1/3 lg:pl-30 mt-3 md:mt-0

.header-title
  color: white
  height: fit-content
  text-transform: uppercase
  @apply w-1/3  md:w-fit

.content-container
  color: white

.link__list
  min-width: fit-content
  a
    text-decoration: none
    text-transform: capitalize
    color: white
    display: block
    font-size: 16px
    width: fit-content
    white-space: nowrap
    opacity: 0.8
    transition: .2s linear opacity
    @apply mb-2

    &:hover
      opacity: 1

.link__icon
  display: inline-block
  width: 16px
  height: 16px
  margin-right: 8px
  vertical-align: middle
</style>
