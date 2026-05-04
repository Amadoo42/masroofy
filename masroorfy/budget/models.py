from django.db import models, transaction
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.hashers import make_password, check_password
from django.utils import timezone
from django.core.validators import RegexValidator

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
    email = models.EmailField(unique=True)
    username = models.CharField(
        max_length=150,
        unique=True,
        blank=True,
        null=True
    )
    
    pin_validator = RegexValidator(r'^\d{4}$', 'PIN must be exactly 4 digits.')
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']
    
    def __str__(self):
        return self.email

class BudgetCycleManager(models.Manager):
    def get_active_cycle(self, user):
        return self.filter(user=user, is_active=True).order_by('-start_date').first()

    def create_cycle(self, user, allowance, start, end):
        with transaction.atomic():
            self.filter(user=user, is_active=True).update(is_active=False)
            new_cycle = self.create(
                user=user,
                total_allowance = allowance,
                remaining_cycle_balance = allowance,
                spent_today = 0,
                start_date = start,
                end_date = end,
                is_active = True
            )
        return new_cycle

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
    
    def get_remaining_balance(self):
        return self.remaining_cycle_balance
    
    def calculate_daily_limit(self):
        if self.get_remaining_days() <= 0:
            return 0.00
        
        return self.get_remaining_balance() / self.get_remaining_days()
    
    def get_remaining_days(self):
        return (self.end_date - timezone.now().date()).days + 1
    
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