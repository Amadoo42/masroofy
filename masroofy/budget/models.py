from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator

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
    username = models.CharField(max_length=150, blank=False, null=False)
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']
    
    def __str__(self):
        return self.email

class BudgetCycle(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='budget_cycles')
    total_allowance = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)])
    remaining_cycle_balance = models.DecimalField(max_digits=10, decimal_places=2)
    spent_today = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    last_update_date = models.DateField(auto_now_add=True)
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=True)
    
class Transaction(models.Model):
    cycle = models.ForeignKey(BudgetCycle, on_delete=models.CASCADE, related_name='transactions')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    category = models.CharField(max_length=20, choices=Category.choices)
    timestamp = models.DateTimeField(auto_now_add=True)
    note = models.TextField(blank=True, null=True)

class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    message = models.CharField(max_length=255)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']