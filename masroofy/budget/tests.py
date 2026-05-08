from django.test import TestCase, Client, RequestFactory
from django.urls import reverse
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth.models import AnonymousUser
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import update_session_auth_hash
from decimal import Decimal
from unittest.mock import patch
import json

from hypothesis import given, settings
from hypothesis.extra.django import TestCase as HypothesisTestCase
import hypothesis.strategies as st

from .models import BudgetCycle, Transaction, User, AllowanceStatus, Notification
from .services import BudgetCycleService, TransactionMutationCommand, AccountService
from .factories import UserFactory, BudgetCycleFactory, TransactionFactory
from .forms import BudgetCycleForm, PinSignupForm, AccountUpdateForm, ActiveCycleUpdateForm
from .context_processors import notification_processor
from .admin import BudgetCycleAdmin

class AdditionalCoverageTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = UserFactory()
    
    def test_notification_processor_anonymous(self):
        request = self.factory.get('/')
        request.user = AnonymousUser()
        result = notification_processor(request)
        self.assertEqual(result, {'unread_notifications': []})

    def test_user_str(self):
        self.assertEqual(str(self.user), self.user.email)

    def test_budget_cycle_admin_save(self):
        site = AdminSite()
        admin = BudgetCycleAdmin(BudgetCycle, site)
        cycle = BudgetCycle(user=self.user, total_allowance=1000, remaining_cycle_balance=1000, start_date=timezone.localdate(), end_date=timezone.localdate() + timezone.timedelta(days=10))
        request = self.factory.get('/')
        admin.save_model(request, cycle, None, False)
        self.assertIsNotNone(cycle.pk)

class FormCoverageTests(TestCase):
    def setUp(self):
        self.user = UserFactory()

    def test_budget_cycle_form_invalid_dates(self):
        form = BudgetCycleForm(data={
            'total_allowance': '1000',
            'start_date': timezone.localdate(),
            'end_date': timezone.localdate() - timezone.timedelta(days=1)
        })
        self.assertFalse(form.is_valid())
        self.assertTrue(any("after the start date" in e for e in form.errors.get('__all__', [])))

    def test_pin_signup_form_clean_username(self):
        form = PinSignupForm(data={
            'email': 'test@test.com',
            'username': 'testuser',
            'password1': '1234',
            'password2': '1234'
        })
        self.assertTrue(form.is_valid())
        self.assertEqual(form.clean_username(), 'testuser')

    def test_active_cycle_update_form_invalid_dates(self):
        form = ActiveCycleUpdateForm(data={
            'total_allowance': '1000',
            'start_date': timezone.localdate(),
            'end_date': timezone.localdate() - timezone.timedelta(days=1)
        })
        self.assertFalse(form.is_valid())

    def test_account_update_form_meta(self):
        form = AccountUpdateForm()
        self.assertIn('username', form.fields)

class FinancialInvariantTests(HypothesisTestCase):
    def setUp(self):
        self.user = UserFactory()

    @given(amounts=st.lists(st.decimals(min_value=Decimal('0.01'), max_value=Decimal('1000.00'), places=2), min_size=1, max_size=20))
    def test_balance_invariant_under_load(self, amounts):
        cycle = BudgetCycleService.create_cycle(
            user=self.user,
            allowance=Decimal('10000.00'),
            start_date=timezone.localdate(),
            end_date=timezone.localdate() + timezone.timedelta(days=30)
        )
        total_spent = Decimal('0.00')
        for amount in amounts:
            TransactionMutationCommand.log(self.user, amount, 'OTHER', 'Stress Test')
            total_spent += amount

        cycle.refresh_from_db()
        self.assertEqual(cycle.remaining_cycle_balance, cycle.total_allowance - total_spent)
        
        BudgetCycle.objects.all().delete()
        Transaction.objects.all().delete()

class TemporalRolloverTests(TestCase):
    def setUp(self):
        self.user = UserFactory()
        self.cycle = BudgetCycleService.create_cycle(
            user=self.user, allowance=Decimal('5000.00'),
            start_date=timezone.localdate() - timezone.timedelta(days=5),
            end_date=timezone.localdate() + timezone.timedelta(days=25)
        )

    def test_retroactive_transaction_does_not_corrupt_daily_tracker(self):
        initial_balance = self.cycle.remaining_cycle_balance
        past_date = timezone.localdate() - timezone.timedelta(days=2)
        
        tx = Transaction.objects.create(cycle=self.cycle, amount=Decimal('500.00'), category='FOOD')
        tx.timestamp = timezone.now() - timezone.timedelta(days=2)
        tx.save()
        
        TransactionMutationCommand._mutate_balance(self.cycle, Decimal('500.00'), past_date)
        self.cycle.refresh_from_db()
        self.assertEqual(self.cycle.remaining_cycle_balance, initial_balance - Decimal('500.00'))
        self.assertEqual(self.cycle.spent_today, Decimal('0.00'))

    def test_validation_boundaries(self):
        with self.assertRaisesRegex(ValidationError, "positive"):
            TransactionMutationCommand.log(self.user, Decimal('-50.00'), 'FOOD')
        with self.assertRaisesRegex(ValidationError, "positive"):
            TransactionMutationCommand.log(self.user, Decimal('0.00'), 'FOOD')

        tx = TransactionMutationCommand.log(self.user, Decimal('50.00'), 'FOOD')
        with self.assertRaisesRegex(ValidationError, "positive"):
            TransactionMutationCommand.edit(self.user, tx.id, Decimal('-10.00'), 'FOOD')

        with self.assertRaisesRegex(ValidationError, "strictly after"):
            BudgetCycleService.create_cycle(self.user, Decimal('1000'), timezone.localdate(), timezone.localdate())

class ExtendedServiceTests(TestCase):
    def setUp(self):
        self.user = UserFactory()
        self.cycle = BudgetCycleService.create_cycle(
            user=self.user, allowance=Decimal('2000.00'),
            start_date=timezone.localdate(), end_date=timezone.localdate() + timezone.timedelta(days=10)
        )

    def test_edit_transaction(self):
        tx = TransactionMutationCommand.log(self.user, Decimal('100.00'), 'FOOD', 'Lunch')
        edited_tx = TransactionMutationCommand.edit(self.user, tx.id, Decimal('150.00'), 'FOOD', 'Big Lunch')
        self.cycle.refresh_from_db()
        self.assertEqual(edited_tx.amount, Decimal('150.00'))
        self.assertEqual(self.cycle.remaining_cycle_balance, Decimal('1850.00'))

    def test_duplicate_transaction(self):
        tx = TransactionMutationCommand.log(self.user, Decimal('200.00'), 'BILLS', 'Internet')
        dup_tx = TransactionMutationCommand.duplicate(self.user, tx.id)
        self.cycle.refresh_from_db()
        self.assertEqual(dup_tx.amount, Decimal('200.00'))
        self.assertEqual(self.cycle.remaining_cycle_balance, Decimal('1600.00'))

    def test_get_cycle_metrics_thresholds(self):
        TransactionMutationCommand.log(self.user, Decimal('2000.00'), 'OTHER')
        self.assertTrue(Notification.objects.filter(message__contains="Budget exhausted").exists())

    def test_notification_on_high_usage(self):
        TransactionMutationCommand.log(self.user, Decimal('1601.00'), 'OTHER')
        self.assertTrue(
            Notification.objects.filter(message__contains="utilized over 80%").exists()
        )

    def test_daily_limit_overspent(self):
        TransactionMutationCommand.log(self.user, Decimal('250.00'), 'OTHER')
        self.cycle.refresh_from_db()
        metrics = BudgetCycleService.get_cycle_metrics(self.cycle)
        self.assertLess(metrics['remaining_today'], 0)

    def test_is_final_day_metric(self):
        self.cycle.end_date = timezone.localdate()
        self.cycle.save()
        self.cycle.refresh_from_db()
        metrics = BudgetCycleService.get_cycle_metrics(self.cycle)
        self.assertTrue(metrics['is_final_day'])

    def test_log_transaction_no_active_cycle(self):
        self.cycle.is_active = False
        self.cycle.save()
        with self.assertRaisesRegex(ValidationError, "No active budget cycle found"):
            TransactionMutationCommand.log(self.user, Decimal('10.00'), 'OTHER')

    def test_account_service_export_and_wipe(self):
        TransactionMutationCommand.log(self.user, Decimal('50.00'), 'FOOD', 'Snack')
        data_json = AccountService.export_data(self.user)
        parsed = json.loads(data_json)
        self.assertEqual(len(parsed), 1)
        AccountService.wipe_data(self.user)
        self.assertEqual(BudgetCycle.objects.filter(user=self.user).count(), 0)

class ViewIntegrationTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='testuser', email='test@test.com', password='password123')
        self.client.login(email='test@test.com', password='password123')

    def test_setup_view_redirects_if_active(self):
        BudgetCycleService.create_cycle(
            user=self.user, allowance=Decimal('1000'),
            start_date=timezone.localdate(), end_date=timezone.localdate() + timezone.timedelta(days=10)
        )
        response = self.client.get(reverse('setup'))
        self.assertRedirects(response, reverse('dashboard'))

    def test_dashboard_post_standard(self):
        BudgetCycleService.create_cycle(
            user=self.user, allowance=Decimal('1000'),
            start_date=timezone.localdate(), end_date=timezone.localdate() + timezone.timedelta(days=10)
        )
        response = self.client.post(reverse('dashboard'), {
            'amount': '150.00', 'category': 'FOOD', 'note': 'Dinner'
        })
        self.assertRedirects(response, reverse('dashboard'))
        self.assertEqual(Transaction.objects.count(), 1)

    def test_dashboard_post_htmx(self):
        BudgetCycleService.create_cycle(
            user=self.user, allowance=Decimal('1000'),
            start_date=timezone.localdate(), end_date=timezone.localdate() + timezone.timedelta(days=10)
        )
        response = self.client.post(reverse('dashboard'), {
            'amount': '50.00', 'category': 'TRANSPORT', 'note': 'Uber'
        }, HTTP_HX_REQUEST='true')
        
        self.assertEqual(response.status_code, 204)
        self.assertEqual(Transaction.objects.count(), 1)

    def test_history_filters(self):
        cycle = BudgetCycleService.create_cycle(
            user=self.user, allowance=Decimal('1000'),
            start_date=timezone.localdate(), end_date=timezone.localdate() + timezone.timedelta(days=10)
        )
        TransactionMutationCommand.log(self.user, Decimal('100'), 'FOOD')
        TransactionMutationCommand.log(self.user, Decimal('50'), 'BILLS')

        response = self.client.get(reverse('history'), {'category': 'FOOD'})
        self.assertEqual(len(response.context['transactions']), 1)
        self.assertEqual(response.context['transactions'][0].category, 'FOOD')

    def test_transaction_delete_standard_post(self):
        cycle = BudgetCycleService.create_cycle(self.user, Decimal('1000'), timezone.localdate(), timezone.localdate() + timezone.timedelta(days=10))
        tx = TransactionMutationCommand.log(self.user, Decimal('100'), 'FOOD')
        response = self.client.post(reverse('transaction_delete', args=[tx.id]))
        self.assertRedirects(response, reverse('history'))

    def test_transaction_delete_htmx(self):
        cycle = BudgetCycleService.create_cycle(
            user=self.user, allowance=Decimal('1000'),
            start_date=timezone.localdate(), end_date=timezone.localdate() + timezone.timedelta(days=10)
        )
        tx = TransactionMutationCommand.log(self.user, Decimal('100'), 'FOOD')
        
        response = self.client.post(reverse('transaction_delete', args=[tx.id]), HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Transaction.objects.count(), 0)

    def test_settings_export_and_wipe(self):
        cycle = BudgetCycleService.create_cycle(
            user=self.user, allowance=Decimal('1000'),
            start_date=timezone.localdate(), end_date=timezone.localdate() + timezone.timedelta(days=10)
        )
        
        response_export = self.client.post(reverse('settings'), {'action': 'export'})
        self.assertEqual(response_export['Content-Disposition'], 'attachment; filename="masroofy_export.json"')
        
        response_wipe = self.client.post(reverse('settings'), {'action': 'wipe'})
        self.assertRedirects(response_wipe, reverse('setup'))
        self.assertEqual(BudgetCycle.objects.count(), 0)

    def test_notification_read(self):
        notification = Notification.objects.create(user=self.user, message="Budget Warning")
        response = self.client.post(reverse('notification_read', args=[notification.id]))
        self.assertEqual(response.status_code, 200)
        
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)

    def test_dashboard_no_active_cycle(self):
        response = self.client.get(reverse('dashboard'))
        self.assertRedirects(response, reverse('setup'))

    def test_dashboard_invalid_post(self):
        BudgetCycleService.create_cycle(self.user, Decimal('1000'), timezone.localdate(), timezone.localdate() + timezone.timedelta(days=10))
        response = self.client.post(reverse('dashboard'), {
            'amount': 'invalid', 'category': 'FOOD', 'note': ''
        })
        self.assertRedirects(response, reverse('dashboard'))

    def test_settings_update_account(self):
        BudgetCycleService.create_cycle(self.user, Decimal('1000'), timezone.localdate(), timezone.localdate() + timezone.timedelta(days=10))
        response = self.client.post(reverse('settings'), {
            'action': 'update_account',
            'username': 'newuser',
            'email': 'new@test.com'
        })
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, 'newuser')

    def test_settings_update_password_success(self):
        response = self.client.post(reverse('settings'), {
            'action': 'update_password',
            'old_password': 'password123',
            'new_password1': 'newpass1234',
            'new_password2': 'newpass1234'
        })
        self.assertRedirects(response, reverse('settings'))
        self.assertTrue(self.client.login(email='test@test.com', password='newpass1234'))

    def test_settings_update_password_invalid(self):
        response = self.client.post(reverse('settings'), {
            'action': 'update_password',
        })
        self.assertRedirects(response, reverse('settings'))

    def test_settings_update_cycle(self):
        cycle = BudgetCycleService.create_cycle(self.user, Decimal('1000'), timezone.localdate(), timezone.localdate() + timezone.timedelta(days=10))
        response = self.client.post(reverse('settings'), {
            'action': 'update_cycle',
            'total_allowance': '2000.00',
            'start_date': cycle.start_date,
            'end_date': cycle.end_date
        })
        cycle.refresh_from_db()
        self.assertEqual(cycle.total_allowance, Decimal('2000.00'))

    def test_settings_update_cycle_invalid(self):
        cycle = BudgetCycleService.create_cycle(self.user, Decimal('1000'), timezone.localdate(), timezone.localdate() + timezone.timedelta(days=10))
        response = self.client.post(reverse('settings'), {
            'action': 'update_cycle',
            'total_allowance': '2000.00',
            'start_date': cycle.start_date,
            'end_date': cycle.start_date - timezone.timedelta(days=1)
        })
        cycle.refresh_from_db()
        self.assertEqual(cycle.total_allowance, Decimal('1000.00'))

    def test_settings_empty_action(self):
        BudgetCycleService.create_cycle(self.user, Decimal('1000'), timezone.localdate(), timezone.localdate() + timezone.timedelta(days=10))
        response = self.client.post(reverse('settings'), {})
        self.assertRedirects(response, reverse('settings'))

    def test_transaction_edit_get_standard(self):
        cycle = BudgetCycleService.create_cycle(self.user, Decimal('1000'), timezone.localdate(), timezone.localdate() + timezone.timedelta(days=10))
        tx = TransactionMutationCommand.log(self.user, Decimal('100'), 'FOOD')
        response = self.client.get(reverse('transaction_edit', args=[tx.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'budget/tx_edit_row.html')

    def test_transaction_edit_get_cancel(self):
        cycle = BudgetCycleService.create_cycle(self.user, Decimal('1000'), timezone.localdate(), timezone.localdate() + timezone.timedelta(days=10))
        tx = TransactionMutationCommand.log(self.user, Decimal('100'), 'FOOD')
        response = self.client.get(reverse('transaction_edit', args=[tx.id]), {'cancel': 'true'})
        self.assertEqual(response.status_code, 200)

    def test_transaction_edit_post_success(self):
        cycle = BudgetCycleService.create_cycle(self.user, Decimal('1000'), timezone.localdate(), timezone.localdate() + timezone.timedelta(days=10))
        tx = TransactionMutationCommand.log(self.user, Decimal('100'), 'FOOD')
        response = self.client.post(reverse('transaction_edit', args=[tx.id]), {
            'amount': '150.00',
            'category': 'TRANSPORT',
            'note': 'Update'
        })
        self.assertEqual(response.status_code, 200)
        tx.refresh_from_db()
        self.assertEqual(tx.amount, Decimal('150.00'))

    def test_transaction_edit_post_invalid(self):
        cycle = BudgetCycleService.create_cycle(self.user, Decimal('1000'), timezone.localdate(), timezone.localdate() + timezone.timedelta(days=10))
        tx = TransactionMutationCommand.log(self.user, Decimal('100'), 'FOOD')
        response = self.client.post(reverse('transaction_edit', args=[tx.id]), {
            'amount': 'invalid', 'category': 'FOOD', 'note': ''
        })
        self.assertEqual(response.status_code, 400)

    def test_history_no_active_cycle(self):
        response = self.client.get(reverse('history'))
        self.assertRedirects(response, reverse('setup'))

    def test_history_filter_date(self):
        cycle = BudgetCycleService.create_cycle(self.user, Decimal('1000'), timezone.localdate(), timezone.localdate() + timezone.timedelta(days=10))
        tx = TransactionMutationCommand.log(self.user, Decimal('100'), 'FOOD')
        response = self.client.get(reverse('history'), {'date': str(tx.timestamp.date())})
        self.assertEqual(len(response.context['transactions']), 1)

    def test_setup_view_success(self):
        response = self.client.post(reverse('setup'), {
            'total_allowance': '1000',
            'start_date': str(timezone.localdate()),
            'end_date': str(timezone.localdate() + timezone.timedelta(days=30))
        })
        self.assertRedirects(response, reverse('dashboard'))

    def test_setup_invalid_post(self):
        response = self.client.post(reverse('setup'), {
            'total_allowance': '1000',
            'start_date': timezone.localdate(),
            'end_date': timezone.localdate() - timezone.timedelta(days=1)
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('end date must be after', str(response.context['form'].errors))

    @patch('budget.services.BudgetCycleService.create_cycle')
    def test_setup_service_error(self, mock_create):
        mock_create.side_effect = ValidationError("Service error")
        response = self.client.post(reverse('setup'), {
            'total_allowance': '1000',
            'start_date': timezone.localdate(),
            'end_date': timezone.localdate() + timezone.timedelta(days=10)
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn("Service error", str(response.context['form'].errors))

    def test_app_signup_authenticated(self):
        BudgetCycleService.create_cycle(
            self.user, 
            Decimal('1000'), 
            timezone.localdate(), 
            timezone.localdate() + timezone.timedelta(days=10)
        )

        response = self.client.get(reverse('signup'))
        self.assertRedirects(response, reverse('dashboard'))

    def test_app_signup_valid(self):
        self.client.logout()
        response = self.client.post(reverse('signup'), {
            'email': 'new2@test.com',
            'username': 'newuser2',
            'password1': '1234',
            'password2': '1234'
        })
        self.assertRedirects(response, reverse('login'))

    def test_dashboard_redirects_to_setup_when_no_cycle_exists(self):
        BudgetCycle.objects.filter(user=self.user).delete()
        response = self.client.get(reverse('dashboard'))
        self.assertRedirects(response, reverse('setup'))

    def test_app_login_redirect_active_cycle(self):
        BudgetCycleService.create_cycle(
            self.user, Decimal('1000'), 
            timezone.localdate(), 
            timezone.localdate() + timezone.timedelta(days=10)
        )
        self.client.logout()
        response = self.client.post(reverse('login'), {
            'username': 'test@test.com',
            'password': 'password123'
        })
        self.assertRedirects(response, reverse('dashboard'))

    def test_app_login_redirect_no_active_cycle(self):
        BudgetCycle.objects.filter(user=self.user).delete()
        self.client.logout()
        
        response = self.client.post(reverse('login'), {
            'username': 'test@test.com',
            'password': 'password123'
        })
        self.assertRedirects(response, reverse('setup'))