<script setup lang="ts">
defineProps<{ username: string; size?: "sm" | "lg" }>();
</script>

<template>
  <span :class="['avatar', size === 'lg' ? 'avatar-lg' : 'avatar-sm']">{{ username.slice(0, 1) }}</span>
</template>
