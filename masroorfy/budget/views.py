from django.views.generic import ListView
from .models import Transaction, BudgetCycle, Category
from django.contrib.auth.mixins import LoginRequiredMixin

class HistoryView(LoginRequiredMixin, ListView):
    model = Transaction
    template_name = 'budget/history.html'
    context_object_name = 'transactions'

    def get_queryset(self):
        user = self.request.user
        
        active_cycle = BudgetCycle.objects.get_active_cycle(user)

        queryset = Transaction.objects.filter(cycle=active_cycle)

        category_filter = self.request.GET.get('category')
        date_filter = self.request.GET.get('date')

        if category_filter:
            queryset = queryset & Transaction.objects.get_by_category(active_cycle, category_filter)

        if date_filter:
            queryset = queryset & Transaction.objects.get_by_date(active_cycle, date_filter)

        return queryset.order_by('-timestamp')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = Category.choices
        context['current_category'] = self.request.GET.get('category', '')
        context['current_date'] = self.request.GET.get('date', '')
        return context