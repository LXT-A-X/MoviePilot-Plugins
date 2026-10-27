<script setup>
import { computed, onActivated, onDeactivated, onMounted, onUnmounted, ref } from 'vue'
import apiModule from '../api/fontManager.js'

const props = defineProps({
  api: { type: Object, default: () => ({}) },
  enabled: { type: Boolean, default: true },
  refreshKey: { type: Number, default: 0 },
})
const emit = defineEmits(['notify', 'action'])

const summary = ref({ check: [], subset: [], lib_dir: '', hb_ok: false, engine: 'harfbuzz', index_faces: 0 })
const uploads = ref([])
const mappings = ref([])
const loading = ref(false)
const expanded = ref({ check: false, subset: false })
// 严格上传：可选目标缺失字体（人工映射）；不选则按字体内部名称/别名自动匹配
const targetHint = ref(null)

const uploadRef = ref(null)
const uploading = ref(false)
const classifying = ref(false)
const clearing = ref(false)

const PREVIEW_N = 5

// 可选的缺失目标（检查缺失列表），用于上传时人工指定映射
const targetOptions = computed(() => (summary.value.check || []).map(f => ({
  name: f.name,
  title: f.chars ? `${f.name}（缺 ${f.codepoints_count || 0} 字：${f.chars}）` : f.name,
})))

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

// 上传字体（左右两栏共用）：严格校验（名称/别名命中且覆盖缺失字符），可选人工指定目标
async function handleUpload(event) {
  const files = Array.from(event.target.files || [])
  event.target.value = ''
  if (!files.length) return
  // 大量文件一次请求易触发网关请求体限制（410/413），分批顺序上传，每批 3 个
  const BATCH = 3
  let total = 0
  const rejected = []
  uploading.value = true
  try {
    for (let i = 0; i < files.length; i += BATCH) {
      const chunk = files.slice(i, i + BATCH)
      const form = new FormData()
      for (const file of chunk) form.append('file', file)
      if (targetHint.value) form.append('target', targetHint.value)
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
        total += (body?.data?.count ?? 0)
        for (const r of body?.data?.rejected || []) rejected.push(r)
      }
    }
    if (total) {
      emit('notify', `已上传 ${total} 个字体（通过缺失校验），点击「归类」入库`, 'success')
    }
    if (rejected.length) {
      const detail = rejected.slice(0, 3).map(r => `${r.file_name}：${r.reason}`).join('；')
      emit('notify', `${rejected.length} 个字体未通过校验：${detail}`, 'warning')
    }
    if (!total && !rejected.length) emit('notify', '没有字体通过缺失校验', 'warning')
    await loadUploads()
    await loadSummary()
    await loadMappings()
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
    const recheck = res?.recheck || {}
    let msg = res?.message || '已入库'
    if (recheck.checked) {
      msg += `（已重检 ${recheck.checked} 个字幕：完整 ${recheck.ok}，仍缺 ${recheck.missing}）`
    }
    emit('notify', msg, 'success')
    if ((res?.failed || []).length) {
      emit('notify', `${res.failed.length} 个字体未入库：${res.failed.slice(0, 3).join('；')}`, 'warning')
    }
    await loadUploads()
    await loadSummary()
    await loadMappings()
    emit('action', { type: 'missing_classified' })
  } catch (e) {
    emit('notify', e.message || '归类失败')
  } finally {
    classifying.value = false
  }
}

// ===== 人工映射（改派） =====
const remapDialog = ref(false)
const remapItem = ref(null)
const remapTarget = ref('')
const remapping = ref(false)

function openRemap(u) {
  remapItem.value = u
  remapTarget.value = u.matched || ''
  remapDialog.value = true
}

async function submitRemap() {
  if (!remapItem.value || !remapTarget.value) return
  remapping.value = true
  try {
    await apiModule.post(props.api, '/missing/remap', {
      path: remapItem.value.path,
      target: remapTarget.value,
    })
    emit('notify', '已改派缺失目标', 'success')
    remapDialog.value = false
    await loadUploads()
    await loadMappings()
  } catch (e) {
    emit('notify', e.message || '改派失败')
  } finally {
    remapping.value = false
  }
}

async function loadMappings() {
  try {
    mappings.value = await apiModule.get(props.api, '/missing/mappings')
  } catch (e) {
    mappings.value = []
  }
}

async function removeMapping(m) {
  try {
    await apiModule.del(props.api, '/missing/mappings/remove', { id: m.id })
    mappings.value = mappings.value.filter(x => x.id !== m.id)
    emit('notify', '已删除映射记录', 'success')
  } catch (e) {
    emit('notify', e.message || '删除失败')
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
  loadMappings()
  startPolling()
})
// keep-alive 缓存场景：切回时恢复轮询并重拉数据（Q1 修复；Q14 后切 Tab
// 不再由 Page 广播刷新键，各视图自查自刷）
onActivated(() => {
  loadSummary()
  loadUploads()
  loadMappings()
  startPolling()
})
// 切走（进入 keep-alive 缓存）时停止轮询，避免后台不可见视图持续打接口（Q1 修复）
onDeactivated(() => {
  stopPolling()
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
            <v-icon :size="16" :color="summary.hb_ok ? 'success' : 'error'" class="mr-1">
              {{ summary.hb_ok ? 'mdi-check-circle' : 'mdi-close-circle' }}
            </v-icon>
            子集化引擎：{{ summary.hb_ok ? 'HarfBuzz' : '未就绪' }}
          </span>
          <span class="mr-5">
            <v-icon :size="16" :color="summary.index_faces ? 'success' : 'warning'" class="mr-1">
              {{ summary.index_faces ? 'mdi-format-font' : 'mdi-alert' }}
            </v-icon>
            字体索引：{{ summary.index_faces || 0 }} faces
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
          上传即校验：字体名/别名必须命中缺失目标，且至少覆盖一个缺失字符；点击已上传字体可「改派」目标。
          归类时统一归档并自动重检受影响字幕。
        </v-alert>
        <div class="zt-uploads pa-3" v-if="uploads.length">
          <v-chip
            v-for="u in uploads"
            :key="u.path"
            size="small"
            variant="tonal"
            color="primary"
            class="mr-2 mb-2 zt-upload-chip"
            close
            :title="`${u.file_name} → ${u.matched || '?'}${u.covered_chars ? '（覆盖 ' + u.covered_chars + '）' : ''}；点击改派`"
            @click="openRemap(u)"
            @click:close="removeUpload(u.path)"
          >
            {{ u.file_name }}
            <span v-if="u.matched" class="zt-chip-target">→ {{ u.matched }}</span>
          </v-chip>
        </div>
        <div class="d-flex flex-wrap gap-2 align-center">
          <v-select
            v-model="targetHint"
            :items="targetOptions"
            item-title="title"
            item-value="name"
            label="目标缺失字体（可选）"
            density="compact"
            variant="outlined"
            hide-details
            :clearable="!!targetHint"
            no-data-text="暂无可选的缺失字体"
            class="zt-target-select"
          ></v-select>
          <v-btn
            color="primary"
            variant="tonal"
            :disabled="!enabled || uploading || classifying"
            :loading="uploading"
            title="上传字体（支持 ttf/otf/ttc/otc/woff/woff2 与 .zip/.7z/.rar 压缩包）"
            @click="uploadRef?.click()"
          >
            <v-icon start size="18">mdi-upload</v-icon>
            上传字体
          </v-btn>
          <input
            ref="uploadRef"
            type="file"
            accept=".ttf,.otf,.ttc,.otc,.woff,.woff2,.zip,.7z,.rar"
            multiple
            style="display: none"
            @change="handleUpload"
          />
          <v-btn
            color="success"
            variant="tonal"
            :disabled="!enabled || classifying || !uploads.length"
            :loading="classifying"
            title="全部上传字体入库 + 自动增量更新索引（运行中不可重复点击）"
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
                <v-list-item-subtitle class="zt-font-meta">
                  {{ f.count }} 个字幕缺失
                  <template v-if="f.chars"> · 缺 {{ f.codepoints_count || 0 }} 字符：<span class="zt-char-preview">{{ f.chars }}</span></template>
                  <template v-else-if="f.glyph"> · 字符级缺失</template>
                </v-list-item-subtitle>
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

    <v-card v-if="mappings.length" class="zt-card-bg mt-4">
      <v-card-title class="zt-card-title">
        <v-icon start size="18">mdi-link-variant</v-icon>
        人工映射审计（{{ mappings.length }}）
      </v-card-title>
      <v-card-text class="pt-0">
        <v-list density="compact" class="pa-0">
          <v-list-item v-for="m in mappings" :key="m.id">
            <v-list-item-title class="zt-font-meta">
              {{ m.source_name }} → {{ m.target_name }}
            </v-list-item-title>
            <v-list-item-subtitle class="zt-font-meta">
              {{ m.note || '人工映射' }} · {{ m.created_at }}
            </v-list-item-subtitle>
            <template #append>
              <v-btn
                icon="mdi-trash-can-outline"
                size="x-small"
                variant="text"
                color="error"
                title="删除该映射记录"
                @click="removeMapping(m)"
              ></v-btn>
            </template>
          </v-list-item>
        </v-list>
      </v-card-text>
    </v-card>

    <div class="zt-tip mt-3 text-body-2">
      提示：上传字体（支持 .zip/.7z/.rar）→ 校验通过后点「归类」入库 → 自动重检受影响字幕 → 回到「子集化」页重新运行。
    </div>

    <!-- 改派：给已上传字体人工指定缺失目标 -->
    <v-dialog v-model="remapDialog" max-width="460">
      <v-card class="zt-card-bg">
        <v-card-title class="zt-card-title">
          <v-icon start size="18">mdi-link-variant</v-icon>
          改派缺失目标
        </v-card-title>
        <v-card-text>
          <div class="text-body-2 mb-3">
            字体：{{ remapItem?.file_name }}
            <span v-if="remapItem?.name">（内部名：{{ remapItem.name }}）</span>
          </div>
          <div v-if="remapItem?.covered_chars" class="zt-font-meta mb-3">
            当前覆盖字符：{{ remapItem.covered_chars }}
          </div>
          <v-select
            v-model="remapTarget"
            :items="targetOptions"
            item-title="title"
            item-value="name"
            label="缺失目标字体"
            density="compact"
            variant="outlined"
            hide-details
            no-data-text="暂无可选的缺失字体"
          ></v-select>
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="remapDialog = false">取消</v-btn>
          <v-btn
            color="primary"
            variant="tonal"
            :loading="remapping"
            :disabled="!remapTarget"
            @click="submitRemap"
          >
            确认改派
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
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
.zt-target-select {
  min-width: 220px;
  max-width: 320px;
  flex: 0 1 280px;
}
/* 描边在暗色/手机上 0.38 透明度几乎看不见，单独提高本下拉的边框对比度。
   注意：构建时 postcss 会剔除选择器里含 “.v-” 的规则（Vuetify 样式由宿主提供），
   所以这里用属性选择器 [class*="v-field__outline"]，避免我们的覆盖被一起删掉。 */
.zt-target-select :deep([class*="v-field__outline"]) {
  --v-field-border-opacity: 0.9;
}
@media (max-width: 599.95px) {
  .zt-target-select {
    flex: 1 1 100%;
    min-width: 0;
    max-width: none;
  }
}
.zt-upload-chip {
  cursor: pointer;
}
.zt-chip-target {
  opacity: 0.75;
  margin-left: 4px;
}
.zt-char-preview {
  font-family: monospace;
  opacity: 0.9;
  word-break: break-all;
}
</style>