from django.urls import path
from django.views.generic import RedirectView
from django.contrib.auth import views as auth
from retrieval import views
urlpatterns = [
    path('', RedirectView.as_view(pattern_name='search', permanent=False)),
    path('login', auth.LoginView.as_view(template_name='retrieval/login.html'), name='login'),
    path('logout', auth.LogoutView.as_view(), name='logout'),
    path('confluence', views.confluence, name='confluence'),
    path('confluence/', views.confluence),
    path('search', views.search, name='search'),
    path('search/', views.search),
    path('command', views.command, name='command'),
]
