# Class Reference — Masroofy

This document is the authoritative hand-written reference for every class in the
`budget` application. It reflects the actual implemented codebase. For the raw
auto-generated docstring output, see the **API Reference** section of this documentation.

All classes live in `masroofy/budget/` unless a different path is noted.

---

## `models.py`

---

### `AllowanceStatus`

**Type:** `models.TextChoices` (Enum)

**Description:**
Defines the three alert threshold states used by the dashboard UI and the notification
system. The service layer evaluates these states after every balance mutation.

**Values:**

| Value | DB String | Trigger Condition |
|---|---|---|
| `NORMAL` | `"NORMAL"` | Usage is below 80% of `total_allowance` |
| `HIGH_USAGE` | `"HIGH_USAGE"` | Usage has reached or exceeded 80% |
| `LIMIT_REACHED` | `"LIMIT_REACHED"` | Usage has reached or exceeded 100% |

---

### `Category`

**Type:** `models.TextChoices` (Enum)

**Description:**
Enumerates the valid expense categories a user can assign to a `Transaction`.
Used as the `choices` argument on `Transaction.category`.

**Values:** `FOOD`, `TRANSPORT`, `ENTERTAINMENT`, `BILLS`, `OTHER`

---

### `User`

**Inherits from:** `django.contrib.auth.models.AbstractUser`

**Description:**
The custom user model for the application. Email is used as the login identifier
instead of username. Username is retained as a display name field.

**`USERNAME_FIELD`:** `email`
**`REQUIRED_FIELDS`:** `["username"]`

**Fields:**

| Field | Type | Notes |
|---|---|---|
| `email` | `EmailField` | Unique. Used for login. |
| `username` | `CharField(150)` | Display name. Not unique, not blank. |

All other fields (`password`, `is_active`, `is_staff`, `date_joined`, etc.) are
inherited from `AbstractUser`.

> **Note:** The original design specified `hashed_pin`, `is_privacy_lock_enabled`, and
> `failed_attempts` fields. These were removed in migration `0002` in favour of
> Django's built-in password hashing pipeline.

**Methods:**

- **`__str__()`** → Returns `self.email`.

---

### `BudgetCycle`

**Inherits from:** `models.Model`

**Description:**
The central data record representing one allowance period for a user. It acts as the
financial source of truth for the cycle. Business logic (calculations, threshold
evaluation) lives in `BudgetCycleService`, not on this model.

**Fields:**

| Field | Type | Notes |
|---|---|---|
| `user` | `ForeignKey(User)` | `CASCADE`. `related_name="budget_cycles"` |
| `total_allowance` | `DecimalField(10, 2)` | Validated `>= 0.01` via `MinValueValidator` |
| `remaining_cycle_balance` | `DecimalField(10, 2)` | Decremented atomically on each transaction |
| `spent_today` | `DecimalField(10, 2)` | Resets logically when `last_update_date != today` |
| `last_update_date` | `DateField` | Set to `auto_now_add`. Updated by service on each mutation |
| `start_date` | `DateField` | Beginning of the allowance period |
| `end_date` | `DateField` | End of the allowance period |
| `is_active` | `BooleanField` | Only one cycle per user may be `True` at a time |

**Invariants enforced by the service layer:**
- `total_allowance > 0`
- `end_date > start_date`
- Creating a new cycle deactivates all previous active cycles for that user

---

### `Transaction`

**Inherits from:** `models.Model`

**Description:**
Represents a single logged expense within a `BudgetCycle`. Creation, editing, and
deletion are always performed through `TransactionMutationCommand` to ensure the
parent cycle's balance fields stay consistent.

**Fields:**

| Field | Type | Notes |
|---|---|---|
| `cycle` | `ForeignKey(BudgetCycle)` | `CASCADE`. `related_name="transactions"` |
| `amount` | `DecimalField(10, 2)` | Must be `> 0`. Enforced by service. |
| `category` | `CharField(20)` | Must be a valid `Category` choice |
| `timestamp` | `DateTimeField` | `auto_now_add=True`. Immutable after creation. |
| `note` | `TextField` | Optional free-text description. `blank=True, null=True` |

---

### `Notification`

**Inherits from:** `models.Model`

**Description:**
A persistent, user-facing alert record created automatically by
`TransactionMutationCommand._mutate_balance()` when a spending threshold is crossed.
Displayed via the notification bell in `base.html` and dismissed via
`NotificationReadView`.

**Fields:**

| Field | Type | Notes |
|---|---|---|
| `user` | `ForeignKey(User)` | `CASCADE`. `related_name="notifications"` |
| `message` | `CharField(255)` | Human-readable alert text |
| `is_read` | `BooleanField` | `False` by default. Set to `True` on dismissal. |
| `created_at` | `DateTimeField` | `auto_now_add=True` |

**Meta:**
- `ordering = ["-created_at"]` — newest notifications first.

---

## `services.py`

---

### `BudgetCycleService`

**Type:** Plain class (no Django base class). All methods are `@staticmethod`.

**Description:**
Handles all **read** operations and cycle creation. Contains no instance state.

---

#### `BudgetCycleService.get_cycle_metrics(cycle)`

**Signature:** `get_cycle_metrics(cycle: BudgetCycle) -> dict`

**Description:**
The primary read method for the dashboard. Computes all derived financial values
from the stored cycle fields in one pass. Handles the "Midnight Problem" inline:
if `cycle.last_update_date != today`, `spent_today` is treated as `Decimal("0.00")`
without writing to the database.

**Returns a dictionary with the following keys:**

| Key | Type | Description |
|---|---|---|
| `remaining_balance` | `Decimal` | The stored `remaining_cycle_balance` |
| `daily_limit` | `Decimal` | `remaining_balance / days_remaining` |
| `remaining_today` | `Decimal` | `daily_limit - spent_today` (can be negative) |
| `total_spent` | `Decimal` | `total_allowance - remaining_balance` |
| `use_percent` | `float` | Capped at 100. Percentage of allowance spent. |
| `current_day` | `int` | Days elapsed since `start_date` (min 1) |
| `total_days` | `int` | Full length of the cycle in days (min 1) |
| `days_remaining` | `int` | Days left until and including `end_date` (min 0) |
| `status` | `AllowanceStatus` | Current threshold state |
| `is_final_day` | `bool` | `True` if today == `end_date` |

---

#### `BudgetCycleService.create_cycle(user, allowance, start_date, end_date)`

**Signature:** `create_cycle(user: User, allowance: Decimal, start_date, end_date) -> BudgetCycle`

**Decorator:** `@transaction.atomic`

**Description:**
Creates and activates a new `BudgetCycle`. Before saving, it deactivates all
currently active cycles for the user (enforcing the one-active-cycle invariant).
Raises `ValidationError` for invalid inputs before any database writes occur.

**Raises:**
- `ValidationError("Allowance must be a positive amount.")` — if `allowance <= 0`
- `ValidationError("End date must be strictly after start date.")` — if `end_date <= start_date`

---

### `TransactionMutationCommand`

**Type:** Plain class. All methods are `@classmethod` or `@staticmethod`.

**Description:**
Handles all **write** operations on `Transaction` records. Every public method is
`@transaction.atomic`. The private `_mutate_balance` method uses `select_for_update()`
on the cycle row to prevent lost-update race conditions under concurrent requests.

---

#### `TransactionMutationCommand.log(user, amount, category, note)`

**Signature:** `log(user: User, amount: Decimal, category: str, note: str = "") -> Transaction`

**Description:**
Logs a new expense against the user's active cycle. Creates the `Transaction` record,
then calls `_mutate_balance` to decrement the cycle balance and update daily tracking.

**Raises:**
- `ValidationError("No active budget cycle found.")` — if no `is_active=True` cycle exists
- `ValidationError("Amount must be strictly positive.")` — if `amount <= 0`

---

#### `TransactionMutationCommand.delete(user, transaction_id)`

**Signature:** `delete(user: User, transaction_id: int) -> None`

**Description:**
Deletes a transaction and refunds its amount back to the cycle balance by calling
`_mutate_balance` with a negative delta.

---

#### `TransactionMutationCommand.edit(user, transaction_id, amount, category, note)`

**Signature:** `edit(user: User, transaction_id: int, amount: Decimal, category: str, note: str = "") -> Transaction`

**Description:**
Edits an existing transaction in two atomic balance steps: first refunds the old
amount, then charges the new amount. This ensures the cycle balance is always correct
regardless of the difference between old and new amounts.

**Raises:**
- `ValidationError("Amount must be strictly positive.")` — if `amount <= 0`

---

#### `TransactionMutationCommand.duplicate(user, transaction_id)`

**Signature:** `duplicate(user: User, transaction_id: int) -> Transaction`

**Description:**
Creates a new transaction with the same `amount` and `category` as the source
transaction. Appends `"(Copy)"` to the note. Delegates to `log()`.

---

#### `TransactionMutationCommand._mutate_balance(cycle, amount_delta, tx_date)`

**Signature:** `_mutate_balance(cycle: BudgetCycle, amount_delta: Decimal, tx_date) -> None`

**Description:**
Private. The single authoritative method for modifying cycle balance fields. Uses
`select_for_update()` to lock the cycle row for the duration of the transaction.

**Logic:**
1. Locks the `BudgetCycle` row.
2. Captures pre-mutation metrics.
3. Decrements `remaining_cycle_balance` by `amount_delta`.
4. If `tx_date == today`: updates `spent_today` and `last_update_date` (resets
   `spent_today` to `amount_delta` if the date has rolled over).
5. Saves the cycle.
6. Captures post-mutation metrics and compares `AllowanceStatus`. Creates a
   `Notification` if the status crossed from `NORMAL → HIGH_USAGE` or
   from `non-LIMIT_REACHED → LIMIT_REACHED`.

---

### `AccountService`

**Type:** Plain class. All methods are `@staticmethod`.

**Description:**
Handles account-level bulk operations that span multiple models.

---

#### `AccountService.export_data(user)`

**Signature:** `export_data(user: User) -> str`

**Description:**
Serialises all of the user's `BudgetCycle` records and their nested `Transaction`
records to a JSON string. Uses `prefetch_related("transactions")` to avoid N+1 queries.

**Returns:** A JSON-formatted string ready to be written to an HTTP response.

---

#### `AccountService.wipe_data(user)`

**Signature:** `wipe_data(user: User) -> None`

**Decorator:** `@transaction.atomic`

**Description:**
Permanently deletes all `BudgetCycle` (and by cascade, `Transaction`) records and
all `Notification` records for the user. The `User` account itself is not deleted.

---

## `views.py`

---

### `DashboardView`

**Inherits from:** `LoginRequiredMixin`, `TemplateView`

**Template:** `budget/dashboard.html`

**Description:**
The primary hub of the application. Renders real-time cycle metrics, the quick-entry
transaction form, the recent transaction table, and the spending doughnut chart.

**Methods:**

- **`dispatch(request)`** — Resolves the active `BudgetCycle`. Redirects to `setup`
  if none exists.
- **`get_context_data()`** — Calls `BudgetCycleService.get_cycle_metrics()` and
  injects all metric keys, the 5 most recent transactions, category choices, and a
  JSON payload for Chart.js.
- **`post(request)`** — Handles Quick Entry form submission. Parses `amount`,
  `category`, and `note` from `POST`, calls `TransactionMutationCommand.log()`.
  Returns `HttpResponse(204, HX-Refresh: true)` for HTMX requests; redirects to
  `dashboard` otherwise.

---

### `SettingsView`

**Inherits from:** `LoginRequiredMixin`, `TemplateView`

**Template:** `budget/settings.html`

**Description:**
The account management hub. Handles four distinct POST actions dispatched via a
hidden `action` field in each sub-form.

**Methods:**

- **`get_context_data()`** — Injects `AccountUpdateForm`, `PasswordChangeForm`, and
  (if an active cycle exists) `ActiveCycleUpdateForm` into the context.
- **`post(request)`** — Branches on `request.POST["action"]`:
  - `"update_account"` — Saves `AccountUpdateForm`. Re-renders with errors on failure.
  - `"update_password"` — Saves `PasswordChangeForm`, calls `update_session_auth_hash`
    to keep the user logged in after a password change.
  - `"update_cycle"` — Saves `ActiveCycleUpdateForm`. Adjusts `remaining_cycle_balance`
    by the difference between the old and new `total_allowance`.
  - `"export"` — Calls `AccountService.export_data()` and returns a JSON file download.
  - `"wipe"` — Calls `AccountService.wipe_data()` and redirects to `setup`.

---

### `SetupView`

**Inherits from:** `LoginRequiredMixin`, `FormView`

**Form:** `BudgetCycleForm`

**Template:** `budget/setup.html`

**Description:**
Handles the onboarding flow for users without an active cycle.

**Methods:**

- **`dispatch(request)`** — If the user already has an active cycle, redirects to
  `dashboard` immediately.
- **`form_valid(form)`** — Calls `BudgetCycleService.create_cycle()`. Catches
  `ValidationError` from the service layer and surfaces it as a form error.

---

### `HistoryView`

**Inherits from:** `LoginRequiredMixin`, `ListView`

**Model:** `Transaction`

**Template:** `budget/history.html`

**Description:**
Displays a filterable, paginated ledger of all transactions in the active cycle.

**Methods:**

- **`dispatch(request)`** — Resolves active cycle; redirects to `setup` if absent.
- **`get_queryset()`** — Filters the base queryset by `category` and/or `date`
  if those keys are present in `request.GET`.
- **`get_context_data()`** — Injects `Category.choices`, the active filter values
  (`current_category`, `current_date`) for UI state highlighting.

---

### `TransactionDeleteView`

**Inherits from:** `LoginRequiredMixin`, `View`

**Description:**
Handles `POST /transaction_delete/<pk>/`. Calls `TransactionMutationCommand.delete()`.
Returns an empty `HttpResponse("")` (causing HTMX to swap the row out of the DOM)
for HTMX requests; redirects to `history` for standard form posts.

---

### `TransactionEditView`

**Inherits from:** `LoginRequiredMixin`, `View`

**Description:**
Handles inline row editing via HTMX.

**Methods:**

- **`get(request, pk)`** — If `?cancel=true` is present, re-renders `tx_row.html`
  (the read-only row). Otherwise renders `tx_edit_row.html` (the editable row).
- **`post(request, pk)`** — Calls `TransactionMutationCommand.edit()`. On success,
  renders `tx_row.html` with the updated transaction (HTMX swaps it in place).
  Returns `HttpResponse(str(e), status=400)` on validation failure.

---

### `TransactionDuplicateView`

**Inherits from:** `LoginRequiredMixin`, `View`

**Description:**
Handles `POST /transaction_duplicate/<pk>/`. Calls
`TransactionMutationCommand.duplicate()`. Returns `HttpResponse(204, HX-Refresh: true)`
for HTMX requests; redirects to `history` otherwise.

---

### `NotificationReadView`

**Inherits from:** `LoginRequiredMixin`, `View`

**Description:**
Handles `POST /notifications/<pk>/read/`. Marks a `Notification` as read via a
queryset `.update()` call (no object-level fetch needed). Returns an empty
`HttpResponse("")` — HTMX deletes the notification element from the DOM via
`hx-swap="delete"`.

---

### `AppLoginView`

**Inherits from:** `LoginView`

**Form:** `PinLoginForm`

**Template:** `budget/login.html`

**Description:**
Overrides Django's built-in login view to use email as the username field and to
provide custom post-login routing.

**Methods:**

- **`get_success_url()`** — Redirects to `dashboard` if the user has an active cycle;
  redirects to `setup` otherwise.

---

### `AppSignupView`

**Inherits from:** `CreateView`

**Form:** `PinSignupForm`

**Template:** `budget/signup.html`

**Description:**
Handles new account registration. Redirects already-authenticated users to `dashboard`.

**Methods:**

- **`dispatch(request)`** — Redirects authenticated users to `dashboard`.
- **`form_valid(form)`** — Calls `super().form_valid()` and adds a success flash message.

---

## `forms.py`

---

### `BudgetCycleForm`

**Inherits from:** `forms.ModelForm` — Model: `BudgetCycle`

**Fields:** `total_allowance`, `start_date`, `end_date`

**Validations:**
- `total_allowance` — `min_value=0.01`, `max_digits=10`, `decimal_places=2`
- `clean()` — Raises `ValidationError` if `start_date >= end_date`

---

### `PinLoginForm`

**Inherits from:** `AuthenticationForm`

**Description:**
Overrides the default login form to use an `EmailInput` for the username field and
a numeric `PasswordInput` (4-digit, `inputmode="numeric"`) for the PIN/password field.

---

### `PinSignupForm`

**Inherits from:** `UserCreationForm` — Model: `User`

**Fields:** `email`, `username`, `password1`, `password2`

**Validations:**
- `password1` and `password2` — validated by `RegexValidator(r"^\d{4}$")` (exactly
  4 numeric digits)
- `clean_username()` — passes the username through unchanged

---

### `AccountUpdateForm`

**Inherits from:** `forms.ModelForm` — Model: `User`

**Fields:** `username`, `email`

**Description:**
Used in `SettingsView` to update display name and email address. Both inputs are
pre-styled with Tailwind utility classes via `attrs`.

---

### `ActiveCycleUpdateForm`

**Inherits from:** `forms.ModelForm` — Model: `BudgetCycle`

**Fields:** `total_allowance`, `start_date`, `end_date`

**Validations:**
- `clean()` — Raises `ValidationError` if `start_date >= end_date`

**Description:**
Used in `SettingsView` to modify parameters of the currently active cycle.
The view is responsible for adjusting `remaining_cycle_balance` by the allowance
difference after the form saves.

---

## `context_processors.py`

---

### `notification_processor(request)`

**Type:** Function-based context processor (registered in `settings.TEMPLATES`).

**Description:**
Injects `unread_notifications` (a queryset of unread `Notification` objects for the
current user) into every template context site-wide. Returns `{"unread_notifications": []}`
for unauthenticated requests. Powers the notification bell badge in `base.html`.

---

## `admin.py`

---

### `CustomUserAdmin`

**Inherits from:** `UserAdmin`

**Description:**
Registers `User` with the Django admin. Overrides `list_display` to show `username`,
`email`, `is_staff`, and `is_active`.

---

### `BudgetCycleAdmin`

**Inherits from:** `ModelAdmin`

**Description:**
Registers `BudgetCycle` with the Django admin. Overrides `save_model()` to call
`obj.full_clean()` before saving, ensuring model-level validators run even when
data is entered via the admin interface.

---

## `factories.py`

---

**Description:**
Contains `factory_boy` factories used exclusively in tests. Not imported anywhere
in production code.

| Factory | Produces | Notable defaults |
|---|---|---|
| `UserFactory` | `User` | Sequential `user_N` username and email |
| `BudgetCycleFactory` | `BudgetCycle` | `total_allowance=5000`, 30-day cycle from today |
| `TransactionFactory` | `Transaction` | Random amount 10–500, random category, Faker sentence note |