"""
Mastermind URL Configuration
"""

from django.urls import path
from . import views

app_name = 'mastermind'

urlpatterns = [
    # API endpoints for mastermind functionality
    path('api/<str:game_code>/select_player/', views.select_player, name='select_player'),
    path('api/<str:game_code>/ready_response/', views.ready_response, name='ready_response'),
    path('api/<str:game_code>/continue/', views.continue_to_next_player, name='continue'),
    path('api/<str:game_code>/submit_answers/', views.submit_rapid_fire_answers, name='submit_answers'),
    
    # Admin/debug views
    path('<str:game_code>/status/', views.round_status, name='round_status'),
]