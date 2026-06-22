# Learning Guide: Build A Standalone Announcements App

This guide builds a small standalone app called `announcements`.

It is not part of MyThanzi. We are using the same architectural pattern so developers can learn the full flow clearly:

```text
Vue frontend
  -> API client
  -> Django REST API
  -> serializer
  -> model
  -> database
```

The app will let users:

- View published announcements.
- Create announcements.
- Store announcements in a database.

---

## 1. Final Project Shape

```text
announcements-project/
  backend/
    manage.py
    backend/
      settings.py
      urls.py
    announcements/
      admin.py
      apps.py
      models.py
      serializers.py
      views.py
      urls.py
      migrations/

  frontend/
    index.html
    package.json
    vite.config.js
    src/
      main.js
      App.vue
      api/
        client.js
      router/
        index.js
      views/
        AnnouncementsView.vue
```

The backend and frontend are separate projects. They communicate over HTTP.

---

## 2. Architecture Diagram

```text
Browser
  |
  | /announcements
  v
Vue Router
  |
  v
AnnouncementsView.vue
  |
  | listAnnouncements()
  v
frontend/src/api/client.js
  |
  | GET http://127.0.0.1:8000/api/announcements/
  v
Django URL Router
  |
  v
AnnouncementViewSet
  |
  v
AnnouncementSerializer
  |
  v
Announcement model
  |
  v
SQLite database
```

---

## 3. Request Flow

Read flow:

```text
User opens page
  -> Vue loads AnnouncementsView
  -> Vue calls listAnnouncements()
  -> fetch() sends GET request
  -> Django receives /api/announcements/
  -> ViewSet queries database
  -> Serializer converts rows to JSON
  -> Vue receives JSON
  -> Table/list renders
```

Write flow:

```text
User submits form
  -> Vue calls createAnnouncement(payload)
  -> fetch() sends POST request
  -> Django validates request data
  -> Serializer creates model object
  -> Database row is saved
  -> Vue reloads announcements
```

---

## 4. Tools Needed

Install:

- Python 3.11+
- Node.js 20+
- Git
- VS Code or another editor

Check versions:

```powershell
python --version
node --version
npm --version
git --version
```

---

## 5. Create The Project Folder

```powershell
mkdir announcements-project
cd announcements-project
mkdir backend
mkdir frontend
```

The root folder keeps backend and frontend side by side.

---

## 6. Backend: Create Virtual Environment

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install packages:

```powershell
pip install django djangorestframework django-cors-headers
```

Create `requirements.txt`:

```powershell
pip freeze > requirements.txt
```

---

## 7. Backend: Create Django Project

```powershell
django-admin startproject backend .
```

You should now have:

```text
backend/
  manage.py
  backend/
    __init__.py
    settings.py
    urls.py
    asgi.py
    wsgi.py
```

The outer `backend/` is the project folder. The inner `backend/` is the Django configuration package.

---

## 8. Backend: Create Announcements App

```powershell
python manage.py startapp announcements
```

This creates:

```text
announcements/
  __init__.py
  admin.py
  apps.py
  migrations/
    __init__.py
  models.py
  tests.py
  views.py
```

This Django app owns the announcement domain.

---

## 9. Backend: Configure Settings

File: `backend/backend/settings.py`

Add apps:

```py
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'rest_framework',
    'corsheaders',

    'announcements',
]
```

Add CORS middleware near the top:

```py
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
```

Allow the Vite dev server:

```py
CORS_ALLOWED_ORIGINS = [
    'http://127.0.0.1:5173',
    'http://localhost:5173',
]
```

---

## 10. Backend: Create The Model

File: `backend/announcements/models.py`

```py
from django.db import models


class Announcement(models.Model):
    title = models.CharField(max_length=120)
    body = models.TextField()
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title
```

The model defines the database table.

Database shape:

```text
announcements_announcement
  id
  title
  body
  is_published
  created_at
  updated_at
```

---

## 11. Backend: Run Migrations

```powershell
python manage.py makemigrations
python manage.py migrate
```

Flow:

```text
models.py
  -> migration file
  -> database table
```

Create an admin user:

```powershell
python manage.py createsuperuser
```

---

## 12. Backend: Register Admin

File: `backend/announcements/admin.py`

```py
from django.contrib import admin

from .models import Announcement


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ('title', 'is_published', 'created_at')
    list_filter = ('is_published', 'created_at')
    search_fields = ('title', 'body')
```

Admin lets us create test announcements at:

```text
http://127.0.0.1:8000/admin/
```

---

## 13. Backend: Create Serializer

File: `backend/announcements/serializers.py`

```py
from rest_framework import serializers

from .models import Announcement


class AnnouncementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Announcement
        fields = [
            'id',
            'title',
            'body',
            'is_published',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']

    def validate_title(self, value):
        value = value.strip()
        if len(value) < 5:
            raise serializers.ValidationError('Title must be at least 5 characters.')
        return value
```

Serializer job:

```text
Model object <-> JSON
```

---

## 14. Backend: Create ViewSet

File: `backend/announcements/views.py`

```py
from rest_framework import viewsets

from .models import Announcement
from .serializers import AnnouncementSerializer


class AnnouncementViewSet(viewsets.ModelViewSet):
    serializer_class = AnnouncementSerializer

    def get_queryset(self):
        queryset = Announcement.objects.all()

        published = self.request.query_params.get('published')
        if published == 'true':
            queryset = queryset.filter(is_published=True)
        elif published == 'false':
            queryset = queryset.filter(is_published=False)

        return queryset
```

ViewSet job:

- Receive API requests.
- Query the database.
- Choose the serializer.
- Return responses.

---

## 15. Backend: Create App URLs

File: `backend/announcements/urls.py`

```py
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AnnouncementViewSet


router = DefaultRouter()
router.register('announcements', AnnouncementViewSet, basename='announcements')

urlpatterns = [
    path('', include(router.urls)),
]
```

This creates:

```text
GET    /api/announcements/
POST   /api/announcements/
GET    /api/announcements/{id}/
PUT    /api/announcements/{id}/
PATCH  /api/announcements/{id}/
DELETE /api/announcements/{id}/
```

---

## 16. Backend: Connect Root URLs

File: `backend/backend/urls.py`

```py
from django.contrib import admin
from django.urls import include, path


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('announcements.urls')),
]
```

URL flow:

```text
/api/announcements/
  -> backend/urls.py
  -> announcements/urls.py
  -> AnnouncementViewSet
```

---

## 17. Backend: Run Server

```powershell
python manage.py runserver
```

Open:

```text
http://127.0.0.1:8000/api/announcements/
```

Expected response:

```json
[]
```

Create a test item in Django admin, then refresh the API page.

---

## 18. Backend API Test With PowerShell

Create announcement:

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/announcements/ `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"title":"First announcement","body":"Welcome to the standalone app.","is_published":true}'
```

List announcements:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/announcements/
```

Filter published:

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/api/announcements/?published=true"
```

---

## 19. Frontend: Create Vue App

Open a new terminal:

```powershell
cd announcements-project\frontend
npm create vite@latest . -- --template vue
npm install
npm install vue-router
```

Start it:

```powershell
npm run dev
```

Vite should run at:

```text
http://127.0.0.1:5173/
```

---

## 20. Frontend: API Client

Create folder:

```text
frontend/src/api/
```

File: `frontend/src/api/client.js`

```js
const API_ROOT = 'http://127.0.0.1:8000/api'

async function apiFetch(path, options = {}) {
  const headers = new Headers(options.headers || {})

  if (options.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(`${API_ROOT}${path}`, {
    ...options,
    headers
  })

  const data = await response.json().catch(() => null)

  if (!response.ok) {
    const message = data?.detail || JSON.stringify(data) || 'Request failed.'
    throw new Error(message)
  }

  return data
}

export function listAnnouncements(params = {}) {
  const query = new URLSearchParams(params)
  return apiFetch(`/announcements/${query.toString() ? `?${query}` : ''}`)
}

export function createAnnouncement(payload) {
  return apiFetch('/announcements/', {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}

export function updateAnnouncement(id, payload) {
  return apiFetch(`/announcements/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(payload)
  })
}

export function deleteAnnouncement(id) {
  return apiFetch(`/announcements/${id}/`, {
    method: 'DELETE'
  })
}
```

API client job:

- Know the backend base URL.
- Wrap `fetch`.
- Convert JSON responses.
- Give Vue simple functions.

---

## 21. Frontend: Router

Create folder:

```text
frontend/src/router/
```

File: `frontend/src/router/index.js`

```js
import { createRouter, createWebHistory } from 'vue-router'

import AnnouncementsView from '@/views/AnnouncementsView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/announcements' },
    { path: '/announcements', name: 'announcements', component: AnnouncementsView }
  ]
})

export default router
```

Router job:

```text
URL path -> Vue screen
```

---

## 22. Frontend: Main Entry

File: `frontend/src/main.js`

```js
import { createApp } from 'vue'

import App from './App.vue'
import router from './router'
import './style.css'

createApp(App).use(router).mount('#app')
```

This mounts Vue and installs the router.

---

## 23. Frontend: App Shell

File: `frontend/src/App.vue`

```vue
<template>
  <main class="app-shell">
    <header class="topbar">
      <div>
        <p class="eyebrow">Standalone Learning App</p>
        <h1>Announcements</h1>
      </div>
      <RouterLink to="/announcements">Announcements</RouterLink>
    </header>

    <RouterView />
  </main>
</template>
```

The shell stays small. The feature screen lives in `AnnouncementsView.vue`.

---

## 24. Frontend: Announcements View

Create folder:

```text
frontend/src/views/
```

File: `frontend/src/views/AnnouncementsView.vue`

```vue
<script setup>
import { onMounted, ref } from 'vue'

import {
  createAnnouncement,
  deleteAnnouncement,
  listAnnouncements,
  updateAnnouncement
} from '@/api/client'

const announcements = ref([])
const title = ref('')
const body = ref('')
const isPublished = ref(true)
const filter = ref('all')
const error = ref('')
const loading = ref(false)
const saving = ref(false)

async function loadAnnouncements() {
  loading.value = true
  error.value = ''

  try {
    const params = {}
    if (filter.value === 'published') params.published = 'true'
    if (filter.value === 'drafts') params.published = 'false'

    announcements.value = await listAnnouncements(params)
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}

async function submitAnnouncement() {
  saving.value = true
  error.value = ''

  try {
    await createAnnouncement({
      title: title.value,
      body: body.value,
      is_published: isPublished.value
    })

    title.value = ''
    body.value = ''
    isPublished.value = true
    await loadAnnouncements()
  } catch (err) {
    error.value = err.message
  } finally {
    saving.value = false
  }
}

async function togglePublished(announcement) {
  await updateAnnouncement(announcement.id, {
    is_published: !announcement.is_published
  })
  await loadAnnouncements()
}

async function removeAnnouncement(announcement) {
  await deleteAnnouncement(announcement.id)
  await loadAnnouncements()
}

onMounted(loadAnnouncements)
</script>

<template>
  <section class="workspace">
    <form class="panel" @submit.prevent="submitAnnouncement">
      <h2>Create announcement</h2>

      <label>
        Title
        <input v-model="title" type="text" required>
      </label>

      <label>
        Body
        <textarea v-model="body" rows="4" required></textarea>
      </label>

      <label class="inline">
        <input v-model="isPublished" type="checkbox">
        Published
      </label>

      <button type="submit" :disabled="saving">
        {{ saving ? 'Saving...' : 'Create' }}
      </button>
    </form>

    <section class="panel">
      <div class="list-header">
        <h2>Announcement list</h2>
        <select v-model="filter" @change="loadAnnouncements">
          <option value="all">All</option>
          <option value="published">Published</option>
          <option value="drafts">Drafts</option>
        </select>
      </div>

      <p v-if="error" class="error">{{ error }}</p>
      <p v-if="loading">Loading announcements...</p>

      <article
        v-for="announcement in announcements"
        :key="announcement.id"
        class="announcement"
      >
        <div>
          <h3>{{ announcement.title }}</h3>
          <p>{{ announcement.body }}</p>
          <span>{{ announcement.is_published ? 'Published' : 'Draft' }}</span>
        </div>

        <div class="actions">
          <button type="button" @click="togglePublished(announcement)">
            {{ announcement.is_published ? 'Unpublish' : 'Publish' }}
          </button>
          <button type="button" class="danger" @click="removeAnnouncement(announcement)">
            Delete
          </button>
        </div>
      </article>
    </section>
  </section>
</template>
```

This file demonstrates the full frontend flow:

- Load records.
- Create records.
- Update records.
- Delete records.
- Render API data.

---

## 25. Frontend: Basic Styles

File: `frontend/src/style.css`

```css
* {
  box-sizing: border-box;
}

body {
  margin: 0;
  color: #172026;
  background: #f5f7f8;
  font-family: Arial, sans-serif;
}

button,
input,
select,
textarea {
  font: inherit;
}

button {
  border: 0;
  border-radius: 6px;
  padding: 10px 14px;
  color: white;
  background: #126b5f;
  cursor: pointer;
}

button:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.danger {
  background: #a83232;
}

.app-shell {
  width: min(1100px, calc(100% - 32px));
  margin: 0 auto;
  padding: 24px 0;
}

.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 24px;
}

.topbar h1,
.topbar p {
  margin: 0;
}

.eyebrow {
  color: #61717a;
  font-size: 0.85rem;
}

.workspace {
  display: grid;
  grid-template-columns: 360px 1fr;
  gap: 20px;
}

.panel {
  border: 1px solid #d9e1e4;
  border-radius: 8px;
  padding: 18px;
  background: white;
}

.panel h2 {
  margin-top: 0;
}

label {
  display: grid;
  gap: 6px;
  margin-bottom: 14px;
}

.inline {
  display: flex;
  align-items: center;
}

input,
select,
textarea {
  width: 100%;
  border: 1px solid #c7d0d5;
  border-radius: 6px;
  padding: 10px;
}

.list-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.announcement {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  border-top: 1px solid #e1e7ea;
  padding: 16px 0;
}

.announcement h3 {
  margin: 0 0 8px;
}

.announcement p {
  margin: 0 0 10px;
}

.announcement span {
  color: #61717a;
  font-size: 0.9rem;
}

.actions {
  display: flex;
  align-items: start;
  gap: 8px;
}

.error {
  color: #a83232;
}

@media (max-width: 760px) {
  .workspace {
    grid-template-columns: 1fr;
  }

  .announcement,
  .topbar {
    align-items: stretch;
    flex-direction: column;
  }
}
```

---

## 26. Run The Full App

Terminal 1:

```powershell
cd announcements-project\backend
.\.venv\Scripts\Activate.ps1
python manage.py runserver
```

Terminal 2:

```powershell
cd announcements-project\frontend
npm run dev
```

Open:

```text
http://127.0.0.1:5173/announcements
```

---

## 27. Full Flow Recap

```text
Create button clicked
  |
  v
submitAnnouncement()
  |
  v
createAnnouncement(payload)
  |
  v
POST /api/announcements/
  |
  v
AnnouncementViewSet
  |
  v
AnnouncementSerializer
  |
  v
Announcement.objects.create(...)
  |
  v
SQLite row
  |
  v
JSON response
  |
  v
loadAnnouncements()
  |
  v
Updated Vue list
```

That is the complete frontend-to-database pipeline.

---

## 28. Debugging Checklist

If the frontend shows an error:

```text
1. Is Django running on port 8000?
2. Is Vite running on port 5173?
3. Does /api/announcements/ work in the browser?
4. Does the Network tab show a CORS error?
5. Is corsheaders installed and registered?
6. Is the endpoint registered in backend/urls.py?
7. Is the ViewSet registered in announcements/urls.py?
8. Did migrations run?
9. Does the serializer expose the field Vue expects?
```

If the API returns an empty list:

```text
1. Is there data in Django admin?
2. Are you filtering by published=true?
3. Is is_published set correctly?
```

---

## 29. Common Mistakes

Mistake:

```text
ModuleNotFoundError: No module named 'rest_framework'
```

Fix:

```powershell
pip install djangorestframework
```

Mistake:

```text
no such table: announcements_announcement
```

Fix:

```powershell
python manage.py makemigrations
python manage.py migrate
```

Mistake:

```text
CORS error in browser console
```

Fix:

```py
INSTALLED_APPS = [
    'corsheaders',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
]

CORS_ALLOWED_ORIGINS = [
    'http://127.0.0.1:5173',
    'http://localhost:5173',
]
```

---

## 30. Final Mental Model

```text
Model
  database shape

Serializer
  JSON contract

ViewSet
  request handling and database query

URL router
  endpoint mapping

API client
  frontend HTTP helper

Vue view
  user interface
```

Build in this order:

```text
model -> serializer -> viewset -> urls -> api client -> Vue view
```

Debug in this order:

```text
browser -> API client -> URL route -> viewset -> serializer -> model -> database
```
