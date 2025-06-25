from django.urls import path
from . import views

app_name = 'players'

urlpatterns = [
    path('lobby/<str:game_code>/', views.player_lobby, name='player_lobby'),
    path('lobby/<str:game_code>/<int:player_id>/', views.player_lobby_with_id, name='player_lobby_with_id'),
    path('game/<str:game_code>/', views.player_game, name='player_game'),
    path('game/<str:game_code>/<int:player_id>/', views.player_game_with_id, name='player_game_with_id'),
    path('game/<str:game_code>/submit/', views.submit_answer, name='submit_answer'),
]
