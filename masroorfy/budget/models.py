from django.db import models
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.hashers import make_password, check_password

class AllowanceStatus(models.TextChoices):
    NORMAL = 'NORMAL', 'Normal'
    HIGH_USAGE = 'HIGH_USAGE', 'High Usage'
    LIMIT_REACHED = 'LIMIT_REACHED', 'Limit Reached'

class Category(models.TextChoices):
    FOOD = 'FOOD', 'Food'
    TRANSPORT = 'TRANSPORT', 'Transport'
    ENTERTAINMENT = 'ENTERTAINMENT', 'Entertainment'
    BILLS = 'BILLS', 'Bills'
    OTHER = 'OTHER', 'Other'
    
class User(AbstractUser):
    hashed_pin = models.CharField(max_length=128, blank=True, null=True)
    is_privacy_lock_enabled = models.BooleanField(default=False)
    failed_attempts = models.IntegerField(default=0)

    def set_pin(self, raw_pin: str):
        self.hashed_pin = make_password(raw_pin)
        self.save()

    def verify_pin(self, raw_pin: str) -> bool:
        return check_password(raw_pin, self.hashed_pin)
    
    def record_failed_attempt(self):
        self.failed_attempts += 1
        self.save()

    def reset_failed_attempts(self):
        self.failed_attempts = 0
        self.save()

class BudgetCycleManager(models.Manager):
    def get_active_cycle(self, user):
        #TODO
        return self.filter(user=user, is_active=True).first()

    def create_cycle(self, user, allowance, start, end):
        #TODO
        pass

class BudgetCycle(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='budget_cycles')
    total_allowance = models.DecimalField(max_digits=10, decimal_places=2)
    remaining_cycle_balance = models.DecimalField(max_digits=10, decimal_places=2)
    spent_today = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    last_update_date = models.DateField(auto_now_add=True)
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=True)

    objects = BudgetCycleManager()

    #TODO
    def get_total_spent(self): pass
    def get_remaining_balance(self): pass
    def calculate_daily_limit(self): pass
    def get_remaining_days(self): pass
    def get_threshold_status(self): pass
    def is_final_day(self): pass
    def get_remaining_today(self): pass
    def update_balance(self, amount): pass

class TransactionManager(models.Manager):
    def get_by_category(self, cycle, category):
        return self.filter(cycle=cycle, category=category).order_by('-timestamp')
    
    def get_by_date(self, cycle, target_date):
        return self.filter(cycle=cycle, timestamp__date=target_date).order_by('-timestamp')
    
class Transaction(models.Model):
    cycle = models.ForeignKey(BudgetCycle, on_delete=models.CASCADE, related_name='transactions')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    category = models.CharField(max_length=20, choices=Category.choices)
    timestamp = models.DateTimeField(auto_now_add=True)
    note = models.TextField(blank=True, null=True)

    objects = TransactionManager()

    def clean(self):
        #TODO: validation logic
        pass

    def save(self, *args, **kwargs):
        #TODO: update_balance logic
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        #TODO: refund logic
        super().delete(*args, **kwargs)