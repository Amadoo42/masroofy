from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from decimal import Decimal
import json
from .models import BudgetCycle, Transaction, User, AllowanceStatus, Notification


class BudgetCycleService:
    @staticmethod
    def get_cycle_metrics(cycle: BudgetCycle) -> dict:
        today = timezone.localdate()
        total_days = max(1, (cycle.end_date - cycle.start_date).days)
        current_day = max(1, (today - cycle.start_date).days + 1)
        days_remaining = max(0, (cycle.end_date - today).days)

        spent_today = (
            cycle.spent_today if cycle.last_update_date == today else Decimal("0.00")
        )
        daily_limit = cycle.remaining_cycle_balance / Decimal(max(1, days_remaining))
        remaining_today = daily_limit - spent_today
        total_spent = cycle.total_allowance - cycle.remaining_cycle_balance

        use_percent = (
            (total_spent / cycle.total_allowance) * 100
            if cycle.total_allowance > 0
            else 0
        )
        if use_percent >= 100:
            status = AllowanceStatus.LIMIT_REACHED
        elif use_percent >= 80:
            status = AllowanceStatus.HIGH_USAGE
        else:
            status = AllowanceStatus.NORMAL

        return {
            "remaining_balance": cycle.remaining_cycle_balance,
            "daily_limit": daily_limit,
            "remaining_today": remaining_today,
            "total_spent": total_spent,
            "use_percent": min(100, use_percent),
            "current_day": current_day,
            "total_days": total_days,
            "days_remaining": days_remaining,
            "status": status,
            "is_final_day": cycle.end_date == today,
        }

    @staticmethod
    @transaction.atomic
    def create_cycle(
        user: User, allowance: Decimal, start_date, end_date
    ) -> BudgetCycle:
        if end_date <= start_date:
            raise ValidationError("End date must be strictly after start date.")

        BudgetCycle.objects.filter(user=user, is_active=True).update(is_active=False)
        return BudgetCycle.objects.create(
            user=user,
            total_allowance=allowance,
            remaining_cycle_balance=allowance,
            spent_today=Decimal("0.00"),
            start_date=start_date,
            end_date=end_date,
            is_active=True,
        )


class TransactionMutationCommand:
    @staticmethod
    @transaction.atomic
    def _mutate_balance(cycle: BudgetCycle, amount_delta: Decimal, tx_date) -> None:
        locked_cycle = BudgetCycle.objects.select_for_update().get(pk=cycle.pk)

        pre_metrics = BudgetCycleService.get_cycle_metrics(locked_cycle)

        locked_cycle.remaining_cycle_balance -= amount_delta
        today = timezone.localdate()
        if tx_date == today:
            if locked_cycle.last_update_date != today:
                locked_cycle.spent_today = amount_delta
                locked_cycle.last_update_date = today
            else:
                locked_cycle.spent_today += amount_delta
        locked_cycle.save()

        post_metrics = BudgetCycleService.get_cycle_metrics(locked_cycle)
        if (
            pre_metrics["status"] != AllowanceStatus.LIMIT_REACHED
            and post_metrics["status"] == AllowanceStatus.LIMIT_REACHED
        ):
            Notification.objects.create(
                user=cycle.user,
                message="Budget exhausted! You have reached 100% of your cycle allowance.",
            )
        elif (
            pre_metrics["status"] == AllowanceStatus.NORMAL
            and post_metrics["status"] == AllowanceStatus.HIGH_USAGE
        ):
            Notification.objects.create(
                user=cycle.user,
                message="Warning: You have utilized over 80% of your cycle budget.",
            )

    @classmethod
    @transaction.atomic
    def log(
        cls, user: User, amount: Decimal, category: str, note: str = ""
    ) -> Transaction:
        cycle = BudgetCycle.objects.filter(user=user, is_active=True).first()
        if not cycle:
            raise ValidationError("No active budget cycle found.")
        if amount <= 0:
            raise ValidationError("Amount must be strictly positive.")

        tx = Transaction.objects.create(
            cycle=cycle, amount=amount, category=category, note=note
        )
        cls._mutate_balance(cycle, amount, tx.timestamp.date())
        return tx

    @classmethod
    @transaction.atomic
    def delete(cls, user: User, transaction_id: int) -> None:
        tx = Transaction.objects.select_for_update().get(
            id=transaction_id, cycle__user=user
        )
        cls._mutate_balance(tx.cycle, -tx.amount, tx.timestamp.date())
        tx.delete()

    @classmethod
    @transaction.atomic
    def edit(
        cls,
        user: User,
        transaction_id: int,
        amount: Decimal,
        category: str,
        note: str = "",
    ) -> Transaction:
        tx = Transaction.objects.select_for_update().get(
            id=transaction_id, cycle__user=user
        )
        if amount <= 0:
            raise ValidationError("Amount must be strictly positive.")

        cls._mutate_balance(tx.cycle, -tx.amount, tx.timestamp.date())

        tx.amount = amount
        tx.category = category
        tx.note = note
        tx.save()
        cls._mutate_balance(tx.cycle, amount, tx.timestamp.date())
        return tx

    @classmethod
    @transaction.atomic
    def duplicate(cls, user: User, transaction_id: int) -> Transaction:
        tx = Transaction.objects.get(id=transaction_id, cycle__user=user)
        new_note = f"{tx.note} (Copy)" if tx.note else "(Copy)"
        return cls.log(user, tx.amount, tx.category, new_note)


class AccountService:
    @staticmethod
    def export_data(user: User) -> str:
        cycles = BudgetCycle.objects.filter(user=user).prefetch_related("transactions")
        data = [
            {
                "start_date": str(c.start_date),
                "end_date": str(c.end_date),
                "allowance": str(c.total_allowance),
                "transactions": [
                    {
                        "date": str(t.timestamp),
                        "amount": str(t.amount),
                        "category": t.category,
                        "note": t.note,
                    }
                    for t in c.transactions.all()
                ],
            }
            for c in cycles
        ]
        return json.dumps(data)

    @staticmethod
    @transaction.atomic
    def wipe_data(user: User) -> None:
        BudgetCycle.objects.filter(user=user).delete()
        Notification.objects.filter(user=user).delete()
