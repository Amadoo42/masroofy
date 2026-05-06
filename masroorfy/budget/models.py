from django.db import models, transaction
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from django.core.validators import RegexValidator, MinValueValidator
from decimal import Decimal
from django.core.exceptions import ValidationError

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
        blank=False,
        null=False
    )
    
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
    total_allowance = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)])
    remaining_cycle_balance = models.DecimalField(max_digits=10, decimal_places=2)
    spent_today = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    last_update_date = models.DateField(auto_now_add=True)
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=True)

    objects = BudgetCycleManager()

    def clean(self):
        if self.end_date <= self.start_date:
            raise ValidationError({'end_date': 'End date must be after start date.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    #TODO
    def get_total_spent(self):
        return self.total_allowance - self.remaining_cycle_balance
    
    def get_remaining_balance(self):
        return self.remaining_cycle_balance
    
    def calculate_daily_limit(self):
        if self.get_remaining_days() <= 0:
            return Decimal('0.00')
        
        return self.get_remaining_balance() / self.get_remaining_days()
    
    def get_remaining_days(self):
        return (self.end_date - timezone.localdate()).days + 1
    
    def get_threshold_status(self):
        total_spent = self.get_total_spent()
        use_percent = (total_spent / self.total_allowance) * 100
        if use_percent >= 100:
            return AllowanceStatus.LIMIT_REACHED
        elif use_percent >= 80:
            return AllowanceStatus.HIGH_USAGE
        else:
            return AllowanceStatus.NORMAL

    def is_final_day(self): pass
    def get_remaining_today(self):
        today = timezone.now().date()
        if today != self.last_update_date:
            spent_today = 0
        else:
            spent_today = self.spent_today
        return self.calculate_daily_limit() - spent_today
    
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