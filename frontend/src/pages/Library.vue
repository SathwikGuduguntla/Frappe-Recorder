<template>
  <div class="p-8">
    <div class="flex justify-between items-center mb-8">
      <div>
        <h1 class="text-3xl font-bold text-gray-900">Your Recording Library</h1>
        <p class="text-gray-500 text-sm mt-1">Manage, sort, and distribute internal and public captures.</p>
      </div>
      <router-link to="/record" class="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg transition">
        Record Video
      </router-link>
    </div>

    <div v-if="recordings.loading" class="text-center py-12 text-gray-500">
      Fetching files matching account profile...
    </div>

    <div v-else-if="!recordings.data || recordings.data.length === 0" class="text-center py-16 border-2 border-dashed border-gray-300 rounded-2xl">
      <p class="text-gray-500 font-medium">No recorded files located.</p>
      <router-link to="/record" class="text-blue-600 text-sm underline mt-2 block">Create your first capture now</router-link>
    </div>

    <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      <div v-for="item in recordings.data" :key="item.name" class="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm flex flex-col">
        <div class="bg-gray-100 aspect-video flex items-center justify-center relative border-b border-gray-100">
          <video v-if="item.video_file" :src="item.video_file" class="w-full h-full object-cover" preload="metadata"></video>
          <span class="absolute bottom-2 right-2 bg-black/70 text-white text-xs px-2 py-0.5 rounded font-mono">
            {{ item.duration_seconds }}s
          </span>
        </div>
        
        <div class="p-4 flex-grow flex flex-col justify-between">
          <div>
            <h3 class="font-semibold text-gray-900 line-clamp-1 mb-1">{{ item.title }}</h3>
            <p class="text-xs text-gray-400 mb-4">Created: {{ new Date(item.creation).toLocaleDateString() }}</p>
          </div>
          
          <div class="flex items-center justify-between gap-2 mt-auto">
            <span class="px-2 py-0.5 text-xs font-medium rounded-full" 
              :class="item.status === 'Ready' ? 'bg-green-50 text-green-700 border border-green-200' : 'bg-yellow-50 text-yellow-700'">
              {{ item.status }}
            </span>
            <router-link :to="`/share/${item.route}`" class="text-sm font-medium text-blue-600 hover:text-blue-700">
              View & Share →
            </router-link>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { createListResource } from "frappe-ui";

// Bypasses custom api proxy calls using direct framework multi-row data bindings
const recordings = createListResource({
  doctype: "Screen Recording",
  fields: ["name", "title", "video_file", "duration_seconds", "status", "route", "creation"],
  orderBy: "creation desc",
  auto: true
});
</script>