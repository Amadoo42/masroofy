# Masroofy Refactor:
**Date:** May 8th, 2026

**Scope:** Core Backend Logic, UI/UX Delivery, and Testing Infrastructure

---

## Part 1: New Tech Stack

Before diving into the files, it is crucial that every team member understands the new tools and concepts introduced in this update. 

### 1. HTMX: The End of Page Reloads
In traditional web development, when you submit a form (like adding a new expense), the browser sends a request to the server, the server calculates everything, and then sends back an *entirely new HTML page*. The browser goes blank for a split second and redraws everything. 

**HTMX** is a modern tool that changes this. Instead of reloading the whole page, HTMX allows specific buttons or forms to send a request in the background. The server responds, and HTMX seamlessly "swaps" only a small piece of the screen.

### 2. HTTP Responses & Status 204
When the server finishes processing a request, it must tell the browser what happened using an **HTTP Status Code**. 
* `200 OK` means "Here is your data."
* `404 Not Found` means "I couldn't find what you asked for."

In our new architecture, when a user logs a transaction via HTMX, we process it and return an `HttpResponse(status=204)`. 
* **`204 No Content`**: This tells the browser, "I received your request, I processed it successfully, but I have no new HTML to show you right now." 
We pair this with a special header (`HX-Refresh: true`) which instructs HTMX to smoothly refresh the state of the dashboard without a jarring browser reload.

### 3. Property-Based Testing (Hypothesis)
Standard unit tests check specific, hard-coded scenarios (e.g., "If I add 5 and 5, do I get 10?"). 
**Property-based testing**, powered by a library called `hypothesis`, is much more advanced. Instead of hard-coding values, you define the *rules* (the properties). You tell Hypothesis: "Generate 1,000 random transaction amounts between 0.01 and 1000.00." Hypothesis will automatically throw insane edge cases at your code (like decimals, zero, massive numbers) to see if it can break your math. If your code survives, it is mathematically proven to be solid.

---

## Part 2: File-by-File Breakdown & Code Examples

### `masroofy/budget/services.py`
**The Decision:** Previously, our business logic (math, calculations, database updates) was mixed into our views. This makes code hard to test and dangerous. We implemented the **Strict Command Pattern**. All logic now lives in `services.py`.

**Key Concept: Database Locking (`select_for_update`)**
Imagine two users are logged into the same account on different phones, and they both try to log a 50 EGP expense at the exact same millisecond. If we aren't careful, the database might read the balance simultaneously and only deduct 50 once instead of 100. We use `@transaction.atomic` and `.select_for_update()` to "lock" the database row. The second phone must wait in line for the first phone to finish.

**Code Example:**
```python
class TransactionMutationCommand:
    @staticmethod
    @transaction.atomic
    def _mutate_balance(cycle: BudgetCycle, amount_delta: Decimal, tx_date) -> None:
        # 1. LOCK THE DATABASE ROW
        locked_cycle = BudgetCycle.objects.select_for_update().get(pk=cycle.pk)

        # 2. PERFORM MATH SAFELY
        locked_cycle.remaining_cycle_balance -= amount_delta
        
        # 3. SAVE TO DATABASE
        locked_cycle.save()

```

### `masroofy/budget/views.py`

**The Decision:** Because all logic moved to `services.py`, our views are now incredibly "thin". Their only job is to act as traffic controllers: receive the HTTP request, ask the Service to do the math, and return an HTTP Response.

**Code Example:**

```python
class DashboardView(LoginRequiredMixin, TemplateView):
    def post(self, request, *args, **kwargs):
        # 1. Extract data from the form
        amount = Decimal(request.POST.get("amount"))
        category = request.POST.get("category")
        
        # 2. Delegate to the Service (No math happens here!)
        TransactionMutationCommand.log(request.user, amount, category, "")
        
        # 3. Handle HTMX seamlessly
        if request.htmx:
            return HttpResponse(status=204, headers={"HX-Refresh": "true"})
        
        return redirect("dashboard")

```

### `masroofy/budget/tests.py`

**The Decision:** We replaced basic tests with high-tier mathematical proofs using `hypothesis`.

**Code Example:**

```python
from hypothesis import given
import hypothesis.strategies as st

class FinancialInvariantTests(HypothesisTestCase):
    # Tell Hypothesis to generate random lists of decimal amounts
    @given(
        amounts=st.lists(
            st.decimals(min_value=Decimal("0.01"), max_value=Decimal("1000.00"), places=2),
            min_size=1,
            max_size=20,
        )
    )
    def test_balance_invariant_under_load(self, amounts):
        # ... setup cycle ...
        total_spent = Decimal("0.00")
        for amount in amounts:
            TransactionMutationCommand.log(self.user, amount, "OTHER")
            total_spent += amount

        cycle.refresh_from_db()
        # Mathematically prove the balance is always correct regardless of inputs
        self.assertEqual(
            cycle.remaining_cycle_balance, cycle.total_allowance - total_spent
        )

```

### `masroofy/budget/templates/budget/base.html` (The UI System)

**The Decision:** We implemented a "Zen Mode" Minimalist Design System using Tailwind CSS. We abandoned traditional custom CSS files in favor of utility classes to ensure absolute pixel-perfect consistency across the app.

**How Styling Works Now:**
Instead of writing CSS like `.my-button { background: red; }`, we apply classes directly to the HTML: `class="bg-red-500"`.
To maintain a dark, professional aesthetic (similar to developer tools like Obsidian), we configured a custom color palette directly in the `base.html` header.

**Code Example (Tailwind Configuration):**

```html
<script id="tailwind-config">
    tailwind.config = {
        darkMode: "class",
        theme: {
            extend: {
                colors: {
                    "primary": "#007AFF", // Our specific blue accent
                    "surface-container-highest": "#353534",
                },
                fontFamily: {
                    // We use Inter for reading text, but JetBrains Mono for NUMBERS
                    // This ensures decimal points align perfectly in tables.
                    "heading": ["Inter"], 
                    "data-md": ["JetBrains Mono"] 
                }
            }
        }
    }
</script>

```

### `masroofy/budget/templates/budget/dashboard.html`

**The Decision:** Integrate HTMX directly into the front-end forms so the user never sees a loading screen when interacting with their budget.

**Code Example:**

```html
<form hx-post="{% url 'dashboard' %}" class="flex flex-col gap-4">
    {% csrf_token %}
    <div class="flex flex-col gap-1">
        <label class="font-label text-on-surface-variant uppercase">Amount (EGP)</label>
        
        <input type="number" name="amount" required 
               class="bg-black border border-[#333] p-2 font-data-md text-on-surface focus:border-primary w-full">
    </div>
    
    <button type="submit" class="btn-primary text-white font-label py-2 px-4 mt-2">
        Log Transaction
    </button>
</form>

```

---

## Summary for Future Development

1. **Adding a Feature?** Write the logic in `services.py` first. Do not put it in `views.py`.
2. **Changing the Database?** Ensure you lock the row with `select_for_update()` if it modifies a financial state like a budget limit.
3. **Adding a UI action?** Use `hx-post` or `hx-get` to make it a zero-reload interaction.
4. **Styling a new element?** Stick to the monochromatic `#0A0A0A` backgrounds and `#222` rigid borders defined in Tailwind. Use `JetBrains Mono` for any financial figures.