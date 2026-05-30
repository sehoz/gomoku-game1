<script setup lang="ts">
import { watch } from "vue";
import GlobalSettings from "./components/GlobalSettings.vue";
import { authState, initAuth } from "./stores/auth";
import { connectPresence } from "./stores/presence";

initAuth();
connectPresence();
watch(() => authState.user?.id, () => connectPresence());
</script>

<template>
  <RouterView />
  <GlobalSettings />
</template>
