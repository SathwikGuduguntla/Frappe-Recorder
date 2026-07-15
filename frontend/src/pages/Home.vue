<template>
  <div class="min-h-screen bg-gray-50 p-8">
    <!-- Header Hero Grid Section -->
    <div class="max-w-6xl mx-auto mb-12 flex flex-col md:flex-row md:items-center md:justify-between border-b border-gray-200 pb-8 gap-4">
      <div>
        <h1 class="text-3xl font-extrabold text-gray-900 tracking-tight">Frappe Screen Recorder</h1>
        <p class="text-gray-500 text-sm mt-1">Capture high-fidelity audio/video presentations and share them instantly.</p>
      </div>
      <div class="flex items-center gap-3">
        <router-link to="/library" class="px-4 py-2 bg-white border border-gray-300 hover:bg-gray-50 text-gray-700 font-medium rounded-lg shadow-sm transition">
          View Library
        </router-link>
        <router-link to="/record" class="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg shadow-sm transition flex items-center gap-2">
          <span class="w-2.5 h-2.5 bg-red-500 rounded-full animate-pulse"></span>
          New Recording
        </router-link>
      </div>
    </div>

    <!-- Quick Insights Dashboard Counters -->
    <div class="max-w-6xl mx-auto grid grid-cols-1 md:grid-cols-3 gap-6 mb-12">
      <div class="bg-white p-6 rounded-xl border border-gray-200 shadow-sm">
        <p class="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-1">Available Workspace</p>
        <h3 class="text-2xl font-bold text-gray-800">Frappe Cloud Storage</h3>
        <p class="text-xs text-green-600 mt-2 flex items-center gap-1">● Connected and Active</p>
      </div>
      <div class="bg-white p-6 rounded-xl border border-gray-200 shadow-sm">
        <p class="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-1">Sharing Access Model</p>
        <h3 class="text-2xl font-bold text-gray-800">Decoupled Public API</h3>
        <p class="text-xs text-gray-500 mt-2">Bypasses external origin limitations</p>
      </div>
      <div class="bg-white p-6 rounded-xl border border-gray-200 shadow-sm">
        <p class="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-1">Browser Interface Engine</p>
        <h3 class="text-2xl font-bold text-gray-800">MediaStreams MediaRecorder</h3>
        <p class="text-xs text-gray-500 mt-2">Native audio track compilation</p>
      </div>
    </div>

    <!-- Feature Quick Jump Cards -->
    <div class="max-w-6xl mx-auto">
      <h3 class="text-lg font-semibold text-gray-900 mb-6">Functional Management Hub</h3>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
        
        <!-- Option Block A: Record Screen -->
        <router-link to="/record" class="group bg-white p-8 rounded-2xl border border-gray-200 shadow-sm hover:border-blue-500 hover:shadow-md transition text-left flex flex-col justify-between">
          <div>
            <div class="w-12 h-12 bg-blue-50 text-blue-600 rounded-xl flex items-center justify-center mb-6 group-hover:bg-blue-600 group-hover:text-white transition">
              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" class="w-6 h-6">
                <path stroke-linecap="round" stroke-linejoin="round" d="M6 20.25h12m-7.5-3v3m3.75-3v3m-14.25-7.5h16.5m0 0A2.25 2.25 0 0 0 19.5 4.5h-15a2.25 2.25 0 0 0-2.25 2.25m19.5 0v.225a2.25 2.25 0 0 1-2.25 2.25h-15a2.25 2.25 0 0 1-2.25-2.25V6.75m19.5 0v3.375a2.25 2.25 0 0 1-2.25 2.25h-15a2.25 2.25 0 0 1-2.25-2.25V6.75" />
              </svg>
            </div>
            <h4 class="text-xl font-bold text-gray-900 group-hover:text-blue-600 transition">Launch Recording Interface</h4>
            <p class="text-gray-500 text-sm mt-2 leading-relaxed">Configure screen streams, manage local auxiliary microphonic nodes, capture desktop workspaces, and commit outputs to your DB.</p>
          </div>
          <span class="text-sm font-semibold text-blue-600 mt-6 inline-flex items-center gap-1 group-hover:translate-x-1 transition-transform">Configure Studio Options →</span>
        </router-link>

        <!-- Option Block B: Library -->
        <router-link to="/library" class="group bg-white p-8 rounded-2xl border border-gray-200 shadow-sm hover:border-blue-500 hover:shadow-md transition text-left flex flex-col justify-between">
          <div>
            <div class="w-12 h-12 bg-purple-50 text-purple-600 rounded-xl flex items-center justify-center mb-6 group-hover:bg-purple-600 group-hover:text-white transition">
              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" class="w-6 h-6">
                <path stroke-linecap="round" stroke-linejoin="round" d="M2.25 12.75V12A9 9 0 0 1 12 3v0a9 9 0 0 1 9 9v.75m-18 0A2.25 2.25 0 0 0 5.25 15h13.5A2.25 2.25 0 0 0 21 12.75m-18 0J12 9.75l6 3m-12 0v5.25A2.25 2.25 0 0 0 5.25 20h13.5A2.25 2.25 0 0 0 21 17.25V12.75" />
              </svg>
            </div>
            <h4 class="text-xl font-bold text-gray-900 group-hover:text-purple-600 transition">Manage Video Assets</h4>
            <p class="text-gray-500 text-sm mt-2 leading-relaxed">Review historical data logs, track dynamic view metrics, sort recorded entries by group hierarchies, and generate secure guest tokens.</p>
          </div>
          <span class="text-sm font-semibold text-purple-600 mt-6 inline-flex items-center gap-1 group-hover:translate-x-1 transition-transform">Browse File System →</span>
        </router-link>

      </div>
    </div>
  </div>
</template>

<script setup>
// Landing Dashboard Component Layout Logic
</script>