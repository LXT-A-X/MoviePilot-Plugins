import { reactive } from 'vue'

export function useConfirm() {
  const cState = reactive({
    open: false, title: '', text: '', detail: '',
    okText: '确认', color: 'warning', _resolve: null,
  })

  function askConfirm(opts = {}) {
    return new Promise((resolve) => {
      cState.open = true
      cState.title = opts.title || '请确认'
      cState.text = opts.text || ''
      cState.detail = opts.detail || ''
      cState.okText = opts.okText || '确认'
      cState.color = opts.color || 'warning'
      cState._resolve = resolve
    })
  }

  function _finish(v) {
    cState.open = false
    const r = cState._resolve
    cState._resolve = null
    if (r) r(v)
  }

  return { cState, askConfirm, cOk: () => _finish(true), cCancel: () => _finish(false) }
}