<template>
  <div class="max-w-3xl mx-auto my-10 p-6 bg-white border border-gray-200 rounded-xl shadow-sm">
    <div class="mb-6">
      <h1 class="text-2xl font-bold text-gray-900">Screen Recorder Studio</h1>
      <p class="text-gray-500 text-sm mt-1">Capture your full workspace interface with integrated system and microphone inputs.</p>
    </div>

    <div class="mb-6 bg-gray-950 rounded-lg aspect-video flex items-center justify-center overflow-hidden border border-gray-800 shadow-inner relative">
      <video 
        ref="previewVideo" 
        autoplay 
        muted 
        playsinline 
        class="w-full h-full object-contain"
        :class="{ 'hidden': !streamActive }"
      ></video>
      
      <div v-if="!streamActive && !isUploading" class="text-center text-gray-500 p-4">
        <div class="w-12 h-12 rounded-full bg-gray-900 border border-gray-800 flex items-center justify-center mx-auto mb-3">
          <span class="w-3 h-3 bg-red-500 rounded-full"></span>
        </div>
        <p class="text-sm font-medium">No live media inputs active</p>
      </div>

      <div v-if="isUploading" class="text-center text-blue-400 p-4">
        <span class="animate-spin border-2 border-blue-400 border-t-transparent rounded-full w-8 h-8 block mx-auto mb-3"></span>
        <p class="text-sm">Encoding stream and uploading binary payload...</p>
      </div>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
      <div>
        <label class="block text-xs font-semibold uppercase tracking-wider text-gray-400 mb-1">Recording Session Title</label>
        <input 
          v-model="title" 
          type="text" 
          :disabled="isRecording || isUploading"
          class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none text-sm disabled:bg-gray-50 text-gray-800"
        />
      </div>
      <div class="flex items-center md:pt-5">
        <label class="inline-flex items-center cursor-pointer">
          <input 
            v-model="includeMic" 
            type="checkbox" 
            :disabled="isRecording || isUploading"
            class="h-4 w-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500" 
          />
          <span class="ml-2 text-sm text-gray-600 font-medium">Include External Microphone Track</span>
        </label>
      </div>
    </div>

    <div class="flex flex-wrap items-center gap-3 border-t border-gray-100 pt-5">
      <button 
        v-if="!isRecording" 
        @click="startRecording" 
        :disabled="isUploading"
        class="px-5 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white text-sm font-semibold rounded-lg shadow-sm transition flex items-center gap-2"
      >
        <span class="w-2.5 h-2.5 bg-white rounded-full"></span>
        Start Capturing Screen
      </button>

      <button 
        v-else 
        @click="stopRecording" 
        class="px-5 py-2.5 bg-red-600 hover:bg-red-700 text-white text-sm font-semibold rounded-lg shadow-sm transition flex items-center gap-2 animate-pulse"
      >
        <span class="w-2.5 h-2.5 bg-white rounded-sm"></span>
        Stop & Save Session
      </button>

      <router-link to="/library" class="px-5 py-2.5 bg-white border border-gray-300 hover:bg-gray-50 text-gray-700 text-sm font-medium rounded-lg shadow-sm transition ml-auto">
        Back to Library
      </router-link>
    </div>

    <div v-if="shareUrl" class="mt-6 p-4 bg-green-50 border border-green-200 rounded-lg flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
      <div>
        <p class="text-sm font-bold text-green-900">🎉 Broadcast Clip Compiled Successfully!</p>
        <p class="text-xs text-green-700 mt-0.5">The raw recording record has been committed directly to your database logs.</p>
      </div>
      <a :href="shareUrl" target="_blank" class="px-3 py-1.5 bg-green-600 hover:bg-green-700 text-white text-xs font-semibold rounded-md shadow transition text-center whitespace-nowrap">
        Open Shared Link
      </a>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRecorder } from '../composables/useRecorder'

const title = ref('Capture Stream — ' + new Date().toLocaleDateString())
const includeMic = ref(true)
const shareUrl = ref(null)
const streamActive = ref(false)
const previewVideo = ref(null)

const { isRecording, isUploading, start, stop } = useRecorder()

// Global capture cache layers
let globalStream = null

async function startRecording() {
  shareUrl.value = null
  try {
    // 1. Initialize screen capture parameters
    const screenStream = await navigator.mediaDevices.getDisplayMedia({
      video: true,
      audio: true 
    })
    
    globalStream = screenStream

    // 2. Connect binary stream directly to visual video container element 
    if (previewVideo.value) {
      previewVideo.value.srcObject = screenStream
      streamActive.value = true
    }

    // 3. Initiate the backend document processing sequence via our useRecorder composable hook
    // The composable handles the audio mixing internally or captures configuration defaults
    await start(title.value, null, includeMic.value)
    
    // Wire automated callback fallback hooks if the native client clicks browser "Stop Sharing" bubble
    screenStream.getVideoTracks()[0].onended = () => {
      stopRecording()
    }

  } catch (error) {
    console.error('Session configuration aborted:', error)
    alert('User cancelled capture permissions or layout selection context failed.')
  }
}

async function stopRecording() {
  // 1. Trigger the stop method and catch the backend resource mapping response payload context
  const result = await stop()
  
  // 2. Clear visual presentation data links safely
  if (globalStream) {
    globalStream.getTracks().forEach(track => track.stop())
  }
  
  if (previewVideo.value) {
    previewVideo.value.srcObject = null
  }
  
  streamActive.value = false

  // 3. Bind the returned sharing link to display the generated distribution card layout view
  if (result && result.share_url) {
    shareUrl.value = result.share_url
  }
}
</script>