<template>
  <div style="min-height: 100vh">
    <Page v-if="currentView === 'page'" @navigate="currentView = $event" />
    <Config v-else-if="currentView === 'config'" @navigate="currentView = $event" />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import Page from './Page.vue'
import Config from './Config.vue'

const currentView = ref('page')
</script>
