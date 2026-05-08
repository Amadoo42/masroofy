# Masroofy — Personal Budget Manager

Masroofy is a personal budget management web application built with **Django 6** (MVT architecture). It is designed to help college students track their monthly allowance, calculate a dynamic **Safe Daily Limit**, and receive threshold alerts before they exhaust their budget.

> **Docs:** Full developer documentation lives in [`docs/`](docs/). Start with [`docs/source/guides/architecture.md`](docs/source/guides/architecture.md) for a complete picture of how the system is structured.

---

## Features

- **Budget Cycles** — Define an allowance period with a start/end date and a total allowance.
- **Safe Daily Limit** — Automatically calculates how much you can safely spend each remaining day.
- **Transaction Logging** — Log expenses by category (Food, Transport, Entertainment, Bills, Other) with optional notes.
- **Spending Notifications** — Automatic alerts when you cross 80% or 100% of your cycle budget.
- **Full History** — Filterable transaction ledger with inline edit, delete, and duplicate actions.
- **Data Export / Wipe** — Download a full JSON export of your financial history or wipe all data.
- **Zero-Reload UI** — All interactions (logging, editing, dismissing notifications) are powered by HTMX — no full page reloads.

---

## Tech Stack

| Layer | Technology |
| :--- | :--- |
| Backend Framework | Django 6 |
| Database | SQLite (swappable for PostgreSQL) |
| Frontend Interactions | HTMX 1.9 |
| Styling | Tailwind CSS (CDN, JIT-less) |
| Charts | Chart.js |
| Icons | Material Symbols Outlined |
| Fonts | Inter (UI), JetBrains Mono (numeric data) |
| Testing | Django `TestCase` + Hypothesis (property-based) + factory_boy |
| Linting / Formatting | Ruff |
| Documentation | Sphinx + MyST Parser (`sphinx_rtd_theme`) |

---

## Project Structure

```
masroofy/               ← Django project root (manage.py lives here)
├── core/               ← Project configuration (settings, URLs, WSGI/ASGI)
│   ├── settings.py
│   ├── urls.py
│   ├── asgi.py
│   └── wsgi.py
└── budget/             ← The single Django application
    ├── models.py       ← Schema definitions only (no business logic)
    ├── views.py        ← HTTP traffic controllers only (no business logic)
    ├── services.py     ← All business logic lives here
    ├── forms.py        ← Input validation at the HTTP boundary
    ├── urls.py
    ├── admin.py
    ├── context_processors.py
    ├── factories.py    ← factory_boy factories (test use only)
    ├── tests.py
    ├── migrations/
    └── templates/
        └── budget/
docs/                   ← Sphinx documentation source
requirements.txt
```

> For a detailed breakdown of each layer's responsibilities, see [`docs/source/guides/architecture.md`](docs/source/guides/architecture.md).

---

## Local Development Setup

### Prerequisites

- Python 3.11+
- `pip` (or a virtual environment manager of your choice)

### Steps

**1. Clone the repository and create a virtual environment.**

```bash
git clone <repo-url>
cd masroofy
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
```

**2. Install dependencies.**

```bash
pip install -r requirements.txt
```

**3. Apply database migrations.**

```bash
cd masroofy
python manage.py migrate
```

**4. (Optional) Create a superuser** to access the Django admin at `/admin/`.

```bash
python manage.py createsuperuser
```

**5. Run the development server.**

```bash
python manage.py runserver
```

The app will be available at `http://127.0.0.1:8000/`.

### Environment Variables

The `settings.py` currently contains a hardcoded `SECRET_KEY` suitable for local development only. Before any deployment, move secrets to a `.env` file. The `.env` file is already listed in `.gitignore` — never commit it.

---

## Running Tests

```bash
cd masroofy
python manage.py test budget
```

The test suite uses two complementary approaches:

- **Standard `TestCase`** — Deterministic scenario-based tests for views, forms, and service boundary conditions.
- **Hypothesis property-based tests** — Mathematical invariant proofs that run hundreds of randomly generated inputs against financial logic (e.g., proving the cycle balance is always exactly `allowance − Σ transactions`).

To measure code coverage:

```bash
coverage run manage.py test budget
coverage report
```

---

## Building the Docs

```bash
cd docs
make html
```

The built documentation will be in `docs/build/html/`. Open `index.html` in a browser to browse it locally.

---

## Key Architectural Rules

The codebase follows a **Strict Service Layer (Command Pattern)**. The rule is simple:

> **Business logic → `services.py`. HTTP routing → `views.py`. Schema → `models.py`.**

Crossing these boundaries will fail code review. See [`docs/source/guides/conventions.md`](docs/source/guides/conventions.md) for the full set of rules, including HTMX integration patterns, database locking requirements for financial mutations, and frontend styling conventions.

---

## Contributing

Please read [**CONTRIBUTING.md**](CONTRIBUTING.md) before opening a pull request. It covers the Git workflow, branch naming, commit prefix conventions, code style, and the full checklist that every PR must satisfy.

---

## License

MIT License — Copyright © 2026 Ahmad Amin. See [LICENSE](LICENSE) for the full text.

---

## Authors

Ahmad Amin · Seif Lashin · Jana Ali · Yara Hegab