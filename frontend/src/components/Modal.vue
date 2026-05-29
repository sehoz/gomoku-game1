<script setup lang="ts">
import { X } from "lucide-vue-next";

defineProps<{ title: string }>();
const emit = defineEmits<{ close: [] }>();
</script>

<template>
  <div class="modal-backdrop">
    <section class="modal-card">
      <header class="modal-header">
        <h2>{{ title }}</h2>
        <button class="icon-button" type="button" @click="emit('close')"><X :size="18" /></button>
      </header>
      <slot />
    </section>
  </div>
</template>
