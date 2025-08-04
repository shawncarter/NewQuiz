"""
Refactored Mastermind WebSocket Consumer

Uses the base consumer framework to eliminate code duplication
while maintaining mastermind-specific functionality.
"""

import json
import logging
from channels.db import database_sync_to_async
from shared.consumers import BaseGameConsumer
from .services import MastermindService
from game_sessions.models import GameSession

logger = logging.getLogger('mastermind')


class MastermindConsumer(BaseGameConsumer):
    """
    Dedicated WebSocket consumer for mastermind functionality.
    
    Inherits common connection handling, error management, and message
    routing from BaseGameConsumer while providing mastermind-specific
    message handlers and business logic.
    """
    
    def get_game_group_name(self) -> str:
        """Override to use mastermind-specific group naming"""
        return f'mastermind_{self.game_code}'

    async def setup_connection(self):
        """Mastermind-specific connection setup"""
        logger.info(f"Mastermind WebSocket connected to game {self.game_code}")

        # Send initial mastermind game state
        game_state = await self.get_mastermind_game_state()
        await self.send_response('mastermind_state', game_state)
    
    async def cleanup_connection(self, close_code):
        """Mastermind-specific cleanup"""
        logger.info(f"Mastermind WebSocket disconnected from game {self.game_code}")
    
    async def handle_message(self, message_type: str, data: dict):
        """Route mastermind-specific messages to appropriate handlers"""
        handlers = {
            'select_player': self.handle_select_player,
            'preload_questions': self.handle_preload_questions,
            'ready_response': self.handle_ready_response,
            'continue_to_next_player': self.handle_continue_to_next_player,
            'submit_rapid_fire_answers': self.handle_submit_rapid_fire_answers,
            'start_rapid_fire': self.handle_start_rapid_fire,
        }

        handler = handlers.get(message_type)
        if handler:
            await handler(data)
        else:
            logger.warning(f"Unknown mastermind message type: {message_type}")
            await self.send_error_response(f'Unknown message type: {message_type}')
    
    # Mastermind Message Handlers
    
    async def handle_select_player(self, data: dict):
        """Handle GM selecting a player for mastermind round"""
        try:
            game_session = await self.get_game_session()
            service = MastermindService(game_session)
            
            player_id = data.get('player_id')
            round_number = data.get('round_number', game_session.current_round_number)
            
            if not player_id:
                logger.error("No player_id provided for mastermind player selection")
                await self.send_error_response('Player ID is required')
                return
            
            result = await self._run_service_method(
                service.select_player, round_number, player_id
            )
            
            # Broadcast result to all mastermind clients
            await self.broadcast_mastermind_message({
                'type': 'player_selected',
                'result': result,
                'round_number': round_number
            })

        except Exception as e:
            logger.error(f"Error handling select player: {e}")
            await self.send_error_response('Failed to select player')

    async def handle_preload_questions(self, data: dict):
        """Handle question pre-loading with progress updates"""
        try:
            game_session = await self.get_game_session()
            service = MastermindService(game_session)

            player_id = data.get('player_id')
            round_number = data.get('round_number', game_session.current_round_number)

            if not player_id:
                logger.error("No player_id provided for question pre-loading")
                await self.send_error_response('Player ID is required')
                return

            # Get player info
            player = await self._get_player(player_id)
            if not player:
                await self.send_error_response('Player not found')
                return

            # Start question generation with progress updates
            await self._preload_questions_with_progress(service, round_number, player)

        except Exception as e:
            logger.error(f"Error handling question pre-loading: {e}")
            await self.send_error_response('Failed to preload questions')

    async def handle_start_rapid_fire(self, data: dict):
        """Handle starting the rapid-fire round"""
        try:
            game_session = await self.get_game_session()
            service = MastermindService(game_session)

            round_number = data.get('round_number', game_session.current_round_number)

            # Get round data with questions
            round_data = await self._run_service_method(
                service.get_round_data, round_number
            )

            # Broadcast start of rapid-fire round
            await self.broadcast_mastermind_message({
                'type': 'rapid_fire_started',
                'round_data': round_data,
                'round_number': round_number,
                'duration_seconds': 90  # 90 seconds for specialist round
            })

        except Exception as e:
            logger.error(f"Error starting rapid-fire round: {e}")
            await self.send_error_response('Failed to start rapid-fire round')
    
    async def handle_ready_response(self, data: dict):
        """Handle player's ready response"""
        try:
            game_session = await self.get_game_session()
            service = MastermindService(game_session)
            
            is_ready = data.get('is_ready', False)
            round_number = data.get('round_number', game_session.current_round_number)
            
            result = await self._run_service_method(
                service.player_ready_response, round_number, is_ready
            )
            
            # Broadcast result to all mastermind clients
            await self.broadcast_mastermind_message({
                'type': 'ready_response',
                'result': result,
                'round_number': round_number
            })
            
        except Exception as e:
            logger.error(f"Error handling ready response: {e}")
            await self.send_error_response('Failed to process ready response')
    
    async def handle_continue_to_next_player(self, data: dict):
        """Handle GM continuing to next player"""
        try:
            game_session = await self.get_game_session()
            service = MastermindService(game_session)
            
            round_number = data.get('round_number', game_session.current_round_number)
            
            result = await self._run_service_method(
                service.continue_to_next_player, round_number
            )
            
            # Broadcast result to all mastermind clients
            await self.broadcast_mastermind_message({
                'type': 'continue_to_next_player',
                'result': result,
                'round_number': round_number
            })
            
        except Exception as e:
            logger.error(f"Error handling continue to next player: {e}")
            await self.send_error_response('Failed to continue to next player')
    
    async def handle_submit_rapid_fire_answers(self, data: dict):
        """Handle submission of rapid-fire answers"""
        try:
            game_session = await self.get_game_session()
            service = MastermindService(game_session)
            
            player_id = data.get('player_id')
            answers = data.get('answers', [])
            round_number = data.get('round_number', game_session.current_round_number)
            
            if not player_id or not answers:
                logger.error("No player_id or answers provided for rapid-fire submission")
                await self.send_error_response('Player ID and answers are required')
                return
            
            result = await self._run_service_method(
                service.submit_rapid_fire_answers, round_number, player_id, answers
            )
            
            # Broadcast result to all mastermind clients
            await self.broadcast_mastermind_message({
                'type': 'rapid_fire_completed',
                'result': result,
                'player_id': player_id,
                'round_number': round_number
            })
            
        except Exception as e:
            logger.error(f"Error handling rapid-fire answers: {e}")
            await self.send_error_response('Failed to submit rapid-fire answers')
    
    # Helper Methods
    
    @database_sync_to_async
    def _run_service_method(self, method, *args, **kwargs):
        """Run a service method synchronously in async context"""
        return method(*args, **kwargs)
    
    async def broadcast_mastermind_message(self, message: dict):
        """Broadcast message to all clients in the mastermind group"""
        await self.channel_layer.group_send(
            self.game_group_name,
            {
                'type': 'mastermind_message',
                'message': message
            }
        )
    
    # Group Message Handlers

    async def mastermind_message(self, event):
        """Send mastermind message to WebSocket"""
        message = event['message']
        await self.send(text_data=json.dumps(message))

    # Helper Methods

    async def _run_service_method(self, method, *args):
        """Run a service method in a thread to avoid blocking the event loop"""
        import asyncio
        from asgiref.sync import sync_to_async

        # Convert the sync method to async
        async_method = sync_to_async(method)
        return await async_method(*args)

    async def get_mastermind_game_state(self):
        """Get current mastermind game state"""
        try:
            game_session = await self.get_game_session()
            service = MastermindService(game_session)

            round_data = await self._run_service_method(
                service.get_round_data, game_session.current_round_number
            )

            # Get connected players
            players = await self._get_connected_players()

            return {
                'game_code': self.game_code,
                'round_data': round_data,
                'players': players,
                'game_status': game_session.status
            }

        except Exception as e:
            logger.error(f"Error getting mastermind game state: {e}")
            return {'error': 'Failed to get game state'}

    @database_sync_to_async
    def _get_player(self, player_id):
        """Get player by ID"""
        try:
            from players.models import Player
            return Player.objects.get(
                id=player_id,
                game_session__game_code=self.game_code,
                is_connected=True
            )
        except Player.DoesNotExist:
            return None

    @database_sync_to_async
    def _get_connected_players(self):
        """Get list of connected players"""
        try:
            game_session = GameSession.objects.get(game_code=self.game_code)
            players = game_session.players.filter(is_connected=True).order_by('joined_at')

            return [{
                'id': p.id,
                'name': p.name,
                'specialist_subject': p.specialist_subject,
                'joined_at': p.joined_at.strftime('%H:%M:%S'),
                'total_score': p.current_score,
            } for p in players]
        except Exception as e:
            logger.error(f"Error getting connected players: {e}")
            return []

    async def _preload_questions_with_progress(self, service, round_number, player):
        """Pre-load questions with real-time progress updates"""
        try:
            # Send initial progress
            await self.broadcast_mastermind_message({
                'type': 'question_generation_progress',
                'player_id': player.id,
                'player_name': player.name,
                'specialist_subject': player.specialist_subject,
                'progress': 0,
                'total': 20,
                'status': 'starting'
            })

            # Start question generation in background
            import asyncio
            asyncio.create_task(self._generate_questions_async(service, round_number, player))

        except Exception as e:
            logger.error(f"Error starting question pre-loading: {e}")
            await self.send_error_response('Failed to start question generation')

    async def _generate_questions_async(self, service, round_number, player):
        """Generate questions asynchronously with progress updates"""
        try:
            # Simulate question generation progress (replace with actual AI generation)
            for i in range(1, 21):  # 20 questions
                # Simulate generation time
                await asyncio.sleep(0.5)  # 0.5 seconds per question = 10 seconds total

                # Send progress update
                await self.broadcast_mastermind_message({
                    'type': 'question_generation_progress',
                    'player_id': player.id,
                    'player_name': player.name,
                    'specialist_subject': player.specialist_subject,
                    'progress': i,
                    'total': 20,
                    'status': 'generating'
                })

            # Actually generate the questions
            result = await self._run_service_method(
                service._preload_player_questions,
                service.get_or_create_round(round_number),
                player
            )

            if result:
                # Questions generated successfully
                await self.broadcast_mastermind_message({
                    'type': 'questions_ready',
                    'player_id': player.id,
                    'player_name': player.name,
                    'specialist_subject': player.specialist_subject,
                    'total_questions': 20,
                    'status': 'ready'
                })
            else:
                # Generation failed
                await self.broadcast_mastermind_message({
                    'type': 'question_generation_failed',
                    'player_id': player.id,
                    'player_name': player.name,
                    'error': 'Failed to generate questions'
                })

        except Exception as e:
            logger.error(f"Error generating questions: {e}")
            await self.broadcast_mastermind_message({
                'type': 'question_generation_failed',
                'player_id': player.id,
                'player_name': player.name,
                'error': str(e)
            })