<script setup lang="ts">
defineProps<{ username: string; avatarUrl?: string; size?: "sm" | "lg" }>();
</script>

<template>
  <span :class="['avatar', size === 'lg' ? 'avatar-lg' : 'avatar-sm']">
    <img v-if="avatarUrl" :src="avatarUrl" alt="" />
    <span v-else>{{ username.slice(0, 1) }}</span>
  </span>
</template>
