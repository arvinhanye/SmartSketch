import { createPinia } from 'pinia'
import { createApp } from 'vue'
import { createWebHistory } from 'vue-router'
import App from './App.vue'
import { createAppRouter } from './router'

// 登录页与会话存储由 H13 接入；在此之前一律视为未登录
const router = createAppRouter({ history: createWebHistory(), getAccountRole: () => null })

createApp(App).use(createPinia()).use(router).mount('#app')
