import { createApp } from 'vue'
import AppPage from './AppPage.vue'

// 仅用于本地构建/调试；宿主通过联邦远程入口加载 Page / AppPage / Config
createApp(AppPage).mount('#app')
