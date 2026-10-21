import { boot } from 'quasar/wrappers'
import axios from 'axios'

// Set base URL for all API calls - use proxy in development
const api = axios.create({ 
  // Relative in both modes: dev goes through the quasar proxy, production
  // through the nginx /api/ location. No host is baked into the bundle.
  baseURL: process.env.API_BASE_URL || '/api',
  timeout: 90000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// Add response interceptor for debugging
api.interceptors.response.use(
  response => {
    return response
  },
  error => {
    console.error('API Error:', error.response?.data || error.message)
    return Promise.reject(error)
  }
)

export default boot(({ app }) => {
  app.config.globalProperties.$axios = axios
  app.config.globalProperties.$api = api
})

export { api }