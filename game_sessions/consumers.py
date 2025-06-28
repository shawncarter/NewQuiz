import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.db import models
from .models import GameSession
from django.core.cache import cache

logger = logging.getLogger('websockets')


class GameConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.game_code = self.scope['url_route']['kwargs']['game_code']
        self.game_group_name = f'game_{self.game_code}'
        self.player_id = None  # Will be set by identify message
        self.last_game_started_time = None  # Track when game_started was sent

        logger.info(f"WebSocket connecting to game {self.game_code}")

        # Join game group
        await self.channel_layer.group_add(
            self.game_group_name,
            self.channel_name
        )

        await self.accept()
        logger.info(f"WebSocket connected to game {self.game_code} (channel: {self.channel_name})")

        # Send initial game state to this connection only
        game_state = await self.get_game_state()
        logger.info(f"Sending initial game state to new connection for {self.game_code}")
        await self.send(text_data=json.dumps({
            'type': 'game_state_sync',
            'data': game_state
        }))

    async def disconnect(self, close_code):
        logger.info(f"WebSocket disconnecting from game {self.game_code}")
        await self.handle_player_disconnect()
        await self.channel_layer.group_discard(
            self.game_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        data = json.loads(text_data)
        message_type = data.get('type')

        if message_type == 'identify':
            # Set player_id for this connection
            self.player_id = data.get('player_id')
            logger.info(f"Player identified as {self.player_id} for game {self.game_code}")
            
            # Mark player as connected when they identify
            await self.mark_player_connected()

        elif message_type == 'ping':
            # Respond with current game state
            game_state = await self.get_game_state()
            await self.send(text_data=json.dumps({
                'type': 'game_state',
                'data': game_state
            }))

        elif message_type == 'submit_answer':
            await self.handle_submit_answer(data.get('data', {}))

    # Receive message from game group
    async def game_update(self, event):
        logger.info(f"Broadcasting game_update to {self.game_code}: {event['data']}")
        # Send message to WebSocket
        await self.send(text_data=json.dumps({
            'type': 'game_update',
            'data': event['data']
        }))

    async def game_restart_confirmation(self, event):
        logger.info(f"Broadcasting game_restart_confirmation to {self.game_code}: {event['data']}")
        # Send message to WebSocket
        await self.send(text_data=json.dumps({
            'type': 'game_restart_confirmation',
            'data': event['data']
        }))

    async def round_started(self, event):
        await self.send(text_data=json.dumps({
            'type': 'round_started',
            'data': event['data']
        }))

    async def round_ended(self, event):
        # Forward the answers as provided by the backend (from DB)
        await self.send(text_data=json.dumps({
            'type': 'round_ended',
            'data': event['data']
        }))

    async def timer_update(self, event):
        await self.send(text_data=json.dumps({
            'type': 'timer_update',
            'data': event['data']
        }))

    async def score_update(self, event):
        await self.send(text_data=json.dumps({
            'type': 'score_update',
            'data': event['data']
        }))

    async def game_complete(self, event):
        await self.send(text_data=json.dumps({
            'type': 'game_complete',
            'data': event['data']
        }))

    async def game_started(self, event):
        import time
        from django.core.cache import cache
        # Track game start time globally for this game
        cache.set(f'game_started_time_{self.game_code}', time.time(), timeout=10)
        await self.send(text_data=json.dumps({
            'type': 'game_started',
            'data': event['data']
        }))

    async def handle_submit_answer(self, data):
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
        cache_key = f'game_{self.game_code}_round_{round_number}_answers'
        
        answers = cache.get(cache_key, {})
        answers[str(player_id)] = answer_text
        cache.set(cache_key, answers, timeout=3600)

        logger.info(f"Player {player_id} submitted answer for round {round_number} in game {self.game_code}")

    

    @database_sync_to_async
    def get_game_state(self):
        try:
            game_session = GameSession.objects.get(game_code=self.game_code)
            current_round_info = game_session.get_current_round_info()

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

            data = {
                'game_status': game_session.status,
                'player_count': connected_players.count(),
                'players': players_data,
            }

            if current_round_info:
                data.update({
                    'current_round': {
                        'round_number': current_round_info['round_number'],
                        'prompt': f"A {current_round_info['category'].name.lower()} that starts with '{current_round_info['prompt_letter']}'",
                        'letter': current_round_info['prompt_letter'],
                        'category': current_round_info['category'].name,
                        'is_active': current_round_info['is_active'],
                        'time_remaining': int(current_round_info['time_remaining']),
                        'total_time': game_session.configuration.round_time_seconds,
                    }
                })

            return data
        except GameSession.DoesNotExist:
            return {'error': 'Game not found'}

    @database_sync_to_async
    def handle_player_disconnect(self):
        """Handle player disconnect and broadcast update"""
        try:
            game_session = GameSession.objects.get(game_code=self.game_code)

            # Check if this disconnect is happening shortly after game_started
            import time
            from django.core.cache import cache
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
    def mark_player_connected(self):
        """Mark player as connected when they identify"""
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
            pass
