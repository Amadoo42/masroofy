from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from decimal import Decimal
import json
from .models import BudgetCycle, Transaction, User, AllowanceStatus

class BudgetCycleService:
    @staticmethod
    def get_cycle_metrics(cycle: BudgetCycle) -> dict:
        """Computes O(1) read-only metrics dynamically for the active cycle."""
        today = timezone.localdate()
        days_remaining = max(1, (cycle.end_date - today).days + 1)
        
        spent_today = cycle.spent_today if cycle.last_update_date == today else Decimal('0.00')
        daily_limit = cycle.remaining_cycle_balance / Decimal(days_remaining)
        remaining_today = daily_limit - spent_today
        total_spent = cycle.total_allowance - cycle.remaining_cycle_balance
        
        use_percent = (total_spent / cycle.total_allowance) * 100 if cycle.total_allowance > 0 else 0
        if use_percent >= 100:
            status = AllowanceStatus.LIMIT_REACHED
        elif use_percent >= 80:
            status = AllowanceStatus.HIGH_USAGE
        else:
            status = AllowanceStatus.NORMAL

        return {
            'remaining_balance': cycle.remaining_cycle_balance,
            'daily_limit': daily_limit,
            'remaining_today': remaining_today,
            'status': status,
            'is_final_day': cycle.end_date == today
        }

    @staticmethod
    @transaction.atomic
    def create_cycle(user: User, allowance: Decimal, start_date, end_date) -> BudgetCycle:
        if end_date <= start_date:
            raise ValidationError("End date must be strictly after start date.")
            
        BudgetCycle.objects.filter(user=user, is_active=True).update(is_active=False)
        return BudgetCycle.objects.create(
            user=user,
            total_allowance=allowance,
            remaining_cycle_balance=allowance,
            spent_today=Decimal('0.00'),
            start_date=start_date,
            end_date=end_date,
            is_active=True
        )

    @staticmethod
    @transaction.atomic
    def reset_cycle(user: User) -> None:
        """Closes the active cycle without wiping historical data."""
        BudgetCycle.objects.filter(user=user, is_active=True).update(is_active=False)

class TransactionMutationCommand:
    @staticmethod
    @transaction.atomic
    def _mutate_balance(cycle: BudgetCycle, amount_delta: Decimal, tx_date) -> None:
        """Core engine for shifting balance. Uses select_for_update to prevent race conditions."""
        locked_cycle = BudgetCycle.objects.select_for_update().get(pk=cycle.pk)
        locked_cycle.remaining_cycle_balance -= amount_delta
        
        today = timezone.localdate()
        if tx_date == today:
            if locked_cycle.last_update_date != today:
                locked_cycle.spent_today = amount_delta
                locked_cycle.last_update_date = today
            else:
                locked_cycle.spent_today += amount_delta
                
        locked_cycle.save()

    @classmethod
    @transaction.atomic
    def log(cls, user: User, amount: Decimal, category: str, note: str = "") -> Transaction:
        cycle = BudgetCycle.objects.filter(user=user, is_active=True).first()
        if not cycle:
            raise ValidationError("No active budget cycle found.")
        if amount <= 0:
            raise ValidationError("Amount must be strictly positive.")
            
        tx = Transaction.objects.create(cycle=cycle, amount=amount, category=category, note=note)
        cls._mutate_balance(cycle, amount, tx.timestamp.date())
        return tx

    @classmethod
    @transaction.atomic
    def edit(cls, user: User, transaction_id: int, new_amount: Decimal, new_category: str, new_note: str) -> Transaction:
        tx = Transaction.objects.select_for_update().get(id=transaction_id, cycle__user=user)
        if new_amount <= 0:
            raise ValidationError("Amount must be strictly positive.")
            
        delta = new_amount - tx.amount
        tx.amount = new_amount
        tx.category = new_category
        tx.note = new_note
        tx.save()
        
        cls._mutate_balance(tx.cycle, delta, tx.timestamp.date())
        return tx

    @classmethod
    @transaction.atomic
    def delete(cls, user: User, transaction_id: int) -> None:
        tx = Transaction.objects.select_for_update().get(id=transaction_id, cycle__user=user)
        cls._mutate_balance(tx.cycle, -tx.amount, tx.timestamp.date())
        tx.delete()

    @classmethod
    @transaction.atomic
    def duplicate(cls, user: User, transaction_id: int) -> Transaction:
        source_tx = Transaction.objects.get(id=transaction_id, cycle__user=user)
        return cls.log(user, source_tx.amount, source_tx.category, f"{source_tx.note} (Copy)")

class AccountService:
    @staticmethod
    def export_data(user: User) -> str:
        """Returns all user financial data as a strictly formatted JSON payload."""
        cycles = BudgetCycle.objects.filter(user=user).prefetch_related('transactions')
        data = []
        for cycle in cycles:
            data.append({
                'start_date': str(cycle.start_date),
                'end_date': str(cycle.end_date),
                'allowance': str(cycle.total_allowance),
                'transactions': [
                    {'date': str(t.timestamp), 'amount': str(t.amount), 'category': t.category, 'note': t.note}
                    for t in cycle.transactions.all()
                ]
            })
        return json.dumps(data)

    @staticmethod
    @transaction.atomic
    def wipe_data(user: User) -> None:
        """Destructive action: Hard deletes all financial records for the user."""
        BudgetCycle.objects.filter(user=user).delete()