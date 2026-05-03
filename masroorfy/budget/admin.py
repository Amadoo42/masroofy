from django.contrib import admin
from .models import User, BudgetCycle, Transaction

# Register your models here.
admin.site.register(User)
admin.site.register(BudgetCycle)
admin.site.register(Transaction)