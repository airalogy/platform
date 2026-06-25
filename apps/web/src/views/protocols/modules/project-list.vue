<template>
  <n-list>
    <n-list-item v-for="item in props.list" :key="item.id">
      <template #prefix>
        <project-icon class="align-middle" />
      </template>
      <router-link to="/">
        {{ item.name }}
      </router-link>
    </n-list-item>
  </n-list>
</template>

<script setup lang="ts">
defineOptions({ name: "ProjectList" })

const props = withDefaults(defineProps<IProps>(), {
  list: () => [],
})

interface IProps {
  list: Partial<Api.Project.ProjectItem>[]
}
</script>

<style scoped></style>
