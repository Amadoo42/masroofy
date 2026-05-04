from django.views.generic import ListView, FormView, CreateView
from .models import Transaction, BudgetCycle, Category
from .forms import BudgetCycleForm
from django.urls import reverse_lazy
from django.shortcuts import render, redirect
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView
from .forms import PinLoginForm, PinSignupForm
from django.contrib import messages


class HistoryView(ListView):
    model = Transaction
    template_name = 'budget/history.html'
    context_object_name = 'transactions'

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return Transaction.objects.none()
        
        active_cycle = BudgetCycle.objects.get_active_cycle(user)
        if not active_cycle:
            return Transaction.objects.none()

        queryset = Transaction.objects.filter(cycle=active_cycle).order_by('-timestamp')

        category_filter = self.request.GET.get('category')
        date_filter = self.request.GET.get('date')

        if category_filter:
            queryset = Transaction.objects.get_by_category(active_cycle, category_filter)

        if date_filter:
            queryset = Transaction.objects.get_by_date(active_cycle, date_filter)

        return queryset
    
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
    redirect_authenticated_user = True
    
    def form_valid(self, form):
        messages.success(self.request, 'Account created successfully')
        return super().form_valid(form)
    
    def dispatch(self, request, *args, **kwargs):
        user = self.request.user
        if user.is_authenticated:
            return redirect('dashboard')
        
        return super().dispatch(request, *args, **kwargs)
    

def dashboard(request):
    return render(request, 'budget/dashboard.html')