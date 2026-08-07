<template>
  <div class="pa-4" style="max-width: 900px; margin: 0 auto;">
    <!-- Header -->
    <v-card variant="tonal" color="primary" flat class="mb-4 rounded-lg">
      <v-card-item>
        <template #prepend>
          <v-btn variant="text" icon="mdi-arrow-left" size="small" @click="$emit('navigate', 'page')" />
        </template>
        <v-card-title class="text-h5 font-weight-bold">
          <v-icon size="24" class="mr-2">mdi-cog-outline</v-icon>
          插件设置
        </v-card-title>
      </v-card-item>
    </v-card>

    <!-- Settings Form -->
    <v-card flat elevation="0" class="rounded-lg border pa-4">
      <!-- Enable -->
      <v-switch v-model="config.enabled" label="启用插件" color="primary" hide-details class="mb-4" />

      <!-- Run Once + Cron -->
      <v-row dense>
        <v-col cols="6">
          <v-switch v-model="config.onlyonce" label="立即运行一次" color="warning" hide-details />
        </v-col>
        <v-col cols="6">
          <v-text-field v-model="config.cron" label="定时扫描 cron 表达式" variant="outlined" density="compact" placeholder="0 4 * * *" hide-details />
        </v-col>
      </v-row>

      <!-- Libraries -->
      <v-select
        v-model="config.libraries"
        :items="libOptions"
        label="选择要扫描的媒体库（留空=全库）"
        variant="outlined"
        density="compact"
        chips
        multiple
        clearable
        class="mt-4"
        hide-details
      />

      <!-- Prompt Template -->
      <v-textarea
        v-model="config.prompt_template"
        label="自定义大模型提示词"
        variant="outlined"
        density="compact"
        rows="8"
        class="mt-4"
        hide-details
        :placeholder="defaultPrompt"
      />

      <!-- Translate Types -->
      <div class="mt-4 text-subtitle-2 font-weight-bold mb-2">翻译类型</div>
      <v-row dense>
        <v-col cols="6" sm="4">
          <v-switch v-model="config.translate_actor" label="Actor" color="primary" hide-details density="compact" />
        </v-col>
        <v-col cols="6" sm="4">
          <v-switch v-model="config.translate_voice_actor" label="VoiceActor" color="primary" hide-details density="compact" />
        </v-col>
        <v-col cols="6" sm="4">
          <v-switch v-model="config.translate_director" label="Director" color="primary" hide-details density="compact" />
        </v-col>
        <v-col cols="6" sm="4">
          <v-switch v-model="config.translate_writer" label="Writer" color="primary" hide-details density="compact" />
        </v-col>
        <v-col cols="6" sm="4">
          <v-switch v-model="config.translate_producer" label="Producer" color="primary" hide-details density="compact" />
        </v-col>
        <v-col cols="6" sm="4">
          <v-switch v-model="config.translate_all" label="所有类型" color="primary" hide-details density="compact" />
        </v-col>
      </v-row>

      <!-- Limits -->
      <v-row dense class="mt-2">
        <v-col cols="4">
          <v-text-field v-model="config.max_people_per_title" label="每条目最多翻译人数" type="number" variant="outlined" density="compact" hide-details />
        </v-col>
        <v-col cols="4">
          <v-text-field v-model="config.max_people_per_batch" label="单批送大模型人数" type="number" variant="outlined" density="compact" hide-details />
        </v-col>
        <v-col cols="4">
          <v-text-field v-model="config.delay" label="条目间延迟(秒)" type="number" variant="outlined" density="compact" hide-details />
        </v-col>
      </v-row>

      <!-- Options -->
      <v-row dense class="mt-2">
        <v-col cols="6">
          <v-switch v-model="config.overwrite_chinese" label="覆盖已有中文" color="warning" hide-details density="compact" />
        </v-col>
        <v-col cols="6">
          <v-switch v-model="config.force_refresh" label="强制刷新(清缓存)" color="error" hide-details density="compact" />
        </v-col>
      </v-row>

      <!-- Save -->
      <v-divider class="my-4" />
      <div class="d-flex">
        <v-btn variant="tonal" prepend-icon="mdi-arrow-left" @click="$emit('navigate', 'page')" class="mr-2">
          返回数据面板
        </v-btn>
        <v-spacer />
        <v-btn color="primary" prepend-icon="mdi-content-save" @click="saveConfig" :loading="saving">
          保存设置
        </v-btn>
      </div>

      <v-snackbar v-model="snackbar.show" :color="snackbar.color" timeout="3000" location="top">
        {{ snackbar.text }}
      </v-snackbar>
    </v-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'

const emit = defineEmits(['navigate'])

const API_BASE = '/api/v1/plugin/EmbyPeopleLocalize'

const defaultPrompt = `你是一位世界级的影视专家，扮演一个只返回 JSON 的 API。
你的任务是利用提供的影视上下文，准确地将外语或拼音的演员名和角色名翻译成 **简体中文**。

**输入格式：**
你将收到一个包含 context（含 title 和 year）和 terms（待翻译字符串列表）的 JSON 对象。

**你的策略：**
1. 利用上下文确定具体的剧集/电影，找到官方中文译名
2. 将拼音/英文/日文翻译成汉字
3. 目标语言永远是简体中文
4. 无法翻译时使用原始字符串

**输出格式（强制）：**
必须返回有效的 JSON 对象，将每个原始词条映射到中文翻译。`

const config = reactive({
  enabled: false,
  onlyonce: false,
  cron: '0 4 * * *',
  libraries: [],
  prompt_template: defaultPrompt,
  translate_actor: true,
  translate_voice_actor: true,
  translate_director: false,
  translate_writer: false,
  translate_producer: false,
  translate_all: false,
  max_people_per_title: 15,
  max_people_per_batch: 5,
  overwrite_chinese: false,
  force_refresh: false,
  delay: 2,
})

const libOptions = ref([])
const saving = ref(false)
const snackbar = reactive({ show: false, text: '', color: 'success' })

async function fetchConfig() {
  try {
    const res = await fetch(`${API_BASE}/config`)
    if (res.ok) {
      const data = await res.json()
      Object.assign(config, data)
    }
  } catch (e) { /* use defaults */ }
}

async function fetchLibraries() {
  try {
    const res = await fetch(`${API_BASE}/libraries`)
    if (res.ok) {
      const data = await res.json() || []
      libOptions.value = data.map(l => ({ title: l, value: l }))
    }
  } catch (e) { /* ignore */ }
}

async function saveConfig() {
  saving.value = true
  try {
    const res = await fetch(`${API_BASE}/config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
    })
    if (res.ok) {
      snackbar.text = '设置已保存'
      snackbar.color = 'success'
    } else {
      snackbar.text = '保存失败'
      snackbar.color = 'error'
    }
  } catch (e) {
    snackbar.text = '保存失败: ' + e.message
    snackbar.color = 'error'
  } finally {
    saving.value = false
    snackbar.show = true
  }
}

onMounted(() => {
  fetchConfig()
  fetchLibraries()
})
</script>
