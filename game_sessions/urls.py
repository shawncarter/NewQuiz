from django.urls import path
from . import views

app_name = 'game_sessions'

urlpatterns = [
    path('', views.home, name='home'),
    path('create/', views.create_game, name='create_game'),
    path('join/', views.join_game, name='join_game'),
    path('game/<str:game_code>/', views.game_master, name='game_master'),
    path('game/<str:game_code>/status/', views.game_status, name='game_status'),
    path('game/<str:game_code>/start/', views.start_game, name='start_game'),
    path('game/<str:game_code>/restart/', views.restart_game, name='restart_game'),
    path('game/<str:game_code>/configure/', views.configure_game, name='configure_game'),
    path('game/<str:game_code>/start-round/', views.start_round, name='start_round'),
    path('game/<str:game_code>/end-round/', views.end_round, name='end_round'),
    path('game/<str:game_code>/validate-answer/', views.validate_answer, name='validate_answer'),
]
