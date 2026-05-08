# Data Schema — Masroofy

This document is the authoritative reference for the database schema used in Masroofy.
It covers every model, every field, the constraints enforced at each layer, and the
relationships between models. For the business logic that operates on this schema, see
`guides/class-reference.md`. For the architectural rationale behind key design decisions,
see `guides/architecture.md`.

All models live in `masroofy/budget/models.py`. The database engine is SQLite
(`db.sqlite3`), configured in `core/settings.py`. The schema is managed entirely
through Django migrations located in `masroofy/budget/migrations/`.

---

## Entity Relationship Overview

```
User  ──< BudgetCycle ──< Transaction
 └─────────────────────────< Notification
```

- One `User` has many `BudgetCycle`s. Only one cycle may be `is_active=True` at any time.
- One `BudgetCycle` has many `Transaction`s. Deleting a cycle cascades to all its transactions.
- One `User` has many `Notification`s. Notifications are decoupled from cycles — they are
  not deleted when a cycle ends, only when `AccountService.wipe_data()` is called.

---

## Enumerations

These are Django `TextChoices` enums. Their string values are stored directly in the
database as `VARCHAR` fields.

### `AllowanceStatus`

Used internally by the service layer to evaluate spending thresholds after every balance
mutation. Never stored in the database — computed on the fly by `BudgetCycleService.get_cycle_metrics()`.

| Enum Member | DB Value | Trigger Condition |
| :--- | :--- | :--- |
| `NORMAL` | `"NORMAL"` | `use_percent < 80` |
| `HIGH_USAGE` | `"HIGH_USAGE"` | `80 <= use_percent < 100` |
| `LIMIT_REACHED` | `"LIMIT_REACHED"` | `use_percent >= 100` |

### `Category`

Stored in `Transaction.category` as a `VARCHAR(20)`.

| Enum Member | DB Value | Display Label |
| :--- | :--- | :--- |
| `FOOD` | `"FOOD"` | Food |
| `TRANSPORT` | `"TRANSPORT"` | Transport |
| `ENTERTAINMENT` | `"ENTERTAINMENT"` | Entertainment |
| `BILLS` | `"BILLS"` | Bills |
| `OTHER` | `"OTHER"` | Other |

---

## Models

---

### `User`

**DB Table:** `budget_user`

**Inherits from:** `django.contrib.auth.models.AbstractUser`

The application's custom user model. Email is the login identifier (`USERNAME_FIELD = "email"`).
Username is retained as a human-readable display name. All standard Django auth fields
(`password`, `is_active`, `is_staff`, `date_joined`, etc.) are inherited from `AbstractUser`
and are not repeated here.

> **Migration history note:** The original schema (`0001_initial`) included `hashed_pin`,
> `is_privacy_lock_enabled`, and `failed_attempts` fields for a PIN-lock feature. These
> were removed in migration `0002` in favour of Django's built-in PBKDF2 password pipeline.
> Migration `0003` changed `username` from a unique nullable field to a non-unique
> non-nullable field to allow multiple users to share a display name.

| Column | Django Field | Type | Constraints | Notes |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `BigAutoField` | `BIGINT` | PK, auto-increment | Inherited from AbstractUser |
| `email` | `EmailField` | `VARCHAR(254)` | Unique, Not Null | Login identifier |
| `username` | `CharField(150)` | `VARCHAR(150)` | Not Null | Display name only. Not used for login. |
| `password` | `CharField(128)` | `VARCHAR(128)` | Not Null | PBKDF2-hashed by Django |
| `is_active` | `BooleanField` | `BOOLEAN` | Default `True` | Inherited |
| `is_staff` | `BooleanField` | `BOOLEAN` | Default `False` | Inherited |
| `date_joined` | `DateTimeField` | `DATETIME` | Default `now` | Inherited |
| `last_login` | `DateTimeField` | `DATETIME` | Nullable | Inherited |

**Indexes:** Unique index on `email`.

---

### `BudgetCycle`

**DB Table:** `budget_budgetcycle`

The central financial record for one allowance period. It acts as the source of truth
for a user's budget state. The `remaining_cycle_balance` field is a **stored derived value** —
it is decremented atomically on every transaction mutation rather than being recalculated
via a `SUM()` aggregation on every read. This is a deliberate performance and consistency
trade-off; see `guides/architecture.md` for the rationale.

The `spent_today` / `last_update_date` pair solves the **Midnight Problem**: if
`last_update_date` does not equal today's date, the service layer treats `spent_today`
as `Decimal("0.00")` without issuing a database write. This means the daily tracker
resets lazily on the first transaction or dashboard load of a new day.

| Column | Django Field | Type | Constraints | Notes |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `BigAutoField` | `BIGINT` | PK, auto-increment | |
| `user_id` | `ForeignKey(User)` | `BIGINT` | FK → `budget_user.id`, CASCADE, Not Null | |
| `total_allowance` | `DecimalField(10, 2)` | `DECIMAL(10,2)` | Not Null, `>= 0.01` | Set at cycle creation. Mutable via Settings. |
| `remaining_cycle_balance` | `DecimalField(10, 2)` | `DECIMAL(10,2)` | Not Null | Decremented atomically on each mutation. Never recalculated from scratch. |
| `spent_today` | `DecimalField(10, 2)` | `DECIMAL(10,2)` | Not Null, Default `0.00` | Resets logically when `last_update_date != today`. |
| `last_update_date` | `DateField` | `DATE` | Not Null, `auto_now_add=True` | Compared against `today` to detect day rollover. |
| `start_date` | `DateField` | `DATE` | Not Null | Beginning of the allowance period. |
| `end_date` | `DateField` | `DATE` | Not Null | End of the allowance period. Must be strictly after `start_date`. |
| `is_active` | `BooleanField` | `BOOLEAN` | Not Null, Default `True` | Exactly one cycle per user should be `True` at any time. Enforced by the service layer, not a DB constraint. |

**Indexes:** None beyond the implicit FK index on `user_id`.

**Invariants (enforced by `BudgetCycleService`, not the DB):**
- `total_allowance > 0`
- `end_date > start_date`
- When a new cycle is created, all existing active cycles for the user are set to `is_active=False` before the new one is saved.

---

### `Transaction`

**DB Table:** `budget_transaction`

Represents a single logged expense within a `BudgetCycle`. A `Transaction` record
should never be created, modified, or deleted directly via the ORM in application code.
All mutations must go through `TransactionMutationCommand` to guarantee that
`BudgetCycle.remaining_cycle_balance` and `spent_today` stay consistent.

| Column | Django Field | Type | Constraints | Notes |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `BigAutoField` | `BIGINT` | PK, auto-increment | |
| `cycle_id` | `ForeignKey(BudgetCycle)` | `BIGINT` | FK → `budget_budgetcycle.id`, CASCADE, Not Null | Deleting a cycle deletes all its transactions. |
| `amount` | `DecimalField(10, 2)` | `DECIMAL(10,2)` | Not Null | Must be `> 0`. Enforced by the service layer. |
| `category` | `CharField(20)` | `VARCHAR(20)` | Not Null | Must be a valid `Category` value. Enforced by Django's field `choices`. |
| `timestamp` | `DateTimeField` | `DATETIME` | Not Null, `auto_now_add=True` | Set at creation, immutable. Stored in UTC. Displayed in `Africa/Cairo` timezone via template filter. |
| `note` | `TextField` | `TEXT` | Nullable, Blank allowed | Optional free-text description. |

**Indexes:** None beyond the implicit FK index on `cycle_id`.

---

### `Notification`

**DB Table:** `budget_notification`

**Added in:** Migration `0005`

A persistent alert record created automatically by `TransactionMutationCommand._mutate_balance()`
when a spending threshold boundary is crossed. Notifications are displayed in the
nav bell and dismissed individually via `NotificationReadView`. They are only bulk-deleted
by `AccountService.wipe_data()`.

| Column | Django Field | Type | Constraints | Notes |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `BigAutoField` | `BIGINT` | PK, auto-increment | |
| `user_id` | `ForeignKey(User)` | `BIGINT` | FK → `budget_user.id`, CASCADE, Not Null | |
| `message` | `CharField(255)` | `VARCHAR(255)` | Not Null | Human-readable alert text. Set by the service layer. |
| `is_read` | `BooleanField` | `BOOLEAN` | Not Null, Default `False` | Set to `True` by `NotificationReadView`. Never reset. |
| `created_at` | `DateTimeField` | `DATETIME` | Not Null, `auto_now_add=True` | |

**Ordering:** `Meta.ordering = ["-created_at"]` — newest first by default on all querysets.

**Indexes:** None beyond the implicit FK index on `user_id`.

**Trigger conditions (enforced by `_mutate_balance`):**

| Transition | Message Created |
| :--- | :--- |
| `NORMAL` → `HIGH_USAGE` | `"Warning: You have utilized over 80% of your cycle budget."` |
| any non-`LIMIT_REACHED` → `LIMIT_REACHED` | `"Budget exhausted! You have reached 100% of your cycle allowance."` |

Note that notifications are only created on threshold **crossings**, not on every transaction
that lands within a threshold band. A user who is already at `HIGH_USAGE` will not receive
a second high-usage notification on the next transaction.

---

## Migration History

| Migration | Key Change |
| :--- | :--- |
| `0001_initial` | Creates `User`, `BudgetCycle`, `Transaction`. Initial schema with `hashed_pin`, `failed_attempts`, `is_privacy_lock_enabled` on `User`. |
| `0002_remove_user_...` | Drops `hashed_pin`, `failed_attempts`, `is_privacy_lock_enabled`. Makes `email` unique. Makes `username` nullable and unique. |
| `0003_alter_user_username` | Makes `username` non-nullable and non-unique (display name semantics). |
| `0004_alter_budgetcycle_total_allowance` | Adds `MinValueValidator(0.01)` to `BudgetCycle.total_allowance`. |
| `0005_notification` | Creates the `Notification` model. |

---

## Validation Layers

The schema is protected by validation at three distinct layers. A request must pass all
three before data is written to the database.

**Layer 1 — Django Forms (`forms.py`):** Validates HTTP input at the boundary. Enforces
field types, value ranges, and cross-field rules like date ordering. This is the first
line of defence and produces user-facing error messages.

**Layer 2 — Service Layer (`services.py`):** Enforces business rules before any ORM
call. Raises `ValidationError` with explicit messages for conditions like non-positive
amounts or missing active cycles. Calls `model.full_clean()` as a defence-in-depth
measure before every save.

**Layer 3 — Model / DB (`models.py` + migrations):** Enforces hard constraints at the
schema level via `MinValueValidator`, `choices`, field nullability, and uniqueness
constraints. These are the last line of defence and should never be the first thing
that catches bad data in normal operation.
