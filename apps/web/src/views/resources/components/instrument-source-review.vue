<script setup lang="ts">
import type { AuthoringCommandReview } from "@/service/api/instrument-authoring"

defineProps<{ commands: AuthoringCommandReview[] }>()
</script>

<template>
  <section class="my-3 min-w-0" data-testid="authoring-command-review">
    <h4>{{ $t("page.instrumentAuthoring.commandReview") }}</h4>
    <p class="my-2">
      {{ $t("page.instrumentAuthoring.declaredRiskHint") }}
    </p>
    <article v-for="command in commands" :key="`${command.key}@${command.version}`" class="mb-3 min-w-0 border rounded-lg p-3">
      <div class="flex flex-wrap items-center gap-2">
        <strong class="min-w-0 break-words">{{ command.name }}</strong>
        <n-tag :type="command.risk === 'read_only' ? 'info' : 'warning'">
          {{ $t(`page.resourceLibrary.risk.${command.risk}`) }}
        </n-tag>
      </div>
      <code class="block break-all text-xs">{{ command.key }}@{{ command.version }}</code>
      <p v-for="(effect, index) in command.effects" :key="index" class="my-2 break-words">
        {{ effect }}
      </p>
      <dl class="break-words">
        <dt class="font-semibold">
          {{ $t("page.instrumentAuthoring.completionContract") }}
        </dt>
        <dd class="mb-2">
          {{ command.completion }}
        </dd>
        <dt class="font-semibold">
          {{ $t("page.instrumentAuthoring.stopContract") }}
        </dt>
        <dd class="mb-2">
          {{ command.stop }}
        </dd>
      </dl>
      <n-collapse>
        <n-collapse-item :title="$t('page.instrumentAuthoring.safetyContract')">
          <pre class="whitespace-pre-wrap break-all text-xs">{{ JSON.stringify({ device_confirmation_required: command.device_confirmation_required, ...command.safety_contract }, null, 2) }}</pre>
        </n-collapse-item>
      </n-collapse>
    </article>
  </section>
</template>
