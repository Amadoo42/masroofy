from django.views.generic import ListView, FormView, CreateView, TemplateView
from django.shortcuts import redirect
from .models import Transaction, BudgetCycle, Category, AllowanceStatus
from .forms import BudgetCycleForm
from django.urls import reverse_lazy
from django.shortcuts import render, redirect
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView
from .forms import PinLoginForm, PinSignupForm
from django.contrib import messages
from django.db.models import Sum
import json
from decimal import Decimal, InvalidOperation
from django.core.exceptions import ValidationError


class HistoryView(LoginRequiredMixin, ListView):
    model = Transaction
    template_name = 'budget/history.html'
    context_object_name = 'transactions'

    def dispatch(self, request, *args, **kwargs):
        user = self.request.user
        if user.is_authenticated:
            if not BudgetCycle.objects.get_active_cycle(user):
                return redirect('setup')
        return super().dispatch(request, *args, **kwargs)

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

class SetupView(LoginRequiredMixin, FormView):
    form_class = BudgetCycleForm
    template_name = 'budget/setup.html'
    
    def form_valid(self, form):
        allowance = form.cleaned_data['total_allowance']
        start = form.cleaned_data['start_date']
        end = form.cleaned_data['end_date']
        
        BudgetCycle.objects.create_cycle(
            user=self.request.user,
            allowance=allowance,
            start=start,
            end=end
        )
        
        return super().form_valid(form)
    
    def dispatch(self, request, *args, **kwargs):
        user = self.request.user
        if user.is_authenticated:
            active_cycle = BudgetCycle.objects.get_active_cycle(user)
            if active_cycle:
                return redirect('dashboard')
        
        return super().dispatch(request, *args, **kwargs)
    
    def get_success_url(self):
        return reverse_lazy('dashboard')
    
class AppLoginView(LoginView):
    template_name = 'budget/login.html'
    authentication_form = PinLoginForm
    redirect_authenticated_user = True
    
    def get_success_url(self):
        user = self.request.user
        
        active_cycle = BudgetCycle.objects.get_active_cycle(user)
        
        if active_cycle:
            return reverse_lazy('dashboard')
        
        return reverse_lazy('setup')

class AppSignupView(CreateView):
    form_class = PinSignupForm
    template_name = 'budget/signup.html'
    success_url = reverse_lazy('login')
    
    def form_valid(self, form):
        messages.success(self.request, 'Account created successfully')
        return super().form_valid(form)
    
    def dispatch(self, request, *args, **kwargs):
        user = self.request.user
        if user.is_authenticated:
            return redirect('dashboard')
        
        return super().dispatch(request, *args, **kwargs)
            
class DashboardView(LoginRequiredMixin,TemplateView):

    template_name='budget/dashboard.html'

    def dispatch(self, request, *args, **kwargs):
        user = self.request.user
        if user.is_authenticated:
            if not BudgetCycle.objects.get_active_cycle(user):
                return redirect('setup')
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        self.cycle = BudgetCycle.objects.get_active_cycle(request.user)
        
        if self.cycle:
            status = self.cycle.get_threshold_status()
            if status == AllowanceStatus.LIMIT_REACHED:
                messages.error(self.request, "Budget exhausted! You have reached 100% of your allowance.")
            elif status == AllowanceStatus.HIGH_USAGE:
                messages.warning(self.request, "Warning! You have used 80% of your allowance.")
                
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cycle = getattr(self, 'cycle', None)
        
        if cycle:
            context['cycle'] = cycle
            context['remaining_balance'] = cycle.get_remaining_balance()
            context['daily_limit'] = cycle.calculate_daily_limit()
            context['chart_data'] = self.generate_chart_data(cycle)

        context['categories'] = Category.choices
        return context
    
    def generate_chart_data(self,cycle):

        results=(Transaction.objects
                .filter(cycle=cycle)
                .values('category')
                .annotate(total=Sum('amount'))
                )
        labels=[]
        data=[]

        for entry in results:
            labels.append(entry['category'].capitalize())
            data.append(float(entry['total']))
        return json.dumps({'labels':labels,'data':data})
      
    def post(self,request,*args,**kwargs):

        active_cycle= BudgetCycle.objects.get_active_cycle(self.request.user)

        if not active_cycle:
            return redirect('setup')
            
        amount= request.POST.get('amount')
        category=request.POST.get('category')
        note= request.POST.get('note','')

        try:
            amount= Decimal(amount)
            if amount <=0:
                raise ValueError
        except(ValueError, TypeError, InvalidOperation):
            messages.error(request,'Please enter a valid positive amount.')
            return redirect('dashboard')
        
        try:
            Transaction.objects.create(
                cycle=active_cycle,
                category=category,
                amount=amount,
                note=note   
            )
        except ValidationError as e:
            error_msg = " ".join([f"{msg}" for messages_list in e.message_dict.values() for msg in messages_list]) if hasattr(e, 'message_dict') else str(e)
            messages.error(request, f'Invalid submission: {error_msg}')
            return redirect('dashboard')
            
        messages.success(request,'Expense logged successfully.')
        return redirect('dashboard')