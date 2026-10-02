<template>
  <FrappeUIProvider>
    <div class="flex min-h-full flex-col">
      <AppHeader />
      <main class="flex-1">
        <router-view />
      </main>
    </div>
  </FrappeUIProvider>
</template>

<script setup>
import { FrappeUIProvider } from 'frappe-ui'
import AppHeader from '@/components/AppHeader.vue'
</script>
