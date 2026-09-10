<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import apiModule from '../api/fontManager.js'

const props = defineProps({
  api: { type: Object, default: () => ({}) },
  enabled: { type: Boolean, default: true },
  refreshKey: { type: Number, default: 0 },
})
const emit = defineEmits(['notify', 'action'])

const summary = ref({ check: [], subset: [], lib_dir: '', binary_ok: false })
const uploads = ref([])
const loading = ref(false)
const expanded = ref({ check: false, subset: false })

const uploadRef = ref(null)
const uploading = ref(false)
const classifying = ref(false)
const clearing = ref(false)

const PREVIEW_N = 5

async function loadSummary() {
  loading.value = true
  try {
    summary.value = await apiModule.get(props.api, '/missing/summary')
  } catch (e) {
    emit('notify', e.message || '读取缺失字体汇总失败')
  } finally {
    loading.value = false
  }
}

async function loadUploads() {
  try {
    uploads.value = await apiModule.get(props.api, '/missing/uploads')
  } catch (e) {
    emit('notify', e.message || '读取上传列表失败')
  }
}

// 上传字体（左右两栏共用；不校验匹配，归类时统一入库）
async function handleUpload(event) {
  const files = Array.from(event.target.files || [])
  event.target.value = ''
  if (!files.length) return
  // 大量文件一次请求易触发网关请求体限制（410/413），分批顺序上传，每批 3 个
  const BATCH = 3
  let total = 0
  uploading.value = true
  try {
    for (let i = 0; i < files.length; i += BATCH) {
      const chunk = files.slice(i, i + BATCH)
      const form = new FormData()
      for (const file of chunk) form.append('file', file)
      const res = await props.api.post(
        'plugin/Zitifenlei/missing/upload',
        form,
        { headers: { 'Content-Type': 'multipart/form-data' } }
      )
      const body = res?.data ?? res
      if (body && body.success === false) {
        emit('notify', `第 ${i / BATCH + 1} 批上传失败：${body.message || '上传失败'}`)
        break
      } else {
        total += (body?.data?.count ?? chunk.length)
      }
    }
    emit('notify', `已上传 ${total} 个字体，点击「归类」入库并刷新索引`, 'success')
    await loadUploads()
    await loadSummary()
  } catch (e) {
    emit('notify', e.message || '上传失败')
  } finally {
    uploading.value = false
  }
}

// 归类：全部上传字体入库 + 重建索引（运行中禁用）
async function classify() {
  if (classifying.value) return
  classifying.value = true
  try {
    const res = await apiModule.post(props.api, '/missing/classify')
    emit('notify', res?.index_ok ? '已入库并刷新索引，请回到「子集化」页重新运行' : (res?.message || '已入库'), 'success')
    await loadUploads()
    await loadSummary()
    emit('action', { type: 'missing_classified' })
  } catch (e) {
    emit('notify', e.message || '归类失败')
  } finally {
    classifying.value = false
  }
}

async function clearUploads() {
  if (clearing.value) return
  clearing.value = true
  try {
    await apiModule.del(props.api, '/missing/uploads/clear')
    uploads.value = []
    emit('notify', '已清除上传的字体', 'success')
  } catch (e) {
    emit('notify', e.message || '清除失败')
  } finally {
    clearing.value = false
  }
}

// 删除单条已上传字体（仅删临时文件与内存记录，不影响字体库）
async function removeUpload(path) {
  try {
    await apiModule.del(props.api, '/missing/uploads/remove', { path })
    uploads.value = uploads.value.filter(u => u.path !== path)
    emit('notify', '已移除该字体', 'success')
  } catch (e) {
    emit('notify', e.message || '移除失败')
  }
}

function toggleExpand(side) {
  expanded.value[side] = !expanded.value[side]
}

function shownItems(side) {
  const list = summary.value[side] || []
  return expanded.value[side] ? list : list.slice(0, PREVIEW_N)
}

onMounted(() => {
  loadSummary()
  loadUploads()
  startPolling()
})
onUnmounted(() => stopPolling())

let pollTimer = null
function startPolling() {
  stopPolling()
  pollTimer = setInterval(() => {
    loadSummary()
    loadUploads()
  }, 30000)
}
function stopPolling() {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = null
}
</script>

<template>
  <div class="zt-missing">
    <!-- 状态与操作（公共） -->
    <v-card class="zt-card-bg mb-4">
      <v-card-title class="zt-card-title">
        <v-icon start size="18">mdi-alert-circle-outline</v-icon>
        缺失字体统一管理
      </v-card-title>
      <v-card-text class="pt-0">
        <div class="zt-status-line text-body-2 mb-3">
          <span class="mr-5">
            <v-icon :size="16" :color="summary.binary_ok ? 'success' : 'error'" class="mr-1">
              {{ summary.binary_ok ? 'mdi-check-circle' : 'mdi-close-circle' }}
            </v-icon>
            assfonts：{{ summary.binary_ok ? '就绪' : '未就绪' }}
          </span>
          <span class="mr-5">
            <v-icon :size="16" :color="summary.lib_dir ? 'success' : 'warning'" class="mr-1">
              {{ summary.lib_dir ? 'mdi-folder-check' : 'mdi-folder-alert' }}
            </v-icon>
            字体库：{{ summary.lib_dir || '未配置' }}
          </span>
          <span>
            <v-icon :size="16" class="mr-1">mdi-tray-arrow-up</v-icon>
            已上传待归类：{{ uploads.length }} 个
          </span>
        </div>
        <v-alert v-if="uploads.length" type="info" density="compact" class="mb-3">
          已上传字体将在「归类」时统一归档到字体库并自动刷新 assfonts 索引；库中已有同名字体自动跳过不覆盖。
        </v-alert>
        <div class="zt-uploads pa-3" v-if="uploads.length">
          <v-chip
            v-for="u in uploads"
            :key="u.path"
            size="small"
            variant="tonal"
            color="primary"
            class="mr-2 mb-2"
            close
            :title="u.file_name"
            @click:close="removeUpload(u.path)"
          >
            {{ u.file_name }}
          </v-chip>
        </div>
        <div class="d-flex flex-wrap gap-2">
          <v-btn
            color="primary"
            variant="tonal"
            :disabled="!enabled || uploading || classifying"
            :loading="uploading"
            @click="uploadRef?.click()"
          >
            <v-icon start size="18">mdi-upload</v-icon>
            上传字体
          </v-btn>
          <input
            ref="uploadRef"
            type="file"
            accept=".ttf,.otf,.ttc,.woff,.woff2"
            multiple
            style="display: none"
            @change="handleUpload"
          />
          <v-btn
            color="success"
            variant="tonal"
            :disabled="!enabled || classifying || !uploads.length"
            :loading="classifying"
            title="全部上传字体入库 + 重建索引（运行中不可重复点击）"
            @click="classify"
          >
            <v-icon start size="18">mdi-database-import</v-icon>
            归类
          </v-btn>
          <v-btn
            variant="tonal"
            color="error"
            :disabled="!enabled || clearing || !uploads.length"
            :loading="clearing"
            title="清除已上传的字体"
            @click="clearUploads"
          >
            <v-icon start size="18">mdi-trash-can-outline</v-icon>
            清除全部
          </v-btn>
        </div>
      </v-card-text>
    </v-card>

    <v-row no-gutters class="zt-missing-row">
      <!-- 左栏：检查缺失 -->
      <v-col cols="12" md="6">
        <v-card class="zt-card-bg zt-missing-col">
          <v-card-title class="zt-card-title">
            <v-icon start size="18" color="warning">mdi-file-document-alert-outline</v-icon>
            检查缺失（{{ summary.check?.length ?? 0 }}）
          </v-card-title>
          <v-divider></v-divider>
          <v-progress-linear v-if="loading" indeterminate color="primary"></v-progress-linear>
          <div v-if="!loading && !(summary.check || []).length" class="zt-empty pa-6">
            检查页无缺失字体
          </div>
          <div v-else class="zt-list-body">
            <v-list density="compact" class="pa-0">
              <v-list-item v-for="f in shownItems('check')" :key="f.name" lines="two">
                <template #prepend>
                  <v-icon color="warning" size="18">mdi-alert</v-icon>
                </template>
                <v-list-item-title class="zt-font-name">{{ f.name }}</v-list-item-title>
                <v-list-item-subtitle class="zt-font-meta">{{ f.count }} 个字幕缺失</v-list-item-subtitle>
              </v-list-item>
            </v-list>
            <div v-if="(summary.check || []).length > PREVIEW_N" class="text-center pa-2">
              <v-btn size="small" variant="tonal" @click="toggleExpand('check')">
                {{ expanded.check ? '收起' : `展开全部（${summary.check.length}）` }}
              </v-btn>
            </div>
          </div>
        </v-card>
      </v-col>

      <!-- 右栏：子集化缺失 -->
      <v-col cols="12" md="6">
        <v-card class="zt-card-bg zt-missing-col">
          <v-card-title class="zt-card-title">
            <v-icon start size="18" color="error">mdi-subtitles-alert-outline</v-icon>
            子集化缺失（{{ summary.subset?.length ?? 0 }}）
          </v-card-title>
          <v-divider></v-divider>
          <v-progress-linear v-if="loading" indeterminate color="primary"></v-progress-linear>
          <div v-if="!loading && !(summary.subset || []).length" class="zt-empty pa-6">
            子集化无缺失字体
          </div>
          <div v-else class="zt-list-body">
            <v-list density="compact" class="pa-0">
              <v-list-item v-for="f in shownItems('subset')" :key="f.name" lines="two">
                <template #prepend>
                  <v-icon color="error" size="18">mdi-close-octagon-outline</v-icon>
                </template>
                <v-list-item-title class="zt-font-name">{{ f.name }}</v-list-item-title>
                <v-list-item-subtitle class="zt-font-meta">{{ f.count }} 个字幕子集化时缺此字体</v-list-item-subtitle>
              </v-list-item>
            </v-list>
            <div v-if="(summary.subset || []).length > PREVIEW_N" class="text-center pa-2">
              <v-btn size="small" variant="tonal" @click="toggleExpand('subset')">
                {{ expanded.subset ? '收起' : `展开全部（${summary.subset.length}）` }}
              </v-btn>
            </div>
          </div>
        </v-card>
      </v-col>
    </v-row>

    <div class="zt-tip mt-3 text-body-2">
      提示：上传字体 → 点「归类」入库并自动刷新索引 → 回到「子集化」页重新运行即可。
    </div>
  </div>
</template>

<style scoped>
.zt-card-title {
  font-size: 15px;
  font-weight: 600;
}
.zt-missing-col {
  height: 560px;
  overflow: auto;
}
.zt-list-body {
  min-height: 60px;
}
.zt-uploads {
  max-height: 120px;
  overflow-y: auto;
  border: 1px solid var(--v-divider-color);
  border-radius: 4px;
}
.zt-empty {
  font-size: 13px;
  opacity: 0.6;
  text-align: center;
  line-height: 1.8;
}
.zt-font-name {
  font-size: 14px;
  font-weight: 500;
}
.zt-font-meta {
  font-size: 12px;
  opacity: 0.7;
}
.zt-tip {
  opacity: 0.65;
}
</style>