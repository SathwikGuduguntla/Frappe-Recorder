<template>
	<div class="min-h-screen bg-surface-gray-1">
		<AppHeader />

		<main class="mx-auto max-w-2xl px-4 py-6">
			<h1 class="text-xl font-semibold text-ink-gray-9">Settings</h1>

			<DriveAccountCard
				class="mt-6"
				title="Google Drive storage"
				description="Save every recording to a folder in your Google Drive. Shared links keep working, and play from Drive if the copy on this site is removed."
			/>

			<template v-if="session.isSystemManager">
				<h2 class="mt-10 text-base font-semibold text-ink-gray-9">Site settings</h2>
				<DriveAccountCard
					class="mt-3"
					site
					title="Drive folder for visitors' recordings"
					description="Recordings made without logging in are saved to this folder."
				/>
				<section
					class="mt-4 flex flex-wrap items-center gap-3 rounded-6 border border-outline-gray-2 bg-surface-base p-4"
				>
					<span class="lucide-user-round-x size-5 text-ink-gray-6" />
					<div class="min-w-0 flex-1">
						<h3 class="font-medium text-ink-gray-9">Recording without an account</h3>
						<p class="mt-0.5 text-sm text-ink-gray-6">
							{{
								session.allowGuestRecording
									? 'Anyone can record without logging in, within the size and hourly limits.'
									: 'Switched off: people must log in to record.'
							}}
						</p>
					</div>
					<Button
						label="Recorder Settings"
						icon-right="lucide-arrow-up-right"
						href="/app/recorder-settings"
					/>
				</section>
			</template>
		</main>
	</div>
</template>

<script setup>
import { onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Button, toast } from 'frappe-ui'

import AppHeader from '@/components/AppHeader.vue'
import DriveAccountCard from '@/components/DriveAccountCard.vue'
import { session } from '@/session'

const route = useRoute()
const router = useRouter()

onMounted(() => {
	// back from Google's consent screen
	if (route.query.drive === 'connected')
		toast.success('Google Drive connected. Now paste a folder link.')
	if (route.query.drive === 'error')
		toast.error('Could not connect Google Drive. Please try again.')
	if (route.query.drive) router.replace({ query: {} })
})
</script>
