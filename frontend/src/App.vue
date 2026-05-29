<script setup lang="ts">
import GlobalSettings from "./components/GlobalSettings.vue";
import { initAuth } from "./stores/auth";

initAuth();
</script>

<template>
  <RouterView />
  <GlobalSettings />
</template>
