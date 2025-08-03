"""
Debug command to test WebSocket broadcasting functionality
"""

from django.core.management.base import BaseCommand
from game_sessions.models import GameSession
from players.models import Player
from game_sessions.websocket_utils import broadcast_to_game
import time


class Command(BaseCommand):
    help = 'Debug WebSocket broadcasting'
    
    def add_arguments(self, parser):
        parser.add_argument('game_code', help='Game code to test with')
        parser.add_argument('--test-type', default='player_join', 
                          choices=['player_join', 'simple_message'], 
                          help='Type of test to run')
    
    def handle(self, *args, **options):
        game_code = options['game_code'].upper()
        test_type = options['test_type']
        
        self.stdout.write(f'🔍 Testing WebSocket broadcasting for game: {game_code}')
        
        try:
            game_session = GameSession.objects.get(game_code=game_code)
            self.stdout.write(f'✓ Found game session: {game_session}')
            self.stdout.write(f'  Status: {game_session.status}')
            self.stdout.write(f'  Players: {game_session.player_count}')
        except GameSession.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'✗ Game {game_code} not found'))
            return
        
        if test_type == 'simple_message':
            self.test_simple_message(game_code)
        elif test_type == 'player_join':
            self.test_player_join_broadcast(game_session)
    
    def test_simple_message(self, game_code):
        """Test a simple broadcast message"""
        self.stdout.write('📤 Sending simple test message...')
        
        test_data = {
            'message': f'Test broadcast at {time.strftime("%H:%M:%S")}',
            'timestamp': time.time()
        }
        
        try:
            broadcast_to_game(game_code, 'game_update', test_data)
            self.stdout.write('✓ Broadcast sent successfully')
            self.stdout.write('  Check your browser console and UI for updates')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ Broadcast failed: {e}'))
    
    def test_player_join_broadcast(self, game_session):
        """Test player join broadcast simulation"""
        self.stdout.write('📤 Simulating player join broadcast...')
        
        # Get current players
        players = game_session.players.filter(is_connected=True).order_by('joined_at')
        
        players_data = []
        for p in players:
            players_data.append({
                'id': p.id,
                'name': p.name,
                'joined_at': p.joined_at.strftime('%H:%M:%S'),
                'total_score': p.current_score,
            })
        
        broadcast_data = {
            'game_status': game_session.status,
            'player_count': players.count(),
            'players': players_data,
            'message': f'DEBUG: Player list update at {time.strftime("%H:%M:%S")}'
        }
        
        try:
            broadcast_to_game(game_session.game_code, 'game_update', broadcast_data)
            self.stdout.write('✓ Player join broadcast sent successfully')
            self.stdout.write(f'  Player count: {players.count()}')
            self.stdout.write(f'  Players: {[p["name"] for p in players_data]}')
            self.stdout.write('  Check your browser for real-time updates')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ Broadcast failed: {e}'))