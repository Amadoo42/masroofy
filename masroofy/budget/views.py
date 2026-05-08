from django.views.generic import ListView, FormView, CreateView, TemplateView
from django.views import View
from django.urls import reverse_lazy
from django.shortcuts import redirect, render
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib import messages
from django.db.models import Sum
from decimal import Decimal, InvalidOperation
from django.core.exceptions import ValidationError
from django.http import HttpResponse
import json

from .models import Transaction, BudgetCycle, Category, Notification
from .forms import (
    BudgetCycleForm,
    PinLoginForm,
    PinSignupForm,
    AccountUpdateForm,
    ActiveCycleUpdateForm,
)
from .services import BudgetCycleService, TransactionMutationCommand, AccountService


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "budget/dashboard.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)

        self.active_cycle = BudgetCycle.objects.filter(
            user=request.user, is_active=True
        ).first()

        if not self.active_cycle:
            return redirect("setup")

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        metrics = BudgetCycleService.get_cycle_metrics(self.active_cycle)
        context.update(metrics)
        context["cycle"] = self.active_cycle
        context["categories"] = Category.choices
        context["recent_txs"] = Transaction.objects.filter(
            cycle=self.active_cycle
        ).order_by("-timestamp")[:5]

        results = (
            Transaction.objects.filter(cycle=self.active_cycle)
            .values("category")
            .annotate(total=Sum("amount"))
        )
        chart_data = {r["category"]: float(r["total"]) for r in results}
        context["chart_data_json"] = json.dumps(chart_data)

        context["unread_notifications"] = Notification.objects.filter(
            user=self.request.user, is_read=False
        )
        return context

    def post(self, request, *args, **kwargs):
        try:
            amount = Decimal(request.POST.get("amount"))
            category = request.POST.get("category")
            note = request.POST.get("note", "")
            TransactionMutationCommand.log(request.user, amount, category, note)
            if request.htmx:
                return HttpResponse(status=204, headers={"HX-Refresh": "true"})
            messages.success(request, "Expense logged successfully.")
        except (ValueError, TypeError, InvalidOperation, ValidationError):
            messages.error(request, "Invalid amount.")
        return redirect("dashboard")


class SettingsView(LoginRequiredMixin, TemplateView):
    template_name = "budget/settings.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if "account_form" not in context:
            context["account_form"] = AccountUpdateForm(instance=self.request.user)

        if "password_form" not in context:
            context["password_form"] = PasswordChangeForm(self.request.user)

        active_cycle = BudgetCycle.objects.filter(
            user=self.request.user, is_active=True
        ).first()

        if active_cycle and "cycle_form" not in context:
            context["cycle_form"] = ActiveCycleUpdateForm(instance=active_cycle)

        context["unread_notifications"] = Notification.objects.filter(
            user=self.request.user, is_read=False
        )
        return context

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action")
        user = request.user

        if action == "update_account":
            form = AccountUpdateForm(request.POST, instance=request.user)
            if form.is_valid():
                form.save()
                messages.success(request, "Account updated successfully.")
                return redirect("settings")
            return self.render_to_response(self.get_context_data(account_form=form))

        elif action == "update_password":
            form = PasswordChangeForm(request.user, request.POST)
            if form.is_valid():
                user = form.save()
                update_session_auth_hash(request, user)
                messages.success(request, "Password updated successfully.")
                return redirect("settings")
            return self.render_to_response(self.get_context_data(password_form=form))

        elif action == "update_cycle":
            active_cycle = BudgetCycle.objects.filter(
                user=request.user, is_active=True
            ).first()
            if active_cycle:
                old_allowance = active_cycle.total_allowance
                form = ActiveCycleUpdateForm(request.POST, instance=active_cycle)

                if form.is_valid():
                    new_allowance = form.cleaned_data["total_allowance"]
                    allowance_diff = new_allowance - old_allowance

                    cycle = form.save(commit=False)
                    cycle.remaining_cycle_balance += allowance_diff
                    cycle.save()
                    messages.success(request, "Budget cycle parameters updated.")
                    return redirect("settings")
                return self.render_to_response(self.get_context_data(cycle_form=form))

        elif action == "wipe":
            AccountService.wipe_data(request.user)
            messages.success(request, "All financial data wiped.")
            return redirect("setup")

        elif action == "export":
            data = AccountService.export_data(request.user)
            response = HttpResponse(data, content_type="application/json")
            response["Content-Disposition"] = (
                'attachment; filename="masroofy_export.json"'
            )
            return response

        return redirect("settings")


class NotificationReadView(LoginRequiredMixin, View):
    def post(self, request, pk, *args, **kwargs):
        Notification.objects.filter(id=pk, user=request.user).update(is_read=True)
        return HttpResponse("")


class SetupView(LoginRequiredMixin, FormView):
    form_class = BudgetCycleForm
    template_name = "budget/setup.html"

    def dispatch(self, request, *args, **kwargs):
        if (
            request.user.is_authenticated
            and BudgetCycle.objects.filter(user=request.user, is_active=True).exists()
        ):
            return redirect("dashboard")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        try:
            BudgetCycleService.create_cycle(
                user=self.request.user,
                allowance=form.cleaned_data["total_allowance"],
                start_date=form.cleaned_data["start_date"],
                end_date=form.cleaned_data["end_date"],
            )
            return redirect("dashboard")
        except ValidationError as e:
            form.add_error(None, e.message)
            return self.form_invalid(form)


class TransactionDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk, *args, **kwargs):
        TransactionMutationCommand.delete(request.user, pk)
        if request.htmx:
            return HttpResponse("")
        return redirect("history")


class TransactionEditView(LoginRequiredMixin, View):
    def get(self, request, pk, *args, **kwargs):
        tx = Transaction.objects.get(id=pk, cycle__user=request.user)
        if "cancel" in request.GET:
            return render(request, "budget/tx_row.html", {"tx": tx})
        return render(
            request,
            "budget/tx_edit_row.html",
            {"tx": tx, "categories": Category.choices},
        )

    def post(self, request, pk, *args, **kwargs):
        try:
            amount = Decimal(request.POST.get("amount"))
            category = request.POST.get("category")
            note = request.POST.get("note", "")
            tx = TransactionMutationCommand.edit(
                request.user, pk, amount, category, note
            )
            return render(request, "budget/tx_row.html", {"tx": tx})
        except (ValueError, TypeError, InvalidOperation, ValidationError) as e:
            return HttpResponse(str(e), status=400)


class TransactionDuplicateView(LoginRequiredMixin, View):
    def post(self, request, pk, *args, **kwargs):
        TransactionMutationCommand.duplicate(request.user, pk)
        if request.htmx:
            return HttpResponse(status=204, headers={"HX-Refresh": "true"})
        return redirect("history")


class HistoryView(LoginRequiredMixin, ListView):
    model = Transaction
    template_name = "budget/history.html"
    context_object_name = "transactions"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)

        self.active_cycle = BudgetCycle.objects.filter(
            user=request.user, is_active=True
        ).first()

        if not self.active_cycle:
            return redirect("setup")

        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        queryset = Transaction.objects.filter(cycle=self.active_cycle).order_by(
            "-timestamp"
        )

        category = self.request.GET.get("category")
        if category:
            queryset = queryset.filter(category=category)

        target_date = self.request.GET.get("date")
        if target_date:
            queryset = queryset.filter(timestamp__date=target_date)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["categories"] = Category.choices
        context["current_category"] = self.request.GET.get("category", "")
        context["current_date"] = self.request.GET.get("date", "")
        return context


class AppLoginView(LoginView):
    template_name = "budget/login.html"
    authentication_form = PinLoginForm
    redirect_authenticated_user = True

    def get_success_url(self):
        if BudgetCycle.objects.filter(user=self.request.user, is_active=True).exists():
            return reverse_lazy("dashboard")
        return reverse_lazy("setup")


class AppSignupView(CreateView):
    form_class = PinSignupForm
    template_name = "budget/signup.html"
    success_url = reverse_lazy("login")

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("dashboard")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        messages.success(self.request, "Account created successfully")
        return super().form_valid(form)
