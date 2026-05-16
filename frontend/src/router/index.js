// router/index.js — Vue Router 라우트 정의 및 라우터 인스턴스 생성
// DashboardView, FeatureView, TaskDetailView, ScheduleView, F001~F005 View 11개 페이지를 등록한다
import { createRouter, createWebHistory } from 'vue-router'
import DashboardView from '../views/DashboardView.vue'
import FeatureView from '../views/FeatureView.vue'
import TaskDetailView from '../views/TaskDetailView.vue'
import ScheduleView from '../views/ScheduleView.vue'
import F001View from '../views/F001View.vue'
import F001JobDetailView from '../views/F001JobDetailView.vue'
import F003View from '../views/F003View.vue'
import F004View from '../views/F004View.vue'
import F004JobDetailView from '../views/F004JobDetailView.vue'
import F005View from '../views/F005View.vue'
import F005JobDetailView from '../views/F005JobDetailView.vue'

// 라우트 목록 — 각 경로와 컴포넌트를 매핑
// 중요: /features/F001, /features/F003~F005 는 /features/:id 보다 앞에 등록해야 우선 매칭된다
const routes = [
  {
    path: '/',
    name: 'Dashboard',
    component: DashboardView,
  },
  {
    path: '/features/F001',
    name: 'F001Feature',
    component: F001View,
  },
  {
    path: '/f001/jobs/:jobId',
    name: 'F001JobDetail',
    component: F001JobDetailView,
  },
  {
    path: '/features/F003',
    name: 'F003Feature',
    component: F003View,
  },
  {
    path: '/features/F004',
    name: 'F004Feature',
    component: F004View,
  },
  {
    path: '/f004/jobs/:jobId',
    name: 'F004JobDetail',
    component: F004JobDetailView,
  },
  {
    path: '/features/F005',
    name: 'F005Feature',
    component: F005View,
  },
  {
    path: '/f005/jobs/:jobId',
    name: 'F005JobDetail',
    component: F005JobDetailView,
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
