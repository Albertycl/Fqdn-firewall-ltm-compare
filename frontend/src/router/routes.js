const routes = [
  {
    path: '/',
    component: () => import('layouts/MainLayout.vue'),
    children: [
      { path: '', component: () => import('pages/SearchPage.vue') },
      { path: '/history', component: () => import('pages/HistoryPage.vue') },
      { path: '/update-history', component: () => import('pages/UpdateHistoryPage.vue') }
    ]
  },

  // Always leave this as last one,
  // but you can also remove it
  {
    path: '/:catchAll(.*)*',
    component: () => import('pages/ErrorNotFound.vue')
  }
]

export default routes