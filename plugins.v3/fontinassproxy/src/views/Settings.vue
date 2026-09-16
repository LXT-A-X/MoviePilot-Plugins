<script setup>
import { inject, onMounted, ref, getCurrentInstance } from 'vue'
import api from '../api.js'

const props = defineProps({
  api: { type: Object, default: () => ({}) },
  initialConfig: { type: Object, default: () => ({}) },
})
const emit = defineEmits(['save'])
const toast = inject('moviepilot:toast', null)
const instance = getCurrentInstance()

const DEFAULTS = {
  enabled: true,
  emby_url: '',
  emby_api_key: '',
  font_dirs: '',
  srt_default_font: '思源黑体 CN',
  srt_font_size: 20,
  srt_primary_colour: '&H00FFFFFF',
  cache_enabled: true,
  cache_ttl_hours: 24,
  max_concurrent_subset: 4,
  passthrough_on_error: true,
  internal_proxy_enabled: false,
  internal_proxy_port: 8097,
  notify_enabled: true,
}

const cfg = ref({ ...DEFAULTS })
const saving = ref(false)

function toastMsg(type, message) {
  if (toast && typeof toast[type] === 'function') toast[type](message)
}

onMounted(async () => {
  instance?.emit('layout', { maxWidth: '68rem' })
  try {
    const cur = await api.get(props.api, '/config')
    cfg.value = { ...DEFAULTS, ...(props.initialConfig || {}), ...(cur || {}) }
  } catch (e) {
    toastMsg('error', '加载配置失败: ' + e.message)
  }
})

async function save() {
  saving.value = true
  try {
    await api.post(props.api, '/config', cfg.value)
    emit('save')
    toastMsg('success', '配置已保存并生效')
  } catch (e) {
    toastMsg('error', '保存失败: ' + e.message)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <v-card variant="tonal" class="pa-4">
    <!-- 启用提示（设置页专用横幅由父容器处理） -->
    <v-row dense>
      <v-col cols="12">
        <v-switch v-model="cfg.enabled" label="启用插件"
                  hint="关闭时字幕请求原样透传（返回 502）" persistent-hint />
      </v-col>
      <v-col cols="12" md="6">
        <v-text-field v-model="cfg.emby_url" label="Emby/Jellyfin 地址"
                      hint="如 http://192.168.1.10:8096，需 MoviePilot 容器可访问" persistent-hint density="comfortable" />
      </v-col>
      <v-col cols="12" md="6">
        <v-text-field v-model="cfg.emby_api_key" label="回源 API Key"
                      hint="留空则转发客户端原始 api_key" persistent-hint density="comfortable" />
      </v-col>
      <v-col cols="12">
        <v-textarea v-model="cfg.font_dirs" label="字体目录" rows="2" auto-grow
                    hint="多个用 ; 分隔，递归扫描；目录必须挂载进 MoviePilot 容器" persistent-hint density="comfortable" />
      </v-col>
      <v-col cols="12" md="4">
        <v-text-field v-model="cfg.srt_default_font" label="SRT 兜底字体"
                      hint="SRT / 无明确字体名 / 字体缺失时兜底" persistent-hint density="comfortable" />
      </v-col>
      <v-col cols="12" md="4">
        <v-text-field v-model="cfg.srt_font_size" label="SRT 转 ASS 字号" type="number" density="comfortable" />
      </v-col>
      <v-col cols="12" md="4">
        <v-text-field v-model="cfg.srt_primary_colour" label="SRT 转 ASS 主色（BGR）"
                      hint="十六进制，如 &H00FFFFFF" persistent-hint density="comfortable" />
      </v-col>
      <v-col cols="12" md="4">
        <v-switch v-model="cfg.cache_enabled" label="处理结果缓存" hint="内存 + 磁盘双层" persistent-hint />
      </v-col>
      <v-col cols="12" md="4">
        <v-text-field v-model="cfg.cache_ttl_hours" label="缓存有效期（小时）" type="number"
                      hint="磁盘缓存保留时长，默认 24（1 天）；每 4 小时清理一次" persistent-hint density="comfortable" />
      </v-col>
      <v-col cols="12" md="4">
        <v-text-field v-model="cfg.max_concurrent_subset" label="子集化并发上限" type="number"
                      hint="保护 MP 主进程，超限请求降级透传" persistent-hint density="comfortable" />
      </v-col>
      <v-col cols="12">
        <v-switch v-model="cfg.passthrough_on_error" label="处理失败时返回原始字幕"
                  hint="关闭时失败返回 500" persistent-hint />
      </v-col>
      <v-col cols="12" md="6">
        <v-switch v-model="cfg.internal_proxy_enabled" label="启用内置反代端口"
                  hint="不依赖 nginx，客户端直接访问本端口；需要在 MP 容器映射该端口" persistent-hint />
      </v-col>
      <v-col cols="12" md="6">
        <v-text-field v-model="cfg.internal_proxy_port" label="内置反代端口" type="number"
                      hint="如 8097，MP 容器需映射（ports 加 8097:8097）" persistent-hint density="comfortable" />
      </v-col>
      <v-col cols="12">
        <v-switch v-model="cfg.notify_enabled" label="启用通知"
                  hint="新字体入库 / 缺失字体 / 处理错误时发送消息通知（默认开启，关闭则静默）" persistent-hint />
      </v-col>
    </v-row>
    <v-row class="justify-end mt-2" no-gutters>
      <v-btn color="primary" :loading="saving" @click="save">保存配置</v-btn>
    </v-row>
  </v-card>
</template>