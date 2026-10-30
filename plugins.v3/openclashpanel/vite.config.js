import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import federation from '@originjs/vite-plugin-federation'
import { rmSync } from 'node:fs'

// 联邦产物里不允许出现 Vuetify / MDI 的全局样式（宿主已有）
function removeUnreachableSharedAssets() {
  return {
    name: 'remove-unreachable-shared-assets',
    closeBundle() {
      for (const dir of ['./dist/assets/__federation_shared_vuetify', './dist/assets/__federation_shared_vuetify']) {
        rmSync(new URL(dir, import.meta.url), { recursive: true, force: true })
      }
    },
  }
}

export default defineConfig({
  plugins: [
    vue(),
    federation({
      name: 'OpenClashPanel',
      filename: 'remoteEntry.js',
      exposes: {
        './AppPage': './src/AppPage.vue',
        './Page': './src/Page.vue',
        './Config': './src/Config.vue',
        './Dashboard': './src/Dashboard.vue',
      },
      shared: {
        vue: { requiredVersion: false, generate: false, singleton: true },
        vuetify: { requiredVersion: false, generate: false, singleton: true },
        'vuetify/styles': { requiredVersion: false, generate: false, singleton: true },
      },
      format: 'esm',
    }),
    removeUnreachableSharedAssets(),
  ],
  build: {
    target: 'esnext',
    minify: false,
    cssCodeSplit: true,
  },
  css: {
    postcss: {
      plugins: [
        {
          postcssPlugin: 'internal:charset-removal',
          AtRule: {
            charset: atRule => atRule.remove(),
          },
        },
        {
          postcssPlugin: 'vuetify-filter',
          Root(root) {
            const sourcePath = (root.source?.input?.file || '').replaceAll('\\', '/')
            if (sourcePath.includes('/node_modules/vuetify/') || sourcePath.includes('/node_modules/@mdi/')) {
              root.nodes = []
              return
            }
            root.walkRules(rule => {
              if (rule.selector && (rule.selector.includes('.v-') || rule.selector.includes('.mdi-'))) {
                rule.remove()
              }
            })
          },
        },
      ],
    },
  },
  server: {
    port: 5003,
    cors: true,
  },
})
