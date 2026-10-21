const { configure } = require('quasar/wrappers')

module.exports = configure(function (/* ctx */) {
  return {
    eslint: {
      warnings: true,
      errors: true
    },

    boot: [
      'axios'
    ],

    css: [
      'app.scss'
    ],

    extras: [
      'roboto-font',
      'material-icons'
    ],

    build: {
      vueRouterMode: 'history',
      target: {
        browser: ['es2019', 'edge88', 'firefox78', 'chrome87', 'safari13.1'],
        node: 'node16'
      },
      vitePlugins: []
    },

    devServer: {
      server: {
        type: 'http'
      },
      port: 5434,
      open: true,
      proxy: {
        '/api': {
          target: process.env.API_PROXY_TARGET || 'http://127.0.0.1:5432',
          changeOrigin: true
        }
      }
    },

    framework: {
      config: {},
      plugins: [
        'Notify',
        'Loading'
      ]
    },

    animations: [],

    ssr: {
      pwa: false,
      prodPort: 3000
    },

    pwa: {
      workboxPluginMode: 'InjectManifest',
      workboxOptions: {},
      chainWebpackCustomSW (chain) {
        chain.plugin('eslint-webpack-plugin')
          .use(require('eslint-webpack-plugin'), [{ extensions: ['js'] }])
      },
      manifest: {
        name: '小恐龍2.0',
        short_name: '小恐龍2.0',
        description: 'Network Configuration Analysis Portal',
        display: 'standalone',
        orientation: 'portrait',
        background_color: '#ffffff',
        theme_color: '#027be3',
        icons: [
          {
            src: 'icons/icon-128x128.png',
            sizes: '128x128',
            type: 'image/png'
          },
          {
            src: 'icons/icon-192x192.png',
            sizes: '192x192',
            type: 'image/png'
          },
          {
            src: 'icons/icon-256x256.png',
            sizes: '256x256',
            type: 'image/png'
          },
          {
            src: 'icons/icon-384x384.png',
            sizes: '384x384',
            type: 'image/png'
          },
          {
            src: 'icons/icon-512x512.png',
            sizes: '512x512',
            type: 'image/png'
          }
        ]
      }
    },

    cordova: {},
    capacitor: {
      hideSplashscreen: true
    },
    electron: {
      bundler: 'packager',
      packager: {},
      builder: {
        appId: 'network-config-portal'
      }
    },
    bex: {
      contentScripts: [
        'my-content-script'
      ]
    }
  }
})