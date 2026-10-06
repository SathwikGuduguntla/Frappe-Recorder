<template>
  <div class="mx-auto max-w-2xl px-4 py-8 sm:px-6">
    <h1 class="text-2xl font-semibold text-ink-gray-9">Settings</h1>
    <p class="mt-1 text-base text-ink-gray-6">
      Finished recordings are saved on this site and listed in the File Manager under Home / Recordings.
    </p>

    <AiSettingsCard />
  </div>
</template>

<script setup>
import AiSettingsCard from '@/components/AiSettingsCard.vue'
</script>
