<template>
  <div class="preset-cards">
    <div v-for="(card, index) in cards" :key="index" class="card" @click="openLink(card.link)">
      <h4>{{ card.title }}</h4>
      <p>{{ card.description }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue"

const props = defineProps<{
  content: string
}>()

const cards = computed(() => {
  try {
    return JSON.parse(props.content)
  }
  catch (e) {
    return []
  }
})

function openLink(link: string) {
  window.open(link, "_blank")
}
</script>

<style scoped>
.preset-cards {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
}

.card {
  background-color: #f7f7f7;
  border-radius: 8px;
  padding: 1rem;
  cursor: pointer;
  transition: background-color 0.3s;
  flex: 1 1 calc(50% - 1rem);
}

.card:hover {
  background-color: #e7e7e7;
}

.card h4 {
  margin: 0 0 0.5rem;
}

.card p {
  margin: 0;
  font-size: 0.9rem;
  color: #555;
}
</style>
