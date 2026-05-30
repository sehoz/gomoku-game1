<script setup lang="ts">
import { computed } from "vue";
import type { Move } from "../types";

const props = defineProps<{ size?: number; stones: Move[]; interactive?: boolean }>();
const emit = defineEmits<{ play: [x: number, y: number] }>();
const boardSize = computed(() => props.size || 15);
const step = computed(() => 100 / (boardSize.value - 1));
const starPoints = computed(() => {
  if (boardSize.value !== 15) return [];
  return [
    { x: 3, y: 3 },
    { x: 11, y: 3 },
    { x: 7, y: 7 },
    { x: 3, y: 11 },
    { x: 11, y: 11 },
  ];
});

function stoneAt(x: number, y: number) {
  return props.stones.find((stone) => stone.x === x && stone.y === y);
}

function isLastStone(x: number, y: number) {
  const last = props.stones[props.stones.length - 1];
  return Boolean(last && last.x === x && last.y === y);
}
</script>

<template>
  <div class="board-shell">
    <div class="board-grid" :style="{ backgroundSize: `${step}% ${step}%` }">
      <span
        v-for="point in starPoints"
        :key="`${point.x}-${point.y}`"
        class="board-star"
        :style="{ left: `${point.x * step}%`, top: `${point.y * step}%` }"
        aria-hidden="true"
      />
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
          :class="[
            'stone',
            `stone-${stoneAt((index - 1) % boardSize, Math.floor((index - 1) / boardSize))?.color}`,
            { 'stone-last': isLastStone((index - 1) % boardSize, Math.floor((index - 1) / boardSize)) },
          ]"
        />
      </button>
    </div>
  </div>
</template>
