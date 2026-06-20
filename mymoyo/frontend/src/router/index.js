import { createRouter, createWebHistory } from 'vue-router'

import AppointmentsView from '@/views/AppointmentsView.vue'
import DashboardView from '@/views/DashboardView.vue'
import FacilitiesView from '@/views/FacilitiesView.vue'
import HomeView from '@/views/HomeView.vue'
import LoginView from '@/views/LoginView.vue'
import LocationsManageView from '@/views/LocationsManageView.vue'
import ProfileView from '@/views/ProfileView.vue'
import UsersManageView from '@/views/UsersManageView.vue'

const router = createRouter({
  history: createWebHistory('/app/'),
  routes: [
    { path: '/', name: 'home', component: HomeView },
    { path: '/dashboard', name: 'dashboard', component: DashboardView },
    { path: '/appointments', name: 'appointments', component: AppointmentsView },
    { path: '/facilities', name: 'facilities', component: FacilitiesView },
    { path: '/locations', name: 'locations', component: LocationsManageView },
    { path: '/users', name: 'users', component: UsersManageView },
    { path: '/login', name: 'login', component: LoginView },
    { path: '/profile', name: 'profile', component: ProfileView }
  ]
})

export default router
