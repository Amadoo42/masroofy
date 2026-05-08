from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.core.exceptions import ValidationError
from decimal import Decimal
import json

from hypothesis import given, settings
from hypothesis.extra.django import TestCase as HypothesisTestCase
import hypothesis.strategies as st

from .models import BudgetCycle, Transaction, User, AllowanceStatus
from .services import BudgetCycleService, TransactionMutationCommand, AccountService
from .factories import UserFactory, BudgetCycleFactory, TransactionFactory


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
        with self.assertRaises(ValidationError):
            TransactionMutationCommand.log(self.user, Decimal('-50.00'), 'FOOD')
        with self.assertRaises(ValidationError):
            TransactionMutationCommand.log(self.user, Decimal('0.00'), 'FOOD')


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
        self.assertEqual(dup_tx.note, 'Internet (Copy)')
        self.assertEqual(self.cycle.remaining_cycle_balance, Decimal('1600.00'))

    def test_get_cycle_metrics_thresholds(self):
        metrics = BudgetCycleService.get_cycle_metrics(self.cycle)
        self.assertEqual(metrics['status'], AllowanceStatus.NORMAL)
        
        TransactionMutationCommand.log(self.user, Decimal('1600.00'), 'OTHER')
        self.cycle.refresh_from_db()
        metrics = BudgetCycleService.get_cycle_metrics(self.cycle)
        self.assertEqual(metrics['status'], AllowanceStatus.HIGH_USAGE)
        
        TransactionMutationCommand.log(self.user, Decimal('400.00'), 'OTHER')
        self.cycle.refresh_from_db()
        metrics = BudgetCycleService.get_cycle_metrics(self.cycle)
        self.assertEqual(metrics['status'], AllowanceStatus.LIMIT_REACHED)

    def test_account_service_export_and_wipe(self):
        TransactionMutationCommand.log(self.user, Decimal('50.00'), 'FOOD', 'Snack')
        
        data_json = AccountService.export_data(self.user)
        parsed = json.loads(data_json)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(len(parsed[0]['transactions']), 1)
        
        AccountService.wipe_data(self.user)
        self.assertEqual(BudgetCycle.objects.filter(user=self.user).count(), 0)


class ViewIntegrationTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='testuser', email='test@test.com', password='password123')
        self.client.login(username='test@test.com', password='password123')

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
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('50.00 EGP logged successfully', response.content.decode())
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