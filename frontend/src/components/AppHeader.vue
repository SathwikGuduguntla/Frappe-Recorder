<template>
  <header class="border-b border-outline-gray-1 bg-surface-base">
    <div class="mx-auto flex h-14 max-w-6xl items-center gap-6 px-4 sm:px-6">
      <router-link :to="{ name: 'Record' }" class="flex items-center gap-2">
        <span class="flex size-7 items-center justify-center rounded-lg bg-surface-gray-10">
          <span class="size-2.5 rounded-full bg-surface-red-6" />
        </span>
        <span class="text-lg font-semibold text-ink-gray-9">Recorder</span>
      </router-link>

      <nav v-if="session.user" class="flex items-center gap-1">
        <router-link
          v-for="item in navItems"
          :key="item.name"
          :to="{ name: item.name }"
          class="rounded-md px-2.5 py-1.5 text-base text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9"
          exact-active-class="bg-surface-gray-2 !text-ink-gray-9 font-medium"
        >
          {{ item.label }}
        </router-link>
      </nav>

      <div class="ml-auto flex items-center gap-3">
        <span v-if="session.user" class="hidden text-sm text-ink-gray-5 sm:block">{{ session.full_name }}</span>
        <Button v-else-if="session.loaded" variant="solid" label="Record a video" :route="{ name: 'Record' }" />
      </div>
    </div>
  </header>
</template>

<script setup>
import { computed } from 'vue'
import { Button } from 'frappe-ui'
import { loadSession, session } from '@/api'

loadSession()

const navItems = computed(() => {
  const items = [
    { name: 'Record', label: 'Record' },
    { name: 'Library', label: 'Library' },
  ]
  if (session.is_manager) items.push({ name: 'Settings', label: 'Settings' })
  return items
})
</script>
