import json
import logging
import time
from channels.db import database_sync_to_async
from django.core.cache import cache
from shared.consumers import BaseGameConsumer, GameSessionMixin
from .models import GameSession

logger = logging.getLogger('websockets')


class GameConsumer(BaseGameConsumer, GameSessionMixin):
    """
    WebSocket consumer for standard quiz game functionality.
    
    Handles game state synchronization, player connections, answer submissions,
    and real-time game updates. Inherits common functionality from BaseGameConsumer
    and uses GameSessionMixin for game-specific operations.
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.player_id = None
        self.last_game_started_time = None
    
    async def setup_connection(self):
        """Send initial game state to newly connected client"""
        game_state = await self.get_game_state()
        logger.info(f"Sending initial game state to new connection for {self.game_code}")
        await self.send_response('game_state_sync', game_state)
    
    async def cleanup_connection(self, close_code):
        """Handle player disconnect and cleanup"""
        await self.handle_player_disconnect()
        
        # Remove from individual player group if identified
        if self.player_id:
            await self.channel_layer.group_discard(
                f'player_{self.player_id}',
                self.channel_name
            )
            logger.info(f"Removed player {self.player_id} from individual group")
    
    async def handle_message(self, message_type: str, data: dict):
        """Route incoming messages to appropriate handlers"""
        handlers = {
            'identify': self.handle_identify,
            'ping': self.handle_ping,
            'submit_answer': self.handle_submit_answer,
        }

        handler = handlers.get(message_type)
        if handler:
            await handler(data)
        else:
            logger.warning(f"Unknown message type: {message_type}")
    
    async def handle_identify(self, data: dict):
        """Handle player identification"""
        self.player_id = data.get('player_id')
        logger.info(f"Player identified as {self.player_id} for game {self.game_code}")
        
        # Add player to their individual group for personalized messages
        if self.player_id:
            await self.channel_layer.group_add(
                f'player_{self.player_id}',
                self.channel_name
            )
            logger.info(f"Added player {self.player_id} to individual group")
        
        # Mark player as connected when they identify
        await self.mark_player_connected_with_broadcast()
    
    async def handle_ping(self, data: dict):
        """Handle ping requests by returning current game state"""
        game_state = await self.get_game_state()
        await self.send_response('game_state', game_state)
    
    async def handle_submit_answer(self, data: dict):
        """Handle answer submission from players"""
        player_id = data.get('player_id')
        answer_text = data.get('answer')
        
        if not player_id or answer_text is None:
            logger.warning(f"Invalid submit_answer data received in {self.game_code}")
            return

        game_state = await self.get_game_state()
        current_round = game_state.get('current_round')

        if not current_round or not current_round.get('is_active'):
            logger.warning(f"Answer submitted for {self.game_code} but no active round.")
            return

        round_number = current_round['round_number']
        
        # Use cache service for better answer management
        from .cache_service import get_game_cache
        game_cache = get_game_cache(self.game_code)
        game_cache.cache_player_answer(round_number, player_id, answer_text)

        logger.info(f"Player {player_id} submitted answer for round {round_number} in game {self.game_code}")

    # Group message handlers (received from broadcasts)
    
    async def game_update(self, event):
        """Handle game update broadcasts"""
        logger.info(f"Broadcasting game_update to {self.game_code}: {event['data']}")
        await self.send_response('game_update', event['data'])

    async def game_restart_confirmation(self, event):
        """Handle game restart confirmation broadcasts"""
        logger.info(f"Broadcasting game_restart_confirmation to {self.game_code}: {event['data']}")
        await self.send_response('game_restart_confirmation', event['data'])

    async def round_started(self, event):
        """Handle round started broadcasts"""
        await self.send_response('round_started', event['data'])

    async def round_ended(self, event):
        """Handle round ended broadcasts"""
        await self.send_response('round_ended', event['data'])

    async def timer_update(self, event):
        """Handle timer update broadcasts"""
        await self.send_response('timer_update', event['data'])

    async def score_update(self, event):
        """Handle score update broadcasts"""
        await self.send_response('score_update', event['data'])

    async def player_result(self, event):
        """Handle individual player result broadcasts"""
        logger.info(f"Forwarding player_result to player {self.player_id}: {event['data']}")
        await self.send_response('player_result', event['data'])

    async def game_complete(self, event):
        """Handle game completion broadcasts"""
        await self.send_response('game_complete', event['data'])
    
    async def round_update(self, event):
        """Handle round updates for mastermind state changes"""
        # Convert datetime objects to strings for JSON serialization
        data = event['data'].copy()
        if 'started_at' in data and data['started_at']:
            data['started_at'] = data['started_at'].isoformat()
        
        await self.send_response('round_update', data)

    async def game_started(self, event):
        """Handle game started broadcasts with redirect disconnect tracking"""
        # Track game start time globally for this game
        cache.set(f'game_started_time_{self.game_code}', time.time(), timeout=10)
        await self.send_response('game_started', event['data'])
    
    # Enhanced methods using shared functionality
    
    @database_sync_to_async
    def get_game_state(self):
        """Get current game state with caching optimizations"""
        try:
            # Try to get cached game state first
            from .cache_service import get_game_cache, PlayerCacheService
            game_cache = get_game_cache(self.game_code)
            cached_state = game_cache.get_cached_game_state()
            
            if cached_state:
                # Use cached state if recent (less than 2 minutes old)
                cache_age = time.time() - cached_state.get('updated_at', 0)
                if cache_age < 120:  # 2 minutes
                    data = {
                        'game_status': cached_state['status'],
                        'player_count': cached_state['player_count'],
                        'players': cached_state['players'],
                    }
                    logger.debug(f"Using cached game state for {self.game_code} (age: {cache_age:.1f}s)")
                    
                    # Get round info separately if needed
                    game_session = GameSession.objects.get(game_code=self.game_code)
                    if game_session.current_round_number > 0:
                        self._add_round_info_to_data(data, game_session, game_cache)
                    
                    return data
            
            # Fallback to database query
            game_session = GameSession.objects.get(game_code=self.game_code)
            
            # Check for cached connected players
            cached_players = PlayerCacheService.get_cached_connected_players(self.game_code)
            if cached_players:
                players_data = cached_players
                player_count = len(cached_players)
            else:
                # Get connected players with their details
                connected_players = game_session.players.filter(is_connected=True).order_by('joined_at')
                players_data = []
                for player in connected_players:
                    players_data.append({
                        'id': player.id,
                        'name': player.name,
                        'joined_at': player.joined_at.strftime('%H:%M:%S'),
                        'total_score': player.current_score,
                    })
                player_count = len(players_data)
                
                # Cache the players data
                PlayerCacheService.cache_connected_players(self.game_code, players_data)

            data = {
                'game_status': game_session.status,
                'player_count': player_count,
                'players': players_data,
            }
            
            # Cache the game state
            game_cache.cache_game_state(game_session, players_data)

            # Only include round info if we have an active game with rounds started
            if game_session.current_round_number > 0:
                self._add_round_info_to_data(data, game_session, game_cache)

            return data
        except Exception as e:
            logger.error(f"Error getting game state for {self.game_code}: {e}")
            return {
                'game_status': 'error',
                'player_count': 0,
                'players': [],
                'error': str(e)
            }
    
    def _add_round_info_to_data(self, data, game_session, game_cache):
        """Helper method to add round info to game state data"""
        try:
            # Try cached round state first
            cached_round_state = game_cache.get_cached_round_state(game_session.current_round_number)
            if cached_round_state and cached_round_state.get('round_info'):
                current_round_info = cached_round_state['round_info']
            else:
                # Fallback to round handler
                from .round_handlers import get_round_handler
                round_handler = get_round_handler(game_session, game_session.current_round_number)
                current_round_info = round_handler.get_round_info()
                
            if current_round_info:
                # Map legacy round types for WebSocket compatibility
                mapped_round_type = current_round_info['round_type']
                if mapped_round_type == 'starts_with':
                    mapped_round_type = 'flower_fruit_veg'
                
                current_round_data = {
                    'round_number': current_round_info['round_number'],
                    'is_active': current_round_info['is_active'],
                    'time_remaining': int(current_round_info['time_remaining']),
                    'total_time': game_session.configuration.round_time_seconds,
                    'round_type': mapped_round_type,
                }
                
                # Only add category for round types that have it
                if 'category' in current_round_info and current_round_info['category'] is not None:
                    current_round_data['category'] = current_round_info['category'].name if hasattr(current_round_info['category'], 'name') else current_round_info['category']
                if mapped_round_type == 'flower_fruit_veg':
                    if 'category' in current_round_info and current_round_info['category']:
                        category_name = current_round_info['category'].name if hasattr(current_round_info['category'], 'name') else str(current_round_info['category'])
                        current_round_data.update({
                            'prompt': f"A {category_name.lower()} that starts with '{current_round_info['prompt_letter']}'",
                            'letter': current_round_info['prompt_letter'],
                        })
                elif mapped_round_type == 'multiple_choice':
                    current_round_data.update({
                        'question_text': current_round_info['question_text'],
                        'choices': current_round_info['choices'],
                    })
                data['current_round'] = current_round_data
        except Exception as e:
            logger.error(f"Error adding round info for {game_session.game_code}: {e}")

    @database_sync_to_async
    def handle_player_disconnect(self):
        """Handle player disconnect and broadcast update"""
        try:
            game_session = GameSession.objects.get(game_code=self.game_code)

            # Check if this disconnect is happening shortly after game_started
            is_redirect_disconnect = False
            game_started_time = cache.get(f'game_started_time_{self.game_code}')
            if game_started_time and (time.time() - game_started_time) < 5.0:
                is_redirect_disconnect = True
                logger.info(f"Detected likely redirect disconnect for game {self.game_code} (within 5s of game_started)")

            if self.player_id is not None:
                # Disconnect by player_id - only if they are currently connected
                player = game_session.players.filter(id=self.player_id, is_connected=True).first()
                if player:
                    if is_redirect_disconnect:
                        # Don't mark as disconnected during redirect, just log
                        logger.info(f"Skipping disconnect for player {player.name} (id={self.player_id}) - likely game start redirect")
                    else:
                        # Normal disconnect
                        player.disconnect()
                        logger.info(f"Marked player {player.name} (id={self.player_id}) as disconnected")
                        
                        # Get current connected players after disconnect
                        connected_players = game_session.players.filter(is_connected=True).order_by('joined_at')
                        players_data = []
                        for p in connected_players:
                            players_data.append({
                                'id': p.id,
                                'name': p.name,
                                'joined_at': p.joined_at.strftime('%H:%M:%S'),
                                'total_score': p.current_score,
                            })

                        # Broadcast updated player count
                        from .websocket_utils import broadcast_to_game
                        broadcast_to_game(self.game_code, 'game_update', {
                            'game_status': game_session.status,
                            'player_count': connected_players.count(),
                            'players': players_data,
                            'message': f'{player.name} disconnected'
                        })
                else:
                    logger.info(f"Player {self.player_id} was already disconnected or not found")
            else:
                # No player_id means we can't identify who disconnected
                if not is_redirect_disconnect:
                    logger.warning(f"WebSocket disconnect without player identification for game {self.game_code}")

        except GameSession.DoesNotExist:
            pass

    @database_sync_to_async
    def mark_player_connected_with_broadcast(self):
        """Mark player as connected when they identify and broadcast update"""
        if not self.player_id:
            return
        
        try:
            game_session = GameSession.objects.get(game_code=self.game_code)
            player = game_session.players.filter(id=self.player_id).first()
            if player and not player.is_connected:
                player.is_connected = True
                player.save()
                logger.info(f"Marked player {player.name} (id={self.player_id}) as reconnected")
                
                # Broadcast player reconnected
                connected_players = game_session.players.filter(is_connected=True).order_by('joined_at')
                players_data = []
                for p in connected_players:
                    players_data.append({
                        'id': p.id,
                        'name': p.name,
                        'joined_at': p.joined_at.strftime('%H:%M:%S'),
                        'total_score': p.current_score,
                    })

                from .websocket_utils import broadcast_to_game
                broadcast_to_game(self.game_code, 'game_update', {
                    'game_status': game_session.status,
                    'player_count': connected_players.count(),
                    'players': players_data,
                    'message': f'{player.name} reconnected'
                })
        except GameSession.DoesNotExist:
            logger.warning(f"Game {self.game_code} not found when marking player {self.player_id} as connected")
        except Exception as e:
            logger.error(f"Error marking player {self.player_id} as connected in game {self.game_code}: {e}")