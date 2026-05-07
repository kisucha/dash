// main.js — Vue 앱 엔트리 포인트
// Pinia 스토어와 Vue Router를 앱에 등록하고 #app에 마운트한다
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import './style.css'
import App from './App.vue'
import router from './router/index.js'

const app = createApp(App)

// Pinia 전역 상태 관리 플러그인 등록
app.use(createPinia())

// Vue Router 플러그인 등록
app.use(router)

app.mount('#app')
