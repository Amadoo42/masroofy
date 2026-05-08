# Coding & Naming Conventions

All contributors must adhere to the following conventions to pass code reviews and
maintain velocity. This document reflects the current state of the codebase as of
the v1 refactor (May 8th, 2026). For a full breakdown of what changed in that
refactor, see `guides/changelog.md`.

---

## Git Workflow

- **Main Branch:** `main` (Production-ready, stable code only).
- **Development Branch:** `dev` (Integration branch for testing features together).
  All feature branches merge here first.
- **Feature Branches:** Create branches off `dev` using the format `category/snake_case`.
- *Categories:* `feature`, `bugfix`, `hotfix`, `refactor`, `docs`.
- *Example:* `feature/budget_cycle_model`

---

## Issue & Commit Prefixes

To keep our history and issue tracker clean, all commit messages and issue titles
must start with one of the following prefixes:

- **`feat:`** A new feature or functionality.
- **`fix:`** A bug fix.
- **`styl:`** Changes that do not affect the meaning of the code (white-space,
  formatting, UI styling tweaks).
- **`refactor:`** A code change that neither fixes a bug nor adds a feature
  (e.g., optimizing an ORM query).
- **`docs:`** Documentation only changes (e.g., updating architecture diagrams
  or markdown files).
- **`chore:`** Changes to the build process, environment setup, or library updates.

---

## Naming Standards

| Target | Convention | Example |
| :--- | :--- | :--- |
| **Python Files/Modules** | snake_case | `views.py`, `budget_utils.py` |
| **HTML Templates** | snake_case | `dashboard.html`, `setup.html` |
| **Python Variables/Functions** | snake_case | `get_cycle_metrics()`, `active_cycle` |
| **Python Constants** | SCREAMING_SNAKE | `MAX_LOGIN_ATTEMPTS`, `TAX_RATE` |
| **Django Models/Classes** | PascalCase | `BudgetCycle`, `TransactionMutationCommand` |
| **CSS Classes** | kebab-case | `btn-primary`, `rigid-border` |
| **Service Classes** | PascalCase + intent suffix | `BudgetCycleService`, `TransactionMutationCommand`, `AccountService` |

---

## Django & Python Best Practices

### 1. Architecture: Strict Service Layer Pattern

The codebase follows a **Strict Service Layer (Command Pattern)** architecture.
This supersedes the previously documented "Fat Models, Skinny Views" guideline,
which is no longer applicable.

The responsibilities of each layer are strictly defined and must not be crossed:

- **Models (`models.py`):** Schema definitions and field-level validators only.
  No business logic, no calculations, no threshold evaluations. Models are intentionally
  thin data containers.
- **Services (`services.py`):** All business logic lives here. This includes financial
  calculations, balance mutations, threshold evaluations, and notification creation.
  If you are writing logic that involves math, database state, or cross-model
  coordination, it belongs in a service class.
- **Views (`views.py`):** HTTP traffic controllers only. A view's job is to parse
  the incoming request, delegate to a service, and return an HTTP response. Views
  must contain no business logic whatsoever.
- **Forms (`forms.py`):** Input validation at the HTTP boundary. Forms enforce
  field types, value ranges, and UI-level cross-field rules (e.g., date ordering).
  The service layer performs an additional `full_clean()` call as a defence-in-depth
  measure.

**The rule of thumb:** If you are adding a feature, write the logic in `services.py`
first. Do not put it in `views.py` or `models.py`.

### 2. Service Class Conventions

Service classes are plain Python classes with no Django base class. They hold no
instance state. Use the following patterns:

- **Read-only operations and factory methods** → `@staticmethod` (see `BudgetCycleService`)
- **Write operations that need access to other class methods** → `@classmethod`
  (see `TransactionMutationCommand`)
- **All mutating methods must be decorated with `@transaction.atomic`** to guarantee
  database consistency.

### 3. Database Locking for Financial Mutations

Any service method that modifies a financial balance field (`remaining_cycle_balance`,
`spent_today`) **must** use `select_for_update()` to lock the row for the duration
of the transaction. This prevents lost-update race conditions when the app is served
with multiple workers.

```python
# Correct pattern for any balance mutation
locked_cycle = BudgetCycle.objects.select_for_update().get(pk=cycle.pk)
locked_cycle.remaining_cycle_balance -= amount_delta
locked_cycle.save()
```

Never modify balance fields outside of `TransactionMutationCommand._mutate_balance()`.
That method is the single authoritative point for all cycle balance changes.

### 4. HTMX Integration

The frontend uses HTMX for zero-reload interactions. When adding a new UI action,
follow this pattern:

- Use `hx-post` or `hx-get` attributes on the triggering element instead of
  standard form submissions where a partial update is sufficient.
- In the corresponding view, branch on `request.htmx` (provided by the
  `django-htmx` middleware) to decide the response type:
  - **HTMX request:** Return `HttpResponse(status=204, headers={"HX-Refresh": "true"})`
    for actions that should refresh the whole dashboard, or return a rendered HTML
    partial for targeted swap operations.
  - **Standard request:** Return a `redirect()`.
- The global CSRF token is set via `hx-headers` on the `<body>` tag in `base.html`.
  Do not add per-form CSRF handling for HTMX requests.

### 5. QuerySet Optimisation

- Always use `select_related()` for forward FK lookups and `prefetch_related()` for
  reverse FK or M2M lookups to avoid N+1 database hits.
- Example: `BudgetCycle.objects.filter(user=user).prefetch_related("transactions")`
- The `select_for_update()` pattern (see above) is mandatory for financial mutations
  and is separate from this optimisation concern.

### 6. PEP 8 Compliance

Follow standard Python formatting. The project uses `ruff` for linting and
formatting. Run `ruff check .` and `ruff format .` before committing. The
`ruff` configuration inherits defaults; do not introduce per-file ignores without
team discussion.

### 7. Environment Variables

Never commit secrets. Use an `.env` file for `SECRET_KEY` and any database
credentials. The `.env` file is listed in `.gitignore`. The current
`settings.py` contains a hardcoded insecure `SECRET_KEY` suitable for local
development only — this must be replaced via environment variable before any
deployment.

---

## Frontend Conventions

### Tailwind CSS

The project uses Tailwind CSS loaded via CDN (JIT-less). The custom theme is
configured inline in `base.html` under the `tailwind.config` script block.
When styling new elements:

- Stick to the established colour palette defined in `tailwind.config`:
  - Backgrounds: `#000000` (page), `#0A0A0A` (cards), `#121212` (table headers/rows)
  - Borders: `#222` (rigid borders), `#333` (input borders)
  - Accent: `primary` (`#007AFF`)
  - Destructive: `error` (`#ffb4ab`)
- Do not introduce new custom colour values without updating `tailwind.config`
  and documenting the addition here.
- Do not create external `.css` files for component styles. All styling must be
  done via Tailwind utility classes applied directly in templates.

### Typography

Two font families are in use. Applying them correctly is mandatory for visual
consistency:

- **`font-heading`, `font-body`, `font-label`** → `Inter`. Used for all UI text,
  labels, headings, and descriptions.
- **`font-data-md`, `font-data-sm`, `font-data-lg`** → `JetBrains Mono`. Used
  exclusively for all financial figures, amounts, and numeric data. This ensures
  decimal points align correctly in tables.

### Icons

Use **Material Symbols Outlined** via the Google Fonts icon font. Reference icons
using the `<span class="material-symbols-outlined">icon_name</span>` pattern as
seen throughout the existing templates. Do not introduce a second icon library.

---

## Testing Conventions

The project uses two testing approaches. Both must be used appropriately.

### Standard Django Unit Tests

Use `django.test.TestCase` for deterministic, scenario-based tests. These cover
specific known inputs and expected outputs (e.g., validation boundary conditions,
view redirects, form error states). All existing test classes in `tests.py`
follow this pattern.

### Property-Based Tests (Hypothesis)

Use `hypothesis` with `hypothesis.extra.django.TestCase` for mathematical
invariant testing. Instead of hard-coding values, define the *rules* that must
always hold and let Hypothesis generate hundreds of random inputs to attempt to
falsify them.

Use property-based tests for:
- Financial invariants (e.g., balance always equals allowance minus sum of transactions)
- Any function whose correctness must hold across a continuous range of numeric inputs

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
        # assert the property that must always hold
        ...
```

When writing Hypothesis tests that create database objects, always clean up at
the end of the test body (`BudgetCycle.objects.all().delete()` etc.) to prevent
state leaking between generated examples.

### Test Factories

Use `factory_boy` factories from `budget/factories.py` for all test object
creation. Do not construct model instances manually in tests where a factory
exists. This keeps test setup concise and consistent.

| Factory | Produces |
| :--- | :--- |
| `UserFactory` | `User` with sequential email and username |
| `BudgetCycleFactory` | `BudgetCycle` with 5000 EGP allowance, 30-day cycle |
| `TransactionFactory` | `Transaction` with random amount and category |

---

## Summary Checklist for New Features

When adding any new feature, verify the following before opening a pull request:

- [ ] Business logic is in `services.py`, not in `views.py` or `models.py`.
- [ ] Any balance mutation uses `@transaction.atomic` and `select_for_update()`.
- [ ] Any new UI interaction uses `hx-post` / `hx-get` and branches on `request.htmx`.
- [ ] New elements use `JetBrains Mono` (`font-data-*`) for numbers, `Inter` for text.
- [ ] New colours are added to `tailwind.config` in `base.html`, not hardcoded inline.
- [ ] Tests are written: unit tests for specific scenarios, Hypothesis for numeric invariants.
- [ ] `ruff check .` passes with no errors.
- [ ] No secrets or `.env` values are committed.
- [ ] Branch follows the `category/snake_case` naming convention off `dev`.
- [ ] Commit messages use the correct prefix (`feat:`, `fix:`, `refactor:`, etc.).
