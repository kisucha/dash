// router/index.js — Vue Router 라우트 정의 및 라우터 인스턴스 생성
// DashboardView, FeatureView, TaskDetailView, ScheduleView 4개 페이지를 등록한다
import { createRouter, createWebHistory } from 'vue-router'
import DashboardView from '../views/DashboardView.vue'
import FeatureView from '../views/FeatureView.vue'
import TaskDetailView from '../views/TaskDetailView.vue'
import ScheduleView from '../views/ScheduleView.vue'

// 라우트 목록 — 각 경로와 컴포넌트를 매핑
const routes = [
  {
    path: '/',
    name: 'Dashboard',
    component: DashboardView,
  },
  {
    path: '/features/:id',
    name: 'Feature',
    component: FeatureView,
  },
  {
    path: '/tasks/:id',
    name: 'TaskDetail',
    component: TaskDetailView,
  },
  {
    path: '/schedules',
    name: 'Schedules',
    component: ScheduleView,
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
