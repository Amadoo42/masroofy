# Contributing to Masroofy

Thank you for contributing. This document covers everything you need to know before writing your first line of code: the Git workflow, naming conventions, architectural rules, testing requirements, and the checklist every pull request must satisfy.

For the full coding conventions reference (patterns, examples, Tailwind rules, etc.), see [`docs/source/guides/conventions.md`](docs/source/guides/conventions.md). For a high-level map of the system, see [`docs/source/guides/architecture.md`](docs/source/guides/architecture.md).

---

## Table of Contents

- [Git Workflow](#git-workflow)
- [Commit & Issue Prefixes](#commit--issue-prefixes)
- [Architecture Rules](#architecture-rules)
- [File Structure Quick Reference](#file-structure-quick-reference)
- [Writing Code](#writing-code)
- [Writing Tests](#writing-tests)
- [Linting & Formatting](#linting--formatting)
- [Opening a Pull Request](#opening-a-pull-request)
- [PR Checklist](#pr-checklist)

---

## Git Workflow

| Branch | Purpose |
| :--- | :--- |
| `main` | Production-ready, stable code only. Never commit here directly. |
| `dev` | Integration branch. All feature branches merge here first via PR. |
| `<category>/<name>` | Your working branch. Always created off `dev`. |

**Branch naming format:** `category/snake_case_description`

Valid categories and examples:

| Category | When to use | Example |
| :--- | :--- | :--- |
| `feature` | New functionality | `feature/csv_export` |
| `bugfix` | Fixing a broken behaviour | `bugfix/daily_limit_midnight_rollover` |
| `hotfix` | Urgent fix directly from `main` | `hotfix/balance_underflow` |
| `refactor` | Restructuring without changing behaviour | `refactor/transaction_service_split` |
| `docs` | Documentation only | `docs/data_schema_update` |

**Workflow steps:**

```bash
# 1. Make sure your local dev is up to date
git checkout dev
git pull origin dev

# 2. Create your working branch
git checkout -b feature/my_feature

# 3. Do your work, commit often
git add .
git commit -m "feat: add spending category breakdown to history view"

# 4. Push and open a PR targeting dev
git push origin feature/my_feature
```

Pull requests require **at least one approval** before merging. Squash-merge is preferred to keep the `dev` history readable.

---

## Commit & Issue Prefixes

All commit messages and issue titles must start with one of the following prefixes. This keeps the history scannable and makes automated changelogs possible.

| Prefix | Use for |
| :--- | :--- |
| `feat:` | A new feature or user-facing functionality |
| `fix:` | A bug fix |
| `styl:` | Whitespace, formatting, or UI styling tweaks that don't affect behaviour |
| `refactor:` | Code restructuring that neither fixes a bug nor adds a feature |
| `docs:` | Documentation-only changes |
| `chore:` | Build process, dependency updates, environment setup |
| `test:` | Adding or correcting tests with no production code change |

**Examples:**

```
feat: add notification bell badge to mobile nav
fix: correct spent_today reset on midnight rollover
refactor: extract balance mutation into _mutate_balance helper
docs: update data-schema with Notification model fields
chore: pin hypothesis to 6.152.4 in requirements.txt
```

---

## Architecture Rules

Masroofy follows a **Strict Service Layer (Command Pattern)**. These are non-negotiable and will be enforced during code review.

```
models.py   → Schema definitions and field-level validators only. No logic.
services.py → All business logic, calculations, and cross-model coordination.
views.py    → HTTP traffic controllers only. Parse request, call service, return response.
forms.py    → Input validation at the HTTP boundary.
```

**The rule of thumb:** If you are writing logic that involves math, database state, or decisions about model data — it belongs in `services.py`, not in `views.py` or `models.py`.

### Financial Mutations

Any method that modifies `remaining_cycle_balance` or `spent_today` **must**:

1. Be decorated with `@transaction.atomic`.
2. Use `select_for_update()` to lock the cycle row before reading or writing.

```python
# The only correct pattern for balance changes
locked_cycle = BudgetCycle.objects.select_for_update().get(pk=cycle.pk)
locked_cycle.remaining_cycle_balance -= amount_delta
locked_cycle.save()
```

Never modify balance fields outside of `TransactionMutationCommand._mutate_balance()`. That method is the single authoritative point for all cycle balance changes.

### HTMX Interactions

When adding a new UI action that should not cause a full page reload:

- Use `hx-post` or `hx-get` on the triggering element.
- In the view, branch on `request.htmx`:
  - **HTMX:** Return `HttpResponse(status=204, headers={"HX-Refresh": "true"})` for full-dashboard refreshes, or a rendered HTML partial for targeted swaps.
  - **Standard:** Return a `redirect()`.
- Do not add per-form CSRF tokens for HTMX requests — the global token is already set on `<body>` in `base.html`.

---

## File Structure Quick Reference

```
masroofy/
├── core/
│   ├── settings.py          ← Django config. Use .env for secrets.
│   ├── urls.py              ← Root URL dispatcher → includes budget.urls
│   ├── asgi.py
│   └── wsgi.py
└── budget/
    ├── models.py            ← Schema only. No business logic.
    ├── views.py             ← HTTP routing only. No business logic.
    ├── services.py          ← ALL business logic lives here.
    ├── forms.py             ← Input validation at the HTTP boundary.
    ├── urls.py              ← App-level URL patterns.
    ├── admin.py             ← Django admin registrations.
    ├── context_processors.py← Injects unread_notifications into every template.
    ├── factories.py         ← factory_boy factories. Test use only.
    ├── tests.py             ← Full test suite.
    ├── migrations/
    └── templates/budget/
        ├── base.html        ← Shell, nav, Tailwind config, HTMX, CSRF header.
        ├── dashboard.html
        ├── history.html
        ├── setup.html
        ├── settings.html
        ├── login.html
        ├── signup.html
        ├── tx_row.html      ← Read-only transaction row partial.
        └── tx_edit_row.html ← Editable transaction row partial (HTMX swap target).
docs/
├── Makefile                 ← Run `make html` to build docs.
└── source/
    ├── conf.py
    ├── index.rst
    ├── guides/              ← Hand-written developer guides (start here).
    └── api/                 ← Auto-generated from docstrings via Sphinx autodoc.
```

---

## Writing Code

### Python

- Follow **PEP 8**. The project uses `ruff` — see [Linting & Formatting](#linting--formatting).
- Use type hints on all service method signatures (see `services.py` for examples).
- Use `select_related()` for forward FK lookups and `prefetch_related()` for reverse FK / M2M to avoid N+1 queries.
- Call `model.full_clean()` before every `model.save()` in the service layer as a defence-in-depth measure.

### Frontend (Tailwind + HTMX)

- **No external `.css` files.** All styling is done via Tailwind utility classes in templates.
- Stick to the colour palette defined in `tailwind.config` inside `base.html`:

  | Token | Hex | Use for |
  | :--- | :--- | :--- |
  | `#000000` | Page background | `bg-black` |
  | `#0A0A0A` | Cards and panels | `bg-[#0A0A0A]` |
  | `#121212` | Table headers / hover rows | `bg-[#121212]` |
  | `#222` | Rigid borders | `border-[#222]` |
  | `#333` | Input borders | `border-[#333]` |
  | `primary` (`#007AFF`) | Accent, active states | `text-primary`, `border-primary` |
  | `error` (`#ffb4ab`) | Destructive actions, negative values | `text-error` |

- **Typography rule:** Use `font-data-md` / `font-data-sm` / `font-data-lg` (JetBrains Mono) for all financial figures and numeric data. Use `font-label`, `font-body`, `font-heading` (Inter) for everything else.
- Use **Material Symbols Outlined** for icons: `<span class="material-symbols-outlined">icon_name</span>`. Do not introduce a second icon library.

### Environment Variables

Never commit secrets. Keep `SECRET_KEY` and any credentials in `.env`. The file is already in `.gitignore`.

---

## Writing Tests

The project uses two complementary testing approaches. Both must be used where appropriate.

### Standard Django Unit Tests

Use `django.test.TestCase` for deterministic, scenario-based tests: view redirects, form validation errors, service boundary conditions, and specific known inputs.

Always use `factory_boy` factories from `budget/factories.py` for object creation — do not construct model instances manually where a factory exists.

| Factory | Produces |
| :--- | :--- |
| `UserFactory` | `User` with sequential email and username |
| `BudgetCycleFactory` | `BudgetCycle`, 5000 EGP allowance, 30-day cycle from today |
| `TransactionFactory` | `Transaction` with random amount and category |

### Hypothesis Property-Based Tests

Use `hypothesis` with `hypothesis.extra.django.TestCase` for **mathematical invariants** — properties that must hold across a continuous range of inputs. This is mandatory for any new financial calculation.

```python
from hypothesis import given
from hypothesis.extra.django import TestCase as HypothesisTestCase
import hypothesis.strategies as st

class MyInvariantTests(HypothesisTestCase):
    @given(
        amounts=st.lists(
            st.decimals(min_value=Decimal("0.01"), max_value=Decimal("1000.00"), places=2),
            min_size=1,
            max_size=20,
        )
    )
    def test_my_invariant(self, amounts):
        # Assert the property that must always hold, for any generated input.
        ...
```

Always clean up database objects at the end of a Hypothesis test body to prevent state leaking between generated examples.

### Running the Suite

```bash
cd masroofy
python manage.py test budget

# With coverage
coverage run manage.py test budget
coverage report
```

---

## Linting & Formatting

The project uses `ruff` for both linting and formatting. Run these before every commit:

```bash
# From the repo root
ruff check .
ruff format .
```

Both commands must pass with zero errors before a PR will be approved. Do not introduce per-file `# noqa` ignores without team discussion.

---

## Opening a Pull Request

1. Make sure all tests pass and `ruff check .` is clean.
2. Push your branch and open a PR **targeting `dev`**, not `main`.
3. Fill in the PR description using the issue template as a guide — include a summary, the specific files changed, and the acceptance criteria you've verified.
4. Request a review from at least one other team member.
5. Address all review comments before merging. Squash-merge is preferred.

---

## PR Checklist

Before marking your PR as ready for review, confirm every item below:

- [ ] Business logic is in `services.py` — not in `views.py` or `models.py`.
- [ ] Any balance mutation uses `@transaction.atomic` and `select_for_update()`.
- [ ] Any new UI interaction uses `hx-post` / `hx-get` and branches on `request.htmx`.
- [ ] New elements use `font-data-*` (JetBrains Mono) for numbers, `font-label`/`font-body` for text.
- [ ] New colours are added to `tailwind.config` in `base.html`, not hardcoded inline.
- [ ] Unit tests written for specific scenarios; Hypothesis tests written for numeric invariants.
- [ ] `ruff check .` passes with no errors.
- [ ] `python manage.py test budget` passes with no failures.
- [ ] No secrets, `.env` values, or `db.sqlite3` are committed.
- [ ] Branch follows `category/snake_case` naming convention off `dev`.
- [ ] All commit messages use the correct prefix (`feat:`, `fix:`, `refactor:`, etc.).
- [ ] Docstrings added to any new public service methods.
- [ ] If a new model was added, a migration was generated and committed.

---

## Questions?

Open an issue using the **Project Task** template and tag the relevant team member. For architectural questions, consult [`docs/source/guides/architecture.md`](docs/source/guides/architecture.md) and [`docs/source/guides/conventions.md`](docs/source/guides/conventions.md) first.