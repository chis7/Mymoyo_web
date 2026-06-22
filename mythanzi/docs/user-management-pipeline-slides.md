# User Management Pipeline: Frontend to Database

Slide deck for bringing developers up to speed on one vertical slice of MyThanzi: the user management app.

Use this deck to explain how a user search in the Vue PWA becomes a database query, how the response is shaped, and where create/edit flows currently move through Django server-rendered pages.

---

## 1. Goal Of This Session

By the end, everyone should understand:

- Where the User Management screen lives in the frontend.
- Which API endpoint it calls.
- How Django REST Framework routes the request.
- How permissions protect the endpoint.
- How `User` and `UserProfile` are queried from the database.
- How data is serialized back to Vue.
- Where create/edit/detail flows currently live.

---

## 2. The One Pipeline We Are Following

```text
Browser
  -> Vue route: /app/users
  -> UsersManageView.vue
  -> listUsers()
  -> apiFetch('/users/')
  -> Django route: /api/users/
  -> UserViewSet
  -> UserSerializer
  -> auth.User + users.UserProfile
  -> JSON response
  -> Vue table render
```

This is a read pipeline: the PWA searches and reviews users.

---

## 3. Key Files

```text
frontend/src/router/index.js
frontend/src/views/UsersManageView.vue
frontend/src/api/client.js

api/urls.py
api/views.py
api/serializers.py
api/permissions.py

users/models.py
users/urls.py
users/views.py
```

Mental model:

- `frontend/` asks for user data.
- `api/` exposes JSON endpoints.
- `users/` owns the user domain and database models.

---

## 4. Frontend Entry Point: Vue Router

File: `frontend/src/router/index.js`

```js
import UsersManageView from '@/views/UsersManageView.vue'

const router = createRouter({
  history: createWebHistory('/app/'),
  routes: [
    { path: '/users', name: 'users', component: UsersManageView }
  ]
})
```

When the browser opens:

```text
/app/users
```

Vue loads:

```text
UsersManageView.vue
```

---

## 5. User Management Screen

File: `frontend/src/views/UsersManageView.vue`

```js
import { onMounted, ref, watch } from 'vue'
import { listUsers } from '@/api/client'

const users = ref([])
const query = ref('')
const error = ref('')
const loading = ref(false)
```

This component owns the screen state:

- `users`: rows displayed in the table.
- `query`: search input.
- `loading`: loading indicator.
- `error`: request failure message.

---

## 6. Loading Users From The API

File: `frontend/src/views/UsersManageView.vue`

```js
async function loadUsers() {
  loading.value = true
  error.value = ''
  try {
    const data = await listUsers(query.value ? { q: query.value } : {})
    users.value = data.results || data
  } catch (err) {
    error.value = navigator.onLine
      ? err.message
      : 'Cached user data will appear after an online visit.'
  } finally {
    loading.value = false
  }
}

watch(query, loadUsers)
onMounted(loadUsers)
```

What this means:

- On page load, fetch users.
- On every search text change, fetch users again.
- Support either paginated data with `results` or plain list data.

---

## 7. Rendering The User Table

File: `frontend/src/views/UsersManageView.vue`

```vue
<tr v-for="user in users" :key="user.id">
  <td>{{ user.display_name }}</td>
  <td>{{ user.username }}</td>
  <td>{{ user.email || '-' }}</td>
  <td>{{ user.profile?.role_display || '-' }}</td>
  <td>
    {{ user.profile?.is_active === false || user.is_active === false
      ? 'Inactive'
      : 'Active' }}
  </td>
</tr>
```

Notice that the frontend expects nested profile data:

```text
user.profile.role_display
user.profile.is_active
```

That nested shape comes from the API serializer.

---

## 8. Frontend API Helper

File: `frontend/src/api/client.js`

```js
export function listUsers(params = {}) {
  const query = new URLSearchParams(params)
  return apiFetch(`/users/${query.toString() ? `?${query}` : ''}`)
}
```

Examples:

```js
listUsers()
// GET /api/users/

listUsers({ q: 'mary' })
// GET /api/users/?q=mary
```

The frontend does not know about Django models. It only knows API paths and JSON.

---

## 9. Shared API Wrapper

File: `frontend/src/api/client.js`

```js
const API_ROOT = '/api'

export async function apiFetch(path, options = {}) {
  const response = await fetch(`${API_ROOT}${path}`, {
    credentials: 'include',
    ...fetchOptions,
    headers
  })

  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(data.detail || data.error || 'Request failed.')
  }
  return data
}
```

Responsibilities:

- Prefix every request with `/api`.
- Send browser session cookies with `credentials: 'include'`.
- Decode JSON.
- Convert API errors into JavaScript errors.

---

## 10. Backend Root Routing

File: `mythanzi/urls.py`

```py
urlpatterns = [
    path('api/', include('api.urls')),
    path('app/', vue_frontend, name='vue_frontend'),
    re_path(r'^app/(?P<path>.*)$', vue_frontend, name='vue_frontend_fallback'),
    path('users/', include('users.urls')),
]
```

There are two user-related route families:

- `/api/users/`: JSON API for the Vue PWA.
- `/users/...`: Django-rendered pages for detail, edit, create, delete.

---

## 11. API Router

File: `api/urls.py`

```py
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register('users', UserViewSet, basename='api-users')

urlpatterns = [
    path('', include(router.urls)),
]
```

DRF router creates these routes:

```text
GET /api/users/
GET /api/users/{id}/
```

Because this is a `ReadOnlyModelViewSet`, the API supports reading but not creating/updating users.

---

## 12. Permission Gate

File: `api/views.py`

```py
class UserViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [CanManageUsers]
    serializer_class = UserSerializer
```

File: `api/permissions.py`

```py
class CanManageUsers(IsActivePortalUser):
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        return (
            request.user.is_superuser
            or get_user_role(request.user) in USER_ADMIN_ROLES
        )
```

Only active portal users with user-management roles can access the endpoint.

---

## 13. Querying The Database

File: `api/views.py`

```py
class UserViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [CanManageUsers]
    serializer_class = UserSerializer

    def get_queryset(self):
        queryset = User.objects.select_related('profile').order_by('username')
        search_term = self.request.query_params.get('q', '').strip()
        if search_term:
            queryset = queryset.filter(
                Q(username__icontains=search_term)
                | Q(first_name__icontains=search_term)
                | Q(last_name__icontains=search_term)
                | Q(email__icontains=search_term)
                | Q(profile__reference_number__icontains=search_term)
            )
        return queryset
```

Important details:

- Base table: Django `auth_user`.
- Related table: `users_userprofile`.
- `select_related('profile')` avoids extra queries per row.
- Search checks user fields and profile reference number.

---

## 14. Database Models

File: `users/models.py`

```py
class UserProfile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile'
    )
    facility = models.ForeignKey(
        'locations.Facility',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='workers',
    )
    reference_number = models.CharField(max_length=20, unique=True, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='client')
    phone = models.CharField(max_length=20, blank=True, null=True)
    is_active = models.BooleanField(default=True)
```

The user app extends Django’s built-in `User` instead of replacing it.

---

## 15. User To Profile Relationship

```text
auth.User
  id
  username
  first_name
  last_name
  email
  is_active

users.UserProfile
  user_id
  role
  phone
  facility_id
  reference_number
  is_active
```

Relationship:

```text
User 1 -> 1 UserProfile
```

Code access pattern:

```py
user.profile.role
user.profile.reference_number
```

---

## 16. Automatic Profile Creation

File: `users/models.py`

```py
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    profile, _ = UserProfile.objects.get_or_create(user=instance)
    profile.save()
```

Why this matters:

- New users automatically get profiles.
- API code can safely expect `user.profile`.
- Legacy/missing profiles are healed with `get_or_create`.

---

## 17. Active Status Sync

File: `users/models.py`

```py
@receiver(post_save, sender=UserProfile)
def sync_user_active_status(sender, instance, **kwargs):
    if instance.user.is_active != instance.is_active:
        instance.user.is_active = instance.is_active
        instance.user.save(update_fields=['is_active'])
```

There are two active-status fields:

- `User.is_active`: Django authentication status.
- `UserProfile.is_active`: portal profile status.

The signal keeps them aligned.

---

## 18. Serializing User Data

File: `api/serializers.py`

```py
class UserSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer(read_only=True)
    display_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'first_name',
            'last_name',
            'display_name',
            'email',
            'is_staff',
            'is_superuser',
            'is_active',
            'profile',
        ]
```

This is the contract between backend and frontend.

---

## 19. Serializing Profile Data

File: `api/serializers.py`

```py
class UserProfileSerializer(serializers.ModelSerializer):
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    responsibilities = serializers.SerializerMethodField()
    facility_name = serializers.CharField(source='facility.name', read_only=True)

    class Meta:
        model = UserProfile
        fields = [
            'role',
            'role_display',
            'facility',
            'facility_name',
            'responsibilities',
            'phone',
            'date_of_birth',
            'theme_color',
            'is_active',
            'must_change_password',
        ]
```

The serializer adds friendly display fields so Vue does not have to understand Django choices.

---

## 20. Example JSON Response

```json
{
  "id": 7,
  "username": "maria",
  "first_name": "Maria",
  "last_name": "Banda",
  "display_name": "Maria Banda",
  "email": "maria@example.com",
  "is_staff": false,
  "is_superuser": false,
  "is_active": true,
  "profile": {
    "role": "client",
    "role_display": "Client",
    "facility": 3,
    "facility_name": "Kalingalinga Clinic",
    "phone": "0970000000",
    "theme_color": "teal",
    "is_active": true,
    "must_change_password": false
  }
}
```

This is what the Vue table consumes.

---

## 21. Full Read Request Timeline

```text
1. Admin opens /app/users
2. Vue Router renders UsersManageView
3. onMounted() calls loadUsers()
4. loadUsers() calls listUsers()
5. listUsers() calls apiFetch('/users/')
6. Browser sends GET /api/users/
7. Django routes to api.urls
8. DRF router calls UserViewSet.list()
9. CanManageUsers checks the logged-in user
10. get_queryset() queries User + UserProfile
11. UserSerializer shapes JSON
12. Vue stores data in users.value
13. Template renders table rows
```

This is the core mental model.

---

## 22. Search Timeline

```text
User types "mary"
  -> query changes
  -> watch(query, loadUsers)
  -> GET /api/users/?q=mary
  -> get_queryset() reads query_params['q']
  -> database filter uses icontains
  -> filtered JSON returns
  -> table updates
```

Search fields:

- Username
- First name
- Last name
- Email
- Profile reference number

---

## 23. Why `select_related` Matters

Without `select_related('profile')`:

```text
1 query for users
+ 1 query per user profile
```

With `select_related('profile')`:

```text
1 joined query for users and profiles
```

In user management screens, this prevents slow table rendering as the user count grows.

---

## 24. Current Create/Edit Flow

The Vue user screen links to Django-rendered pages:

```vue
<a :href="`/users/${user.id}/`">View</a>
<a :href="`/users/${user.id}/edit/`">Edit</a>
```

Backend route file:

```py
path('create/', views.user_create, name='user_create'),
path('<int:pk>/', views.user_detail, name='user_detail'),
path('<int:pk>/edit/', views.user_edit, name='user_edit'),
path('<int:pk>/delete/', views.user_delete, name='user_delete'),
```

So the current system is hybrid:

- PWA list/search uses JSON API.
- Detail/edit/create/delete use Django templates.

---

## 25. Why The API Is Read-Only

File: `api/views.py`

```py
class UserViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [CanManageUsers]
    serializer_class = UserSerializer
```

`ReadOnlyModelViewSet` gives:

- `list`
- `retrieve`

It does not give:

- `create`
- `update`
- `partial_update`
- `destroy`

That is why user writes still go through `users/views.py`.

---

## 26. Where FHIR History Fits

File: `UsersManageView.vue`

```js
function userHistoryPath(user) {
  const resourceType = user.profile?.role === 'client'
    ? 'Patient'
    : 'Practitioner'
  return `/api/fhir/${resourceType}/user-${user.id}/_history/`
}
```

The table can link a user to a FHIR history endpoint.

Concept:

- Client users map to FHIR `Patient`.
- Staff/provider users map to FHIR `Practitioner`.
- History is served through `/api/fhir/.../_history/`.

---

## 27. Common Debugging Path

When the user table is empty or broken:

```text
1. Browser console
2. Network tab: GET /api/users/
3. Response status: 200, 403, 500?
4. Django terminal logs
5. Check logged-in user role
6. Check UserProfile exists
7. Check serializer fields
8. Check database rows
```

Useful commands:

```powershell
python manage.py shell
python manage.py check
python manage.py test users api
```

---

## 28. Hands-On Lab: Add A User Field To The Table

Goal: display `reference_number` in the Vue table.

Steps:

1. Confirm `UserProfile.reference_number` exists in `users/models.py`.
2. Add `reference_number` to `UserProfileSerializer.fields`.
3. Add a table header in `UsersManageView.vue`.
4. Render `user.profile?.reference_number || '-'`.
5. Open `/app/users` and test.

Expected pipeline change:

```text
Database field
  -> serializer field
  -> JSON response
  -> Vue render
```

---

## 29. Lab Code: Serializer Change

File: `api/serializers.py`

```py
class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = [
            'role',
            'role_display',
            'reference_number',
            'facility',
            'facility_name',
            'phone',
            'is_active',
        ]
```

Teaching point:

If the frontend needs a field, the backend must explicitly expose it through the serializer.

---

## 30. Lab Code: Vue Table Change

File: `frontend/src/views/UsersManageView.vue`

```vue
<th>Reference</th>
```

```vue
<td>{{ user.profile?.reference_number || '-' }}</td>
```

Teaching point:

Frontend rendering should match the API contract, not the database directly.

---

## 31. Local Run Commands

Backend:

```powershell
cd mythanzi
python manage.py runserver
```

Frontend dev server:

```powershell
cd mythanzi/frontend
npm run dev
```

Docker:

```powershell
cd mythanzi
docker compose up --build
```

Production frontend build:

```powershell
cd mythanzi/frontend
npm run build
```

---

## 32. Pull Request Checklist

Before opening a PR:

```powershell
python manage.py check
python manage.py test users api
cd frontend
npm run build
```

Also verify:

- `/app/users` loads.
- Search works.
- Admin permissions still protect `/api/users/`.
- User detail/edit links still work.
- No serializer field names were broken.

---

## 33. What To Remember

The user management pipeline is:

```text
Vue screen
  -> frontend API helper
  -> DRF router
  -> viewset permissions
  -> queryset
  -> serializer
  -> database models
  -> JSON
  -> Vue render
```

When debugging, walk the pipeline one step at a time.

When adding fields, update the serializer and the UI together.

When adding write behavior, decide whether it belongs in the existing Django pages or a new DRF write endpoint.
