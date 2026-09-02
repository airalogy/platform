<template>
  <section v-if="items.length" class="research-log-field">
    <span>{{ label }}</span>
    <ul>
      <li v-for="(item, index) in items" :key="`${index}:${item}`">
        {{ item }}
      </li>
    </ul>
  </section>
</template>

<script setup lang="ts">
defineProps<{ label: string, items: string[] }>()
</script>

<style scoped lang="sass">
.research-log-field
  min-width: 0
  border-radius: 8px
  background: #F8FAFC
  padding: 12px

  span
    color: #64748B
    font-size: 12px
    font-weight: 600
    letter-spacing: 0.04em
    text-transform: uppercase

  ul
    margin: 8px 0 0
    padding-left: 18px

  li
    margin-top: 4px
    overflow-wrap: anywhere
</style>
