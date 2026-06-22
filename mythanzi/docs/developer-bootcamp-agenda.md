# Developer Bootcamp Agenda: MyThanzi 1-Day Intensive

This bootcamp is designed to help new developers become productive in the MyThanzi codebase in one day. By the end of the day, each participant should be able to run the project locally, understand the main backend and frontend structure, make a small Django change, follow the Git workflow, and know where to go next.

## Pre-Bootcamp Checklist

Participants should have the following installed before the session:

- Git
- Python 3.11+
- Node.js 20+
- Docker Desktop
- A code editor such as VS Code
- Access to the MyThanzi repository

Recommended project entry points:

- Backend: `mythanzi/manage.py`
- Django settings: `mythanzi/mythanzi/settings.py`
- Root URL routing: `mythanzi/mythanzi/urls.py`
- Main API app: `mythanzi/api`
- Users app: `mythanzi/users`
- Locations app: `mythanzi/locations`
- Chatbot app: `mythanzi/chatbot`
- Vue frontend: `mythanzi/frontend`
- Docker Compose stack: `mythanzi/docker-compose.yml`

## Agenda

| Time | Session Title | Focus / Deliverable |
| --- | --- | --- |
| 09:00 AM - 09:30 AM | Welcome & Project Vision | Kickoff, introductions, product context, and high-level MyThanzi project goals. |
| 09:30 AM - 10:30 AM | Local Environment Setup | Clone the repo, create a Python virtual environment, install `requirements.txt`, review `.env`, and confirm the Django app can start locally. |
| 10:30 AM - 10:45 AM | Morning Coffee Break | Network, stretch, and resolve any setup blockers. |
| 10:45 AM - 12:00 PM | Django App Architecture | Walk through the project layout, `INSTALLED_APPS`, app registration, URL routing, templates, static files, and how `api`, `users`, `locations`, and `chatbot` fit together. |
| 12:00 PM - 01:00 PM | Team Lunch | Provided by the company. |
| 01:00 PM - 02:30 PM | Routing, Views, & Models | Connect URLs, build simple views, inspect model patterns, run migrations, and understand the API/database workflow. |
| 02:30 PM - 03:30 PM | Git Workflow & Standards | Branch naming, commit style, pull requests, code review expectations, CI/CD rules, and when frontend production builds happen. |
| 03:30 PM - 03:45 PM | Afternoon Break | Quick breather. |
| 03:45 PM - 04:30 PM | Hands-on Lab & Troubleshooting | Solo or pair programming: create a small test view or API endpoint, wire it into URLs, run it locally, and debug common issues. |
| 04:30 PM - 05:00 PM | Q&A and Wrap-up | Review lessons learned, answer questions, assign first tickets, and agree on next steps. |

## Session Notes

### 09:30 AM - Local Environment Setup

Primary commands:

```powershell
cd mythanzi
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Frontend commands:

```powershell
cd frontend
npm install
npm run dev
```

Docker Compose option:

```powershell
cd mythanzi
docker compose up --build
```

Deliverable: each developer can run the backend and identify whether they are using local Python, Vite dev server, or Docker Compose.

### 10:45 AM - Django App Architecture

Cover these files and folders:

- `mythanzi/mythanzi/settings.py` for project configuration and installed apps.
- `mythanzi/mythanzi/urls.py` for root routing and Vue frontend fallback.
- `mythanzi/api` for API endpoints and FHIR/HAPI sync logic.
- `mythanzi/users` for user-facing Django pages and account-related behavior.
- `mythanzi/locations` for facility/location workflows and OSRM route integrations.
- `mythanzi/chatbot` for local chatbot views and content helpers.
- `mythanzi/frontend` for the Vue/Vite app.

Deliverable: each developer can explain where a new backend feature, frontend change, or route should be added.

### 01:00 PM - Routing, Views, & Models

Suggested lab flow:

1. Create or identify a simple view.
2. Add a URL pattern in the relevant app.
3. Link the app route from `mythanzi/mythanzi/urls.py` if needed.
4. Inspect the model and migration pattern.
5. Run:

```powershell
python manage.py makemigrations
python manage.py migrate
```

Deliverable: each developer understands the path from URL to view to model/database.

### 02:30 PM - Git Workflow & Standards

Recommended branch format:

```text
feature/short-description
fix/short-description
docs/short-description
```

Recommended local checks before opening a pull request:

```powershell
python manage.py check
python manage.py test
cd frontend
npm run build
```

Docker note: the project Dockerfile runs the Vue production build during image creation, so `docker compose up --build` produces minified frontend assets inside the container image.

Deliverable: each developer knows how to create a branch, commit a focused change, run checks, and request review.

### 03:45 PM - Hands-on Lab

Lab goal: stand up a small test view or endpoint without changing core behavior.

Suggested options:

- Add a simple health/status page.
- Add a small JSON endpoint under an existing app.
- Add a temporary internal-only view that confirms routing and templates.

Acceptance criteria:

- The route loads locally.
- The code is placed in the correct app.
- The change is committed on a feature branch.
- The developer can explain how to test it.

## End-of-Day Outcomes

By 05:00 PM, each participant should be able to:

- Run MyThanzi locally with either Python/Vite or Docker Compose.
- Navigate the Django apps and Vue frontend.
- Understand how static frontend assets are built and served.
- Add a basic route/view/model change.
- Run common checks before review.
- Pick up a first ticket with confidence.
