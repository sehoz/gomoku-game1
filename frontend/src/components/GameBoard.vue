<script setup lang="ts">
import { computed } from "vue";
import type { Move } from "../types";

const props = defineProps<{ size?: number; stones: Move[]; interactive?: boolean }>();
const emit = defineEmits<{ play: [x: number, y: number] }>();
const boardSize = computed(() => props.size || 15);
const step = computed(() => 100 / (boardSize.value - 1));

function stoneAt(x: number, y: number) {
  return props.stones.find((stone) => stone.x === x && stone.y === y);
}
</script>

<template>
  <div class="board-shell">
    <div class="board-grid" :style="{ backgroundSize: `${step}% ${step}%` }">
      <button
        v-for="index in boardSize * boardSize"
        :key="index"
        class="board-point"
        :disabled="!interactive || Boolean(stoneAt((index - 1) % boardSize, Math.floor((index - 1) / boardSize)))"
        :style="{ left: `${((index - 1) % boardSize) * step}%`, top: `${Math.floor((index - 1) / boardSize) * step}%` }"
        type="button"
        @click="emit('play', (index - 1) % boardSize, Math.floor((index - 1) / boardSize))"
      >
        <span
          v-if="stoneAt((index - 1) % boardSize, Math.floor((index - 1) / boardSize))"
          :class="['stone', `stone-${stoneAt((index - 1) % boardSize, Math.floor((index - 1) / boardSize))?.color}`]"
        />
      </button>
    </div>
  </div>
</template>
