"""
ASGI config for quiz_game project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'quiz_game.settings')

django_asgi_app = get_asgi_application()

# Import websocket routing
from game_sessions import routing as game_routing
from mastermind import routing as mastermind_routing

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(
            game_routing.websocket_urlpatterns +
            mastermind_routing.websocket_urlpatterns
        )
    ),
})
