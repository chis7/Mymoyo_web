import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  base: '/static/vue/',
  plugins: [
    vue(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['icons/icon.svg', 'icons/maskable-icon.svg'],
      manifest: {
        name: 'MyMoyo',
        short_name: 'MyMoyo',
        description: 'Offline-capable MyMoyo portal',
        theme_color: '#087568',
        background_color: '#f6fbf8',
        display: 'standalone',
        scope: '/app/',
        start_url: '/app/',
        icons: [
          {
            src: '/static/vue/icons/icon.svg',
            sizes: 'any',
            type: 'image/svg+xml'
          },
          {
            src: '/static/vue/icons/maskable-icon.svg',
            sizes: 'any',
            type: 'image/svg+xml',
            purpose: 'maskable'
          }
        ]
      },
      workbox: {
        navigateFallback: '/app/',
        navigateFallbackDenylist: [/^\/api\//, /^\/admin\//],
        runtimeCaching: [
          {
            urlPattern: ({ url }) => url.pathname.startsWith('/api/app/') || url.pathname.startsWith('/api/dashboard/') || url.pathname.startsWith('/api/facilities') || url.pathname.startsWith('/api/provinces') || url.pathname.startsWith('/api/districts') || url.pathname.startsWith('/api/users') || url.pathname.startsWith('/api/appointments'),
            handler: 'NetworkFirst',
            options: {
              cacheName: 'mymoyo-api-cache',
              expiration: {
                maxEntries: 80,
                maxAgeSeconds: 60 * 60 * 24
              },
              networkTimeoutSeconds: 5
            }
          }
        ]
      }
    })
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  build: {
    outDir: '../static/vue',
    emptyOutDir: true
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8000'
    }
  }
})
