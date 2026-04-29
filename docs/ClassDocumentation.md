# Budget Cycle Module - Class Descriptions

## 1. BudgetCycleManager
**Description & Responsibility:**
A Django custom Manager class responsible for handling "table-level" operations. It separates the logic used to *find* or *create* cycles from the business logic of the cycle itself.

**Methods:**
* **`get_active_cycle(user: User)`**: Queries the database to retrieve the currently active `BudgetCycle` for the specified user.
* **`create_cycle(user, allowance, start, end)`**: Handles the initialization of a new budget cycle, setting up default values and ensuring the cycle is bound to the user.

---

## 2. BudgetCycle (Model)
**Description & Responsibility:**
The core data model representing an active allowance period. It acts as the "Source of Truth" for the user's financial state, encapsulating all business logic related to daily limits, balances, and rollover calculations.

**Attributes (Stored Fields):**
* **`user`**: `ForeignKey(User)` - Links the budget cycle to a specific user account.
* **`total_allowance`**: `Decimal` - The initial budget amount set by the user for the cycle.
* **`remaining_cycle_balance`**: `Decimal` - A stored field tracking the overall remaining money. Storing this prevents expensive database summations every time the app loads.
* **`spent_today`**: `Decimal` - Tracks money spent exactly on the current day. Used to power the live "Today Tracker" UI.
* **`last_update_date`**: `Date` - Tracks the last time an expense was logged. Used to solve the "Midnight Problem" by indicating when `spent_today` needs to automatically reset to 0.
* **`start_date`**: `Date` - The beginning date of the cycle.
* **`end_date`**: `Date` - The final date of the cycle.
* **`is_active`**: `Boolean` - A flag indicating whether this is the user's currently active cycle.

**Methods (Business Logic):**
* **`get_total_spent()`**: Returns the total spent by calculating `total_allowance - remaining_cycle_balance`.
* **`get_remaining_balance()`**: A getter method that simply returns the `remaining_cycle_balance`.
* **`calculate_daily_limit()`**: Calculates the dynamic safe daily limit (`remaining_cycle_balance / get_remaining_days()`). Automatically handles positive/negative rollover.
* **`get_remaining_days()`**: Calculates the days left between today and the `end_date` (returns a minimum of 1 to avoid division by zero).
* **`get_threshold_status()`**: Evaluates the percentage of the allowance spent and returns the corresponding `AllowanceStatus`.
* **`is_final_day()`**: Returns `True` if today's date matches the `end_date`, used to trigger the "final day" UI banner.
* **`get_remaining_today()`**: Powers the daily tracker. Calculates `calculate_daily_limit() - spent_today`. It internally checks `last_update_date` to treat `spent_today` as 0 if a new day has started.
* **`update_balance(amount)`**: Triggered when a new transaction is logged. Deducts the amount from `remaining_cycle_balance`, adds it to `spent_today`, and updates the `last_update_date`.
* **`clean()`**: An overridden Django method that acts as the model's internal validator. Enforces core SRS rules (e.g., `start_date` < `end_date`, and `total_allowance` > 0).

---

## 3. AllowanceStatus (Enum)
**Description & Responsibility:**
An enumeration that defines the specific alert thresholds required by the SRS for the dashboard UI.

**Values:**
* **`NORMAL`**: Usage is below 80%.
* **`HIGH_USAGE`**: Usage has crossed the 80% mark (triggers warning alert).
* **`LIMIT_REACHED`**: Usage has reached or exceeded 100% (triggers critical alert, suppressing the 80% alert if reached suddenly).

# Transaction Module - Class Descriptions

## 1. TransactionManager
**Description & Responsibility:**
A custom Django Manager responsible for querying the database for transactions. It handles the SRS requirement for "Filtering logs based on Categories or Dates".

**Methods:**
* **`get_by_category(cycle, category)`**: Returns a list of transactions belonging to a specific budget cycle filtered by the requested category.
* **`get_by_date(cycle, target_date)`**: Returns a list of transactions for a specific day.

---

## 2. Transaction (Model)
**Description & Responsibility:**
The data model representing a single logged expense. It is responsible for validating its own data (like the 10-digit limit) and notifying the `BudgetCycle` whenever it is created, updated, or deleted.

**Attributes (Stored Fields):**
* **`cycle`**: `ForeignKey(BudgetCycle)` - The budget cycle this expense belongs to. 
* **`amount`**: `Decimal` - The numeric value of the expense. *SRS Rule:* Must be strictly numeric and limited to 10 digits (e.g., `max_digits=10`, `decimal_places=2` in Django).
* **`category`**: `Category` - The classification of the expense.
* **`timestamp`**: `DateTime` - *SRS Rule:* Must record time. Handled automatically in Django via `auto_now_add=True`.
* **`note`**: `String` - An optional text description of the expense.

**Methods (Business Logic & Overrides):**
* **`clean()`**: Validates that the `amount` is greater than 0 and strictly numeric before allowing the database to save it. 
* **`save()`**: An overridden Django method. 
  * *Logic:* When a transaction is saved, it automatically calls `self.cycle.update_balance(amount)`. If the transaction is being *edited* (an existing record is changed), it calculates the difference between the old amount and the new amount and updates the cycle accordingly.
* **`delete()`**: An overridden Django method.
  * *Logic:* When an expense is deleted, it calls `self.cycle.update_balance(-amount)` (passing a negative number to "refund" the money back into the cycle's remaining balance).

---

## 3. Category
**Description & Responsibility:**
An enumeration of standard categories a user can choose from when logging an expense.
**Values:**
* **`FOOD`**
* **`TRANSPORT`**
* **`ENTERTRAINMENT`**
* **`BILLS`**
* **`OTHER`**
# User & Security Module - Class Descriptions

## 1. User (Model)
**Description & Responsibility:**
A custom Django model inheriting from Django's built-in `AbstractUser` by directly encapsulating the application's security logic—specifically the 4-digit PIN authentication, privacy lock toggles, and brute-force protection mechanisms.

**Inheritance:** Extends `django.contrib.auth.models.AbstractUser`.

**Attributes (Stored Fields):**
* **`hashed_pin`**: `String` - Stores the cryptographically hashed version of the user's 4-digit PIN. The raw PIN is never stored in plaintext.
* **`is_privacy_lock_enabled`**: `Boolean` - A user setting that toggles whether the application requires PIN entry upon launch.
* **`failed_attempts`**: `Integer` - A counter that tracks consecutive incorrect PIN entries to prevent brute-force attacks.

**Methods (Security Logic):**
* **`set_pin(raw_pin: String)`**: Hashes the provided 4-digit raw PIN and stores it in the `hashed_pin` attribute. Used during initial setup and PIN resets.
* **`verify_pin(raw_pin: String)`**: Hashes the inputted PIN and compares it against the stored `hashed_pin`. Returns `True` if they match, and `False` otherwise.
* **`record_failed_attempt()`**: Increments the `failed_attempts` counter by 1 when `verify_pin` returns `False`.
* **`reset_failed_attempts()`**: Resets the `failed_attempts` counter to 0 upon a successful PIN verification.

# View Layer (Controllers) - Class Descriptions

This section defines the Class-Based Views (CBVs) that drive the application's user interface. By inheriting from Django's built-in default views, these classes act as the controllers linking the UI templates to the underlying data models.

## Default Django Base Classes
These are standard Django classes that provide built-in HTTP handling. Our custom views inherit and override specific methods from these bases.
* **`TemplateView`**: Renders a static HTML page. Exposes `get_context_data()` to pass variables to the template.
* **`ListView`**: Designed to display a list of database records. Exposes `get_queryset()` to determine which records to fetch.
* **`FormView`**: Handles displaying and processing web forms. Exposes `form_valid()` to dictate what happens after successful form submission.

---

## 1. SetupView
**Inherits from:** `FormView`
**Description:** Manages the initial onboarding flow where a user configures their very first budget cycle.

**Attributes (Class Properties):**
* **`form_class`**: `BudgetCycleForm` - Points to the specific form class used to validate the user's start date, end date, and total allowance.
* **`template_name`**: `String` - The file path to the setup HTML template (e.g., `'setup.html'`).

**Methods:**
* **`form_valid(form)`**: Overrides default behavior. Upon a clean form submission, it processes the data to create a new `BudgetCycle` in the database.
* **`get_success_url()`**: Returns a `String` representing the URL route the user is redirected to (typically the Dashboard) after their cycle is successfully created.

---

## 2. DashboardView
**Inherits from:** `TemplateView`
**Description:** The primary hub for the user, rendering real-time tracking metrics, daily limits, and visual charts.

**Attributes (Class Properties):**
* **`template_name`**: `String` - The file path to the dashboard HTML template (e.g., `'dashboard.html'`).

**Methods:**
* **`get_context_data()`**: Retrieves the active `BudgetCycle` and injects its calculated properties (like remaining daily balance and status alerts) into a `Dictionary` for the template to display.
* **`post(request)`**: Overrides the default `TemplateView` behavior to accept incoming POST requests, specifically to handle "Quick Add" form submissions for logging an expense directly from the dashboard.
* **`generate_chart_data(cycle)`**: A private helper method that groups the cycle's transactions by category and outputs a `JSON` payload for the frontend charting library.

---

## 3. HistoryView
**Inherits from:** `ListView`
**Description:** Provides a scrollable, filterable ledger of all past transactions logged during the active cycle.

**Attributes (Class Properties):**
* **`model`**: `Transaction` - Instructs Django that this view is specifically querying the `Transaction` database table.
* **`template_name`**: `String` - The file path to the history HTML template (e.g., `'history.html'`).

**Methods:**
* **`get_queryset()`**: Overrides the default query. It reads the URL parameters (like a specific date or category) and returns a filtered `List<Transaction>` instead of the entire table.
* **`get_context_data()`**: Injects additional UI states into the context `Dictionary`, such as current active filter selections to highlight buttons on the frontend.
* **`post(request)`**: Overrides standard read-only behavior to process destructive actions, intercepting requests to edit or delete specific transactions directly from the ledger.

---

## 4. SettingsView
**Inherits from:** `FormView`
**Description:** The configuration hub for managing the user's security PIN and global account settings.

**Attributes (Class Properties):**
* **`form_class`**: `SettingsForm` - Points to the form class that validates new PIN entries and privacy toggle changes.
* **`template_name`**: `String` - The file path to the settings HTML template (e.g., `'settings.html'`).

**Methods:**
* **`get_context_data()`**: Reads the current user's security preferences (like privacy lock status) into a `Dictionary` to pre-fill the form toggles when the page loads.
* **`form_valid(form)`**: Triggered on successful form submission to securely update the user's PIN via the `User` model's hashing methods.
* **`post(request)`**: Contains custom logic to intercept specific, high-stakes POST requests, such as a user clicking the "Force Cycle Reset" button.

# Form Layer (Validation & Input) - Class Descriptions

In Django, Forms are dedicated classes responsible for handling user input, validating data types, and generating error messages before the data ever reaches the Model or the Database.

## Default Django Base Classes
* **`Form`**: The standard Django base class for handling web forms. It provides built-in mechanisms to validate data and return clean, safe Python objects.

---

## 1. BudgetCycleForm
**Inherits from:** `Form`
**Description & Responsibility:**
Validates the user input during the initial onboarding and budget setup phase. It ensures that the business rules are respected at the UI level before passing data to the `SetupView`.
**Core Validations:**
* Ensures the `total_allowance` is a positive number.
* Ensures the `end_date` strictly comes *after* the `start_date`.

## 2. SettingsForm
**Inherits from:** `Form`
**Description & Responsibility:**
Validates user input on the settings page, specifically handling the security constraints of the PIN system.
**Core Validations:**
* Ensures the new PIN consists of exactly 4 numeric digits.
* Validates that the "New PIN" and "Confirm PIN" inputs match perfectly before passing the data to the `SettingsView`.