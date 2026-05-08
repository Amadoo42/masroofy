import factory
from factory.django import DjangoModelFactory
from django.utils import timezone
from decimal import Decimal
import random

from .models import User, BudgetCycle, Transaction, Category


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"user_{n}")
    email = factory.Sequence(lambda n: f"user_{n}@example.com")


class BudgetCycleFactory(DjangoModelFactory):
    class Meta:
        model = BudgetCycle

    user = factory.SubFactory(UserFactory)
    total_allowance = Decimal("5000.00")
    remaining_cycle_balance = Decimal("5000.00")
    spent_today = Decimal("0.00")
    start_date = factory.LazyFunction(timezone.localdate)
    end_date = factory.LazyAttribute(
        lambda o: o.start_date + timezone.timedelta(days=30)
    )
    is_active = True


class TransactionFactory(DjangoModelFactory):
    class Meta:
        model = Transaction

    cycle = factory.SubFactory(BudgetCycleFactory)
    amount = factory.LazyFunction(
        lambda: Decimal(str(round(random.uniform(10.0, 500.0), 2)))
    )
    category = factory.Iterator([c[0] for c in Category.choices])
    note = factory.Faker("sentence")
