from django.views.generic import ListView, FormView, CreateView, TemplateView
from django.views import View
from django.urls import reverse_lazy
from django.shortcuts import redirect
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView
from django.contrib import messages
from django.db.models import Sum
from decimal import Decimal, InvalidOperation
from django.core.exceptions import ValidationError
from django.http import HttpResponse, JsonResponse
from django.template.loader import render_to_string
import json

from .models import Transaction, BudgetCycle, Category, AllowanceStatus
from .forms import BudgetCycleForm, PinLoginForm, PinSignupForm
from .services import BudgetCycleService, TransactionMutationCommand, AccountService

class SetupView(LoginRequiredMixin, FormView):
    form_class = BudgetCycleForm
    template_name = 'budget/setup.html'
    
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and BudgetCycle.objects.filter(user=request.user, is_active=True).exists():
            return redirect('dashboard')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        try:
            BudgetCycleService.create_cycle(
                user=self.request.user,
                allowance=form.cleaned_data['total_allowance'],
                start_date=form.cleaned_data['start_date'],
                end_date=form.cleaned_data['end_date']
            )
            return redirect('dashboard')
        except ValidationError as e:
            form.add_error(None, e.message)
            return self.form_invalid(form)

class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'budget/dashboard.html'

    def dispatch(self, request, *args, **kwargs):
        self.active_cycle = BudgetCycle.objects.filter(user=request.user, is_active=True).first()
        if not self.active_cycle:
            return redirect('setup')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        metrics = BudgetCycleService.get_cycle_metrics(self.active_cycle)
        
        context.update(metrics)
        context['cycle'] = self.active_cycle
        context['categories'] = Category.choices
        
        if metrics['status'] == AllowanceStatus.LIMIT_REACHED:
            messages.error(self.request, "Budget exhausted! You have reached 100% of your allowance.")
        elif metrics['status'] == AllowanceStatus.HIGH_USAGE:
            messages.warning(self.request, "Warning! You have used 80% of your allowance.")

        results = Transaction.objects.filter(cycle=self.active_cycle).values('category').annotate(total=Sum('amount'))
        context['chart_data'] = json.dumps({
            'labels': [r['category'].capitalize() for r in results],
            'data': [float(r['total']) for r in results]
        })
        return context

    def post(self, request, *args, **kwargs):
        try:
            amount = Decimal(request.POST.get('amount'))
            category = request.POST.get('category')
            note = request.POST.get('note', '')
            
            TransactionMutationCommand.log(request.user, amount, category, note)
            
            if request.htmx:
                self.active_cycle.refresh_from_db()
                metrics = BudgetCycleService.get_cycle_metrics(self.active_cycle)
                
                response_html = f"""
                <div id="balance-card" hx-swap-oob="true" class="card">
                    <div style="font-size: 0.8rem; color: var(--text-muted);">Remaining Balance</div>
                    <div style="font-size: 2rem; font-family: var(--font-mono);">{metrics['remaining_balance']} EGP</div>
                </div>
                <div id="daily-card" hx-swap-oob="true" class="card">
                    <div style="font-size: 0.8rem; color: var(--text-muted);">Safe Daily Limit</div>
                    <div style="font-size: 2rem; font-family: var(--font-mono);">{round(metrics['daily_limit'], 2)} EGP</div>
                </div>
                <div id="toast-container" hx-swap-oob="true" style="margin-top: 1rem; font-size: 0.85rem; color: #4caf50;">
                    ✓ Transaction of {amount} EGP logged successfully.
                </div>
                <form hx-post="{reverse_lazy('dashboard')}" hx-swap="none" style="display: flex; gap: 1rem; align-items: center;" id="log-form" hx-swap-oob="true">
                    <input type="number" name="amount" id="quick-amount" class="input-dark" placeholder="0.00" min="0.01" step="0.01" required autofocus style="width: 120px;">
                    <select name="category" class="input-dark">
                        {''.join([f'<option value="{c[0]}">{c[1]}</option>' for c in Category.choices])}
                    </select>
                    <input type="text" name="note" class="input-dark" placeholder="Note (optional)" style="flex-grow: 1;">
                    <button type="submit" class="btn">Commit</button>
                </form>
                """
                return HttpResponse(response_html)
                
            messages.success(request, 'Expense logged successfully.')
        except (ValueError, TypeError, InvalidOperation, ValidationError) as e:
            if request.htmx:
                return HttpResponse(f'<div id="toast-container" hx-swap-oob="true" style="color: var(--accent-danger);">Error: Invalid amount.</div>')
            messages.error(request, 'Invalid amount.')
            
        return redirect('dashboard')

class TransactionDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk, *args, **kwargs):
        TransactionMutationCommand.delete(request.user, pk)
        if request.htmx:
            return HttpResponse("")
        return redirect('history')

class SettingsView(LoginRequiredMixin, TemplateView):
    template_name = 'budget/settings.html'

    def post(self, request, *args, **kwargs):
        action = request.POST.get('action')
        if action == 'wipe':
            AccountService.wipe_data(request.user)
            messages.success(request, "All data wiped.")
            return redirect('setup')
        elif action == 'export':
            data = AccountService.export_data(request.user)
            response = HttpResponse(data, content_type='application/json')
            response['Content-Disposition'] = 'attachment; filename="masroofy_export.json"'
            return response
        return redirect('settings')

class HistoryView(LoginRequiredMixin, ListView):
    model = Transaction
    template_name = 'budget/history.html'
    context_object_name = 'transactions'

    def dispatch(self, request, *args, **kwargs):
        self.active_cycle = BudgetCycle.objects.filter(user=request.user, is_active=True).first()
        if not self.active_cycle:
            return redirect('setup')
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        queryset = Transaction.objects.filter(cycle=self.active_cycle).order_by('-timestamp')
        
        category = self.request.GET.get('category')
        if category:
            queryset = queryset.filter(category=category)
            
        target_date = self.request.GET.get('date')
        if target_date:
            queryset = queryset.filter(timestamp__date=target_date)
            
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = Category.choices
        context['current_category'] = self.request.GET.get('category', '')
        context['current_date'] = self.request.GET.get('date', '')
        return context

class AppLoginView(LoginView):
    template_name = 'budget/login.html'
    authentication_form = PinLoginForm
    redirect_authenticated_user = True
    
    def get_success_url(self):
        if BudgetCycle.objects.filter(user=self.request.user, is_active=True).exists():
            return reverse_lazy('dashboard')
        return reverse_lazy('setup')

class AppSignupView(CreateView):
    form_class = PinSignupForm
    template_name = 'budget/signup.html'
    success_url = reverse_lazy('login')
    
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('dashboard')
        return super().dispatch(request, *args, **kwargs)
        
    def form_valid(self, form):
        messages.success(self.request, 'Account created successfully')
        return super().form_valid(form)