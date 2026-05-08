# Coding & Naming Conventions

All contributors must adhere to the following conventions to pass code reviews and maintain velocity.

## Git Workflow
* **Main Branch:** `main` (Production-ready, stable code only).
* **Development Branch:** `dev` (Integration branch for testing features together). All feature branches merge here first.
* **Feature Branches:** Create branches off `dev` using the format `category/snake_case`.
* *Categories:* `feature`, `bugfix`, `hotfix`, `refactor`, `docs`.
* *Example:* `feature/budget_cycle_model`

## Issue & Commit Prefixes
To keep our history and issue tracker clean, all commit messages and issue titles must start with one of the following prefixes:
* **`feat:`** A new feature or functionality.
* **`fix:`** A bug fix.
* **`styl:`** Changes that do not affect the meaning of the code (white-space, formatting, UI styling tweaks).
* **`refactor:`** A code change that neither fixes a bug nor adds a feature (e.g., optimizing an ORM query).
* **`docs:`** Documentation only changes (e.g., updating SDS diagrams or markdown files).
* **`chore:`** Changes to the build process, environment setup, or library updates.

## Naming Standards
| Target | Convention | Example |
| :--- | :--- | :--- |
| **Python Files/Modules** | snake_case | `views.py`, `budget_utils.py` |
| **HTML Templates** | snake_case | `dashboard_view.html`, `setup_form.html` |
| **Python Variables/Functions** | snake_case | `calculate_safe_limit()`, `active_cycle` |
| **Python Constants** | SCREAMING_SNAKE | `MAX_LOGIN_ATTEMPTS`, `TAX_RATE` |
| **Django Models/Classes** | PascalCase | `BudgetCycle`, `TransactionForm` |
| **CSS Classes** | kebab-case | `btn-primary`, `dashboard-card` |

## Django & Python Best Practices
1. **PEP 8 Compliance:** Follow standard Python formatting. 
2. **Fat Models, Skinny Views:** Keep business logic (like calculating limits or evaluating thresholds) inside the Django Models (`models.py`), keeping `views.py` clean and strictly for HTTP request/response routing.
3. **QuerySet Optimization:** Always use `select_related()` or `prefetch_related()` when querying foreign keys to avoid N+1 database hits.
4. **Environment Variables:** Never commit secrets. Use an `.env` file for your `SECRET_KEY` and database credentials.