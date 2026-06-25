<template>
  <div class="min-h-[200px] p-4">
    <template v-if="questions.length">
      <div class="space-y-4">
        <n-collapse>
          <n-collapse-item
            v-for="qa in questions"
            :key="qa.id"
            :title="qa.question"
          >
            <div class="whitespace-pre-wrap">
              {{ qa.answer }}
            </div>
            <div class="mt-2 text-sm text-gray-500">
              Answered by {{ qa.answeredBy }} on {{ formatDate(qa.answeredAt) }}
            </div>
          </n-collapse-item>
        </n-collapse>
      </div>
    </template>
    <n-empty v-else description="No questions asked yet">
      <template #extra>
        <n-button secondary @click="$emit('askQuestion')">
          Ask a Question
        </n-button>
      </template>
    </n-empty>
  </div>
</template>

<script setup lang="ts">
import { formatDate } from "@airalogy/shared/utils"

interface Question {
  id: string
  question: string
  answer: string
  answeredBy: string
  answeredAt: string
}

defineEmits<{
  (e: "askQuestion"): void
}>()

const questions = ref<Question[]>([])

// Add your Q&A loading logic here
</script>
