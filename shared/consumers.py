"""
Base WebSocket Consumer Classes

Provides common functionality for game-related WebSocket consumers
to eliminate code duplication and ensure consistent error handling.
"""

import json
import logging
import re
from abc import ABC, abstractmethod
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from game_sessions.models import GameSession

logger = logging.getLogger('websockets')


class BaseGameConsumer(AsyncWebsocketConsumer, ABC):
    """
    Abstract base class for game-related WebSocket consumers.
    
    Provides common functionality including:
    - Game code extraction from URL routing
    - Connection and disconnection handling
    - JSON message parsing and error handling
    - Game session retrieval
    - Standard error response formatting
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.game_code = None
        self.game_group_name = None
    
    async def connect(self):
        """
        Establishes WebSocket connection and joins game group.
        
        Extracts game code from URL routing, creates game group name,
        and calls the abstract setup_connection method for consumer-specific logic.
        """
        # Extract game code from URL routing (supports both test and production)
        self.game_code = self.extract_game_code_from_scope()
        if not self.game_code:
            logger.error(f"Could not extract game_code from scope: {self.scope}")
            await self.close()
            return
        
        # Set up game group name (can be overridden by subclasses)
        self.game_group_name = self.get_game_group_name()
        
        logger.info(f"WebSocket connecting to game {self.game_code} (group: {self.game_group_name})")
        
        # Join game group
        await self.channel_layer.group_add(
            self.game_group_name,
            self.channel_name
        )
        
        await self.accept()
        
        # Allow subclasses to perform additional setup
        await self.setup_connection()
        
        logger.info(f"WebSocket connected to game {self.game_code} (channel: {self.channel_name})")
    
    async def disconnect(self, close_code):
        """
        Handles WebSocket disconnection and cleanup.
        
        Performs cleanup operations and removes from game group.
        Calls abstract cleanup_connection method for consumer-specific cleanup.
        """
        logger.info(f"WebSocket disconnecting from game {self.game_code}")
        
        # Allow subclasses to perform cleanup
        await self.cleanup_connection(close_code)
        
        # Remove from game group
        if self.game_group_name:
            await self.channel_layer.group_discard(
                self.game_group_name,
                self.channel_name
            )
    
    async def receive(self, text_data):
        """
        Handles incoming WebSocket messages with standardized error handling.
        
        Parses JSON messages and delegates to handle_message method.
        Provides consistent error responses for JSON parsing errors and exceptions.
        """
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if not message_type:
                await self.send_error_response('Message type is required')
                return
            
            # Delegate to subclass message handler
            await self.handle_message(message_type, data)
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON received in game {self.game_code}: {e}")
            await self.send_error_response('Invalid message format')
        except Exception as e:
            logger.error(f"Error handling WebSocket message in game {self.game_code}: {e}")
            await self.send_error_response('Server error processing message')
    
    # Helper Methods
    
    def extract_game_code_from_scope(self) -> str:
        """
        Extract game code from WebSocket scope.
        
        Supports both standard URL routing and test path extraction.
        """
        # Handle standard URL routing
        if 'url_route' in self.scope and 'kwargs' in self.scope['url_route']:
            return self.scope['url_route']['kwargs'].get('game_code')
        
        # For testing, extract from path
        path = self.scope.get('path', '')
        match = re.search(r'/ws/game/(\w+)/', path)
        if match:
            return match.group(1)
        
        return None
    
    def get_game_group_name(self) -> str:
        """
        Get the WebSocket group name for this game.
        
        Can be overridden by subclasses for specialized group naming.
        """
        return f'game_{self.game_code}'
    
    async def send_error_response(self, message: str):
        """Send standardized error response to client"""
        await self.send(text_data=json.dumps({
            'type': 'error',
            'data': {'message': message}
        }))
    
    async def send_response(self, response_type: str, data: dict):
        """Send standardized response to client"""
        await self.send(text_data=json.dumps({
            'type': response_type,
            'data': data
        }))
    
    async def broadcast_to_group(self, message_type: str, data: dict):
        """Broadcast message to all clients in the game group"""
        await self.channel_layer.group_send(
            self.game_group_name,
            {
                'type': self.get_group_message_handler_name(message_type),
                'data': data
            }
        )
    
    def get_group_message_handler_name(self, message_type: str) -> str:
        """
        Get the handler method name for group messages.
        
        Can be overridden by subclasses for custom handler naming.
        """
        return message_type.replace('-', '_')
    
    @database_sync_to_async
    def get_game_session(self) -> GameSession:
        """Get the game session for this consumer's game code"""
        try:
            return GameSession.objects.get(game_code=self.game_code)
        except GameSession.DoesNotExist:
            logger.error(f"Game session {self.game_code} not found")
            raise
    
    # Abstract Methods (must be implemented by subclasses)
    
    @abstractmethod
    async def setup_connection(self):
        """
        Perform consumer-specific setup after connection is established.
        
        Called after the WebSocket connection is accepted and the consumer
        has joined the game group. Use this for sending initial state,
        setting up additional groups, or other initialization.
        """
        pass
    
    @abstractmethod
    async def cleanup_connection(self, close_code):
        """
        Perform consumer-specific cleanup before disconnection.
        
        Called before the consumer leaves the game group. Use this for
        marking players as disconnected, cleaning up state, or other teardown.
        """
        pass
    
    @abstractmethod
    async def handle_message(self, message_type: str, data: dict):
        """
        Handle incoming WebSocket messages.
        
        Args:
            message_type: The type of message received
            data: The full message data dictionary
        """
        pass


class GameSessionMixin:
    """
    Mixin providing common game session operations for WebSocket consumers.
    
    Provides methods for common game session operations like player management,
    game state retrieval, and player connection tracking.
    """
    
    @database_sync_to_async
    def mark_player_connected(self, player_id: int):
        """Mark a player as connected in the database"""
        try:
            from players.models import Player
            player = Player.objects.get(id=player_id, game_session__game_code=self.game_code)
            player.reconnect()
            logger.info(f"Marked player {player_id} as connected in game {self.game_code}")
        except Exception as e:
            logger.error(f"Error marking player {player_id} as connected: {e}")
    
    @database_sync_to_async
    def mark_player_disconnected(self, player_id: int):
        """Mark a player as disconnected in the database"""
        try:
            from players.models import Player
            player = Player.objects.get(id=player_id, game_session__game_code=self.game_code)
            player.disconnect()
            logger.info(f"Marked player {player_id} as disconnected in game {self.game_code}")
        except Exception as e:
            logger.error(f"Error marking player {player_id} as disconnected: {e}")
    
    @database_sync_to_async
    def get_game_state(self):
        """Get current game state for broadcasting"""
        try:
            from game_sessions.websocket_utils import get_game_state_for_broadcast
            return get_game_state_for_broadcast(self.game_code)
        except Exception as e:
            logger.error(f"Error getting game state for {self.game_code}: {e}")
            return {'error': 'Could not retrieve game state'}
    
    @database_sync_to_async
    def get_connected_players(self):
        """Get list of connected players for this game"""
        try:
            game_session = GameSession.objects.get(game_code=self.game_code)
            return list(game_session.players.filter(is_connected=True).values(
                'id', 'name', 'current_score', 'specialist_subject'
            ))
        except Exception as e:
            logger.error(f"Error getting connected players for {self.game_code}: {e}")
            return []


class MessageHandlerMixin:
    """
    Mixin providing common message handler patterns for WebSocket consumers.
    
    Provides decorator and utility methods for handling common WebSocket message patterns.
    """
    
    def message_handler(self, message_type: str):
        """
        Decorator for registering message handlers.
        
        Usage:
            @message_handler('submit_answer')
            async def handle_submit_answer(self, data):
                ...
        """
        def decorator(func):
            if not hasattr(self, '_message_handlers'):
                self._message_handlers = {}
            self._message_handlers[message_type] = func
            return func
        return decorator
    
    async def handle_message(self, message_type: str, data: dict):
        """
        Route messages to registered handlers.
        
        Override this in consumers that use the message_handler decorator.
        """
        if hasattr(self, '_message_handlers'):
            handler = self._message_handlers.get(message_type)
            if handler:
                await handler(data)
                return
        
        # Fallback to default handling
        await self.handle_unknown_message(message_type, data)
    
    async def handle_unknown_message(self, message_type: str, data: dict):
        """Handle unknown message types (can be overridden)"""
        logger.warning(f"Unknown message type: {message_type}")
        await self.send_error_response(f'Unknown message type: {message_type}')