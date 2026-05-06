from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, BudgetCycle, Transaction

class CustomUserAdmin(UserAdmin):
    model = User
    list_display = ['username', 'email', 'is_staff', 'is_active']

class BudgetCycleAdmin(admin.ModelAdmin):
    def save_model(self, request, obj, form, change):
        obj.full_clean()
        super().save_model(request, obj, form, change)

admin.site.register(User, CustomUserAdmin)
admin.site.register(BudgetCycle, BudgetCycleAdmin)
admin.site.register(Transaction)