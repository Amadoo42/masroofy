
# System Architecture — Masroofy

## Overview

Masroofy is a personal budget management web application built on **Django 6** using the
**MVT (Model-View-Template)** pattern. It is designed for college students who need to track
a fixed monthly allowance, understand their daily safe spending limit, and receive warnings
before they exhaust their budget.

The application is intentionally structured as a **monolith** — a single Django project with
one app (`budget`) — keeping the deployment surface small and the codebase navigable for a
small team.

---

## High-Level Component Map

```
┌─────────────────────────────────────────────────────────────┐
│                        Browser / Client                     │
│               HTML + Tailwind CSS + HTMX + Chart.js         │
└────────────────────────────┬────────────────────────────────┘
                             │ HTTP / HTMX partial requests
┌────────────────────────────▼────────────────────────────────┐
│                        Django (core/)                       │
│                                                             │
│  ┌──────────────┐   ┌──────────────┐   ┌─────────────────┐  │
│  │   URLs       │──▶│    Views     │──▶│    Templates   │  │
│  │ budget/urls  │   │ budget/views │   │ budget/templates│  │
│  └──────────────┘   └──────┬───────┘   └─────────────────┘  │
│                            │                                │
│                    ┌───────▼────────┐                       │
│                    │    Services    │                       │
│                    │ budget/services│                       │
│                    └───────┬────────┘                       │
│                            │                                │
│                    ┌───────▼────────┐                       │
│                    │     Models     │                       │
│                    │ budget/models  │                       │
│                    └───────┬────────┘                       │
│                            │                                │
│                    ┌───────▼────────┐                       │
│                    │    SQLite DB   │                       │
│                    │   (db.sqlite3) │                       │
│                    └────────────────┘                       │
└─────────────────────────────────────────────────────────────┘
```

---

## Django Project Layout

```
masroofy/          ← Django project root (where manage.py lives)
├── core/          ← Project configuration package
│   ├── settings.py
│   ├── urls.py    ← Root URL dispatcher
│   ├── asgi.py
│   └── wsgi.py
└── budget/        ← The single Django application
    ├── models.py
    ├── views.py
    ├── services.py
    ├── forms.py
    ├── urls.py
    ├── admin.py
    ├── context_processors.py
    ├── factories.py
    ├── tests.py
    ├── migrations/
    └── templates/
        └── budget/
            ├── base.html
            ├── dashboard.html
            ├── history.html
            ├── setup.html
            ├── settings.html
            ├── login.html
            ├── signup.html
            ├── tx_row.html
            └── tx_edit_row.html
```

---

## Architectural Layers

### 1. Templates (Presentation)

All HTML lives under `budget/templates/budget/`. Templates extend `base.html`, which
provides the navigation shell, notification bell, and global CSS/JS imports.

**Frontend stack:**
- **Tailwind CSS** (CDN, JIT-less) — utility-first styling with a custom dark-mode theme
  configured inline via `tailwind.config`.
- **HTMX** — handles partial page updates (inline transaction edits, delete without reload,
  notification dismissal) without writing JavaScript.
- **Chart.js** — renders the spending-by-category doughnut chart on the dashboard.
- **Google Fonts** — Inter (UI) and JetBrains Mono (numeric data).
- **Material Symbols** — icon font for navigation and action buttons.

The templates are deliberately kept logic-free. All computed values (daily limit, status,
days remaining) arrive pre-calculated inside the view's context dictionary.

---

### 2. Views (HTTP Controllers)

`budget/views.py` contains Class-Based Views (CBVs) that handle request routing only.
They are responsible for:

- Authenticating the request via `LoginRequiredMixin`.
- Fetching the active `BudgetCycle` for the current user.
- Calling service methods to mutate data.
- Building the context dictionary passed to templates.
- Returning the correct HTTP response (full page render, HTMX partial, redirect, or
  file download).

Views contain **no business logic**. They delegate all financial calculations and mutations
to the Service layer.

**HTMX integration** is handled via `django-htmx` middleware, which attaches a `request.htmx`
boolean. Views branch on this flag to return either a full redirect or a lightweight
`HttpResponse` fragment with an `HX-Refresh` header.

---

### 3. Services (Business Logic)

`budget/services.py` is the heart of the application. It contains three classes:

| Class | Responsibility |
|---|---|
| `BudgetCycleService` | Pure read operations — metrics calculation, cycle creation |
| `TransactionMutationCommand` | All write operations on transactions and balance |
| `AccountService` | Account-level operations — data export (JSON), data wipe |

All mutating service methods are decorated with `@transaction.atomic` to guarantee
database consistency. `TransactionMutationCommand._mutate_balance` uses
`select_for_update()` to prevent race conditions when two requests update the same
cycle simultaneously.

The service layer is also responsible for **triggering notifications**: after every
balance mutation, it compares pre- and post-mutation `AllowanceStatus` values and
creates a `Notification` record if a threshold boundary has been crossed.

---

### 4. Models (Data & Schema)

`budget/models.py` defines the database schema. Models are intentionally **thin** —
they hold field definitions and validators but contain no business logic. All
calculations live in the service layer.

See `guides/data-schema.md` for a full field-by-field reference.

**Model graph:**

```
User  ──< BudgetCycle ──< Transaction
  └──────────────────────< Notification
```

- One `User` can have many `BudgetCycle`s (only one is `is_active=True` at a time).
- One `BudgetCycle` can have many `Transaction`s.
- One `User` can have many `Notification`s (decoupled from cycles).

---

### 5. Forms (Input Validation)

`budget/forms.py` provides Django form classes that validate user input at the HTTP
boundary before it reaches the service layer. Forms enforce UI-level rules (correct
field types, date ordering, PIN format). The service layer performs an additional
`full_clean()` call as a defence-in-depth measure.

---

### 6. Context Processors

`budget/context_processors.py` injects `unread_notifications` into every template
context for authenticated users, powering the persistent notification bell in the
navigation bar without requiring each view to query for it manually.

---

## Request Lifecycle — Logging a Transaction

The following traces a `POST /dashboard/` request to illustrate how the layers interact:

```
Browser
  │  POST /dashboard/ {amount, category, note}
  ▼
core/urls.py → budget/urls.py
  │  Matches DashboardView
  ▼
DashboardView.post()
  │  Parses & coerces amount to Decimal
  │  Calls TransactionMutationCommand.log(user, amount, category, note)
  ▼
TransactionMutationCommand.log()  [atomic]
  │  Validates amount > 0
  │  Creates Transaction object, calls full_clean(), saves
  │  Calls _mutate_balance(cycle, amount, today)
  ▼
TransactionMutationCommand._mutate_balance()  [atomic + select_for_update]
  │  Captures pre-mutation metrics
  │  Decrements remaining_cycle_balance
  │  Updates spent_today / last_update_date
  │  Saves cycle
  │  Compares pre/post AllowanceStatus → creates Notification if threshold crossed
  ▼
DashboardView.post()  (resumes)
  │  If HTMX request → HttpResponse(204, HX-Refresh: true)
  │  Else            → redirect("dashboard")
  ▼
Browser refreshes / re-renders dashboard
```

---

## Authentication & Security

- `User` extends Django's `AbstractUser` with `email` as the `USERNAME_FIELD`.
- Passwords are stored using Django's default PBKDF2 hashing pipeline.
- All views require authentication via `LoginRequiredMixin`; unauthenticated requests
  are redirected to `/login/`.
- CSRF protection is active on all forms and HTMX requests (the base template sets
  `hx-headers` with the CSRF token globally).
- The PIN signup flow (`PinSignupForm`) restricts passwords to exactly 4 numeric digits
  via a `RegexValidator`, matching the student-focused UX requirement.

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| Service layer instead of fat models | Keeps models as pure schema definitions; service classes are independently testable without HTTP context |
| Stored `remaining_cycle_balance` field | Avoids a `SUM(amount)` aggregation on every page load; updated atomically on every transaction mutation |
| Stored `spent_today` + `last_update_date` | Solves the "Midnight Problem" — if `last_update_date` is not today, `spent_today` is treated as `0` without a DB write |
| HTMX over a full SPA | Keeps the stack simple (no separate API, no JS build step) while still enabling inline editing and partial updates |
| SQLite for storage | Appropriate for single-user local deployment; trivially swappable for PostgreSQL by changing `DATABASES` in `settings.py` |
| `select_for_update()` in mutations | Prevents lost-update race conditions if the app is ever served with multiple workers |
