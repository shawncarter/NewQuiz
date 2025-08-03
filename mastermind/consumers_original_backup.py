"""
Mastermind WebSocket Consumers

Handles mastermind-specific WebSocket communication.
"""

import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .services import MastermindService
from game_sessions.models import GameSession

logger = logging.getLogger('mastermind')


class MastermindConsumer(AsyncWebsocketConsumer):
    """
    Dedicated WebSocket consumer for mastermind functionality.
    
    This handles mastermind-specific messages without cluttering
    the main game consumer.
    """
    
    async def connect(self):
        self.game_code = self.scope['url_route']['kwargs']['game_code']
        self.game_group_name = f'mastermind_{self.game_code}'
        
        # Join game group
        await self.channel_layer.group_add(
            self.game_group_name,
            self.channel_name
        )
        
        await self.accept()
        logger.info(f"Mastermind WebSocket connected to game {self.game_code}")
    
    async def disconnect(self, close_code):
        # Leave game group
        await self.channel_layer.group_discard(
            self.game_group_name,
            self.channel_name
        )
        
        logger.info(f"Mastermind WebSocket disconnected from game {self.game_code}")
    
    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'select_player':
                await self.handle_select_player(data)
            elif message_type == 'ready_response':
                await self.handle_ready_response(data)
            elif message_type == 'continue_to_next_player':
                await self.handle_continue_to_next_player(data)
            elif message_type == 'submit_rapid_fire_answers':
                await self.handle_submit_rapid_fire_answers(data)
            else:
                logger.warning(f"Unknown message type: {message_type}")
                
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON received: {e}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid message format'
            }))
        except Exception as e:
            logger.error(f"Error handling WebSocket message: {e}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Server error processing message'
            }))
    
    @database_sync_to_async
    def handle_select_player(self, data):
        """Handle GM selecting a player for mastermind round"""
        try:
            game_session = GameSession.objects.get(game_code=self.game_code)
            service = MastermindService(game_session)
            
            player_id = data.get('player_id')
            round_number = data.get('round_number', game_session.current_round_number)
            
            if not player_id:
                logger.error("No player_id provided for mastermind player selection")
                return
            
            result = service.select_player(round_number, player_id)
            
            # Broadcast result to all mastermind clients
            self._broadcast_to_group({
                'type': 'player_selected',
                'result': result,
                'round_number': round_number
            })
            
        except Exception as e:
            logger.error(f"Error handling select player: {e}")
    
    @database_sync_to_async
    def handle_ready_response(self, data):
        """Handle player's ready response"""
        try:
            game_session = GameSession.objects.get(game_code=self.game_code)
            service = MastermindService(game_session)
            
            is_ready = data.get('is_ready', False)
            round_number = data.get('round_number', game_session.current_round_number)
            
            result = service.player_ready_response(round_number, is_ready)
            
            # Broadcast result to all mastermind clients
            self._broadcast_to_group({
                'type': 'ready_response',
                'result': result,
                'round_number': round_number
            })
            
        except Exception as e:
            logger.error(f"Error handling ready response: {e}")
    
    @database_sync_to_async
    def handle_continue_to_next_player(self, data):
        """Handle GM continuing to next player"""
        try:
            game_session = GameSession.objects.get(game_code=self.game_code)
            service = MastermindService(game_session)
            
            round_number = data.get('round_number', game_session.current_round_number)
            
            result = service.continue_to_next_player(round_number)
            
            # Broadcast result to all mastermind clients
            self._broadcast_to_group({
                'type': 'continue_to_next_player',
                'result': result,
                'round_number': round_number
            })
            
        except Exception as e:
            logger.error(f"Error handling continue to next player: {e}")
    
    @database_sync_to_async
    def handle_submit_rapid_fire_answers(self, data):
        """Handle submission of rapid-fire answers"""
        try:
            game_session = GameSession.objects.get(game_code=self.game_code)
            service = MastermindService(game_session)
            
            player_id = data.get('player_id')
            answers = data.get('answers', [])
            round_number = data.get('round_number', game_session.current_round_number)
            
            if not player_id or not answers:
                logger.error("No player_id or answers provided for rapid-fire submission")
                return
            
            result = service.submit_rapid_fire_answers(round_number, player_id, answers)
            
            # Broadcast result to all mastermind clients
            self._broadcast_to_group({
                'type': 'rapid_fire_completed',
                'result': result,
                'player_id': player_id,
                'round_number': round_number
            })
            
        except Exception as e:
            logger.error(f"Error handling rapid-fire answers: {e}")
    
    async def _broadcast_to_group(self, message):
        """Broadcast message to all clients in the mastermind group"""
        await self.channel_layer.group_send(
            self.game_group_name,
            {
                'type': 'mastermind_message',
                'message': message
            }
        )
    
    async def mastermind_message(self, event):
        """Send mastermind message to WebSocket"""
        message = event['message']
        
        await self.send(text_data=json.dumps(message))