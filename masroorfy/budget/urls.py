from django.urls import path
from .views import HistoryView, SetupView, AppLoginView, AppSignupView, dashboard
from django.contrib.auth.views import LogoutView
from django.views.generic import RedirectView

urlpatterns = [
    path('', RedirectView.as_view(pattern_name='login', permanent=False), name='landing'),
    path('history/', HistoryView.as_view(), name='history'),
    path('setup/', SetupView.as_view(), name='setup'),
    path('dashboard/', dashboard, name='dashboard'),
    path('login/', AppLoginView.as_view(), name='login'),
    path('signup/', AppSignupView.as_view(), name='signup'),
    path('logout/', LogoutView.as_view(), name='logout')
]