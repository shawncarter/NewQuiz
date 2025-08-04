"""
Mastermind WebSocket Routing

Separate WebSocket routing for Mastermind games to handle their unique
rapid-fire question flow independently from standard quiz games.
"""

from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/mastermind/(?P<game_code>\w+)/$', consumers.MastermindConsumer.as_asgi()),
]
