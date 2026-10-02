<template>
	<header
		class="sticky top-0 z-10 border-b border-outline-gray-1 bg-surface-base/90 backdrop-blur"
	>
		<div class="mx-auto flex h-14 max-w-6xl items-center gap-4 px-4">
			<router-link :to="session.isGuest ? '/record' : '/'" class="flex items-center gap-2">
				<img :src="logo" alt="" class="size-7" />
				<span class="text-base font-semibold text-ink-gray-9">Recorder</span>
			</router-link>

			<nav v-if="!session.isGuest" class="ml-2 hidden items-center gap-1 sm:flex">
				<Button variant="ghost" label="Library" :route="{ name: 'Library' }" />
				<Button variant="ghost" label="Settings" :route="{ name: 'Settings' }" />
			</nav>

			<div class="ml-auto flex items-center gap-2">
				<slot name="actions" />
				<template v-if="session.isGuest">
					<Button variant="subtle" label="Log in" @click="redirectToLogin()" />
					<Button
						variant="solid"
						label="Record a video"
						icon-left="lucide-circle-dot"
						@click="redirectToLogin('/recorder/record')"
					/>
				</template>
				<template v-else>
					<Button
						v-if="showRecordButton"
						variant="solid"
						label="New recording"
						icon-left="lucide-circle-dot"
						:route="{ name: 'Record' }"
					/>
					<Dropdown :options="userMenu" align="end">
						<button
							class="rounded-full focus:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3"
						>
							<Avatar
								:image="session.userImage"
								:label="session.fullName"
								size="lg"
							/>
						</button>
					</Dropdown>
				</template>
			</div>
		</div>
	</header>
</template>

<script setup>
import { Avatar, Button, Dropdown } from 'frappe-ui'
import { useRouter } from 'vue-router'
import logo from '@/assets/logo.svg'
import { logout, redirectToLogin, session } from '@/session'

defineProps({ showRecordButton: { type: Boolean, default: true } })

const router = useRouter()
const userMenu = [
	{ label: 'Library', icon: 'lucide-library', onClick: () => router.push({ name: 'Library' }) },
	{
		label: 'Settings',
		icon: 'lucide-settings',
		onClick: () => router.push({ name: 'Settings' }),
	},
	{
		label: 'Open Desk',
		icon: 'lucide-app-window',
		onClick: () => (window.location.href = '/app'),
	},
	{ label: 'Log out', icon: 'lucide-log-out', onClick: logout },
]
</script>
