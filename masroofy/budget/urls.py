from django.urls import path
from .views import HistoryView, SetupView, AppLoginView, AppSignupView, DashboardView, TransactionDeleteView, SettingsView
from django.contrib.auth.views import LogoutView
from django.views.generic import RedirectView

urlpatterns = [
    path('', RedirectView.as_view(pattern_name='login', permanent=False), name='landing'),
    path('history/', HistoryView.as_view(), name='history'),
    path('setup/', SetupView.as_view(), name='setup'),
    path('dashboard/', DashboardView.as_view(), name='dashboard'),
    path('login/', AppLoginView.as_view(), name='login'),
    path('signup/', AppSignupView.as_view(), name='signup'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('transaction_delete/<int:pk>/', TransactionDeleteView.as_view(), name='transaction_delete'),
    path('settings/', SettingsView.as_view(), name='settings'),
]