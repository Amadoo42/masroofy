from django.contrib import admin
from .models import User, BudgetCycle, Transaction

class BudgetCycleAdmin(admin.ModelAdmin):
    def save_model(self, request, obj, form, change):
        obj.full_clean()
        super().save_model(request, obj, form, change)

# Register your models here.
admin.site.register(User)
admin.site.register(BudgetCycle, BudgetCycleAdmin)
admin.site.register(Transaction)