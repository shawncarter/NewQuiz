"""
Tests for Service Classes

These tests focus on testing the business logic in our service classes,
separate from the HTTP layer. This makes testing faster and more focused.
"""

from django.test import TestCase
from django.utils import timezone
from unittest.mock import patch

from .models import GameSession, GameType, GameCategory, GameConfiguration
from players.models import Player, PlayerAnswer
from .services import GameService, PlayerService


class GameServiceTest(TestCase):
    """Test GameService business logic"""

    def setUp(self):
        """Set up test data"""
        self.game_type = GameType.objects.create(
            name="Flower, Fruit & Veg",
            description="Players think of items in specific categories that start with a given letter"
        )
        self.category = GameCategory.objects.create(
            name="Flowers",
            game_type=self.game_type
        )
        
        # Create a game session
        self.game_session = GameSession.objects.create()
        self.config = GameConfiguration.objects.create(
            game_session=self.game_session,
            game_type=self.game_type,
            num_rounds=3,
            round_time_seconds=30,
            round_type_sequence=['flower_fruit_veg', 'flower_fruit_veg', 'flower_fruit_veg']
        )
        self.config.categories.add(self.category)
        
        self.game_service = GameService(self.game_session)

    def test_start_game_success(self):
        """Test successfully starting a game with players"""
        # Add a player
        Player.objects.create(
            name="Test Player",
            game_session=self.game_session
        )
        
        with patch('game_sessions.services.broadcast_to_game') as mock_broadcast:
            result = self.game_service.start_game()
        
        # Check result
        self.assertTrue(result['success'])
        self.assertIn('Game started', result['message'])
        
        # Check game state changed
        self.game_session.refresh_from_db()
        self.assertEqual(self.game_session.status, 'active')
        self.assertIsNotNone(self.game_session.started_at)
        
        # Check broadcast was called
        mock_broadcast.assert_called_once()

    def test_start_game_no_players(self):
        """Test starting game with no players fails"""
        result = self.game_service.start_game()
        
        # Check result
        self.assertFalse(result['success'])
        self.assertIn('No players', result['error'])
        
        # Check game state unchanged
        self.game_session.refresh_from_db()
        self.assertEqual(self.game_session.status, 'waiting')
        self.assertIsNone(self.game_session.started_at)

    def test_start_game_already_active(self):
        """Test starting game that's already active fails"""
        self.game_session.status = 'active'
        self.game_session.save()
        
        result = self.game_service.start_game()
        
        # Check result
        self.assertFalse(result['success'])
        self.assertIn('not in waiting state', result['error'])

    def test_start_round_success(self):
        """Test successfully starting a round"""
        # Prepare game
        self.game_session.status = 'active'
        self.game_session.save()
        
        # Add a player
        Player.objects.create(name="Test Player", game_session=self.game_session)
        
        with patch('game_sessions.services.broadcast_round_started') as mock_broadcast, \
             patch('game_sessions.websocket_utils.start_timer_broadcast') as mock_timer:
            result = self.game_service.start_round()
        
        # Check result
        self.assertTrue(result['success'])
        self.assertEqual(result['round_number'], 1)
        self.assertEqual(result['round_type'], 'flower_fruit_veg')
        
        # Check game state
        self.game_session.refresh_from_db()
        self.assertEqual(self.game_session.current_round_number, 1)
        self.assertTrue(self.game_session.is_round_active)
        self.assertIsNotNone(self.game_session.current_round_started_at)
        
        # Check broadcasts
        mock_broadcast.assert_called_once()
        mock_timer.assert_called_once()

    def test_start_round_game_not_active(self):
        """Test starting round when game is not active"""
        result = self.game_service.start_round()
        
        # Check result
        self.assertFalse(result['success'])
        self.assertIn('Game is not active', result['error'])

    def test_start_round_game_complete(self):
        """Test starting round when game is already complete"""
        # Prepare game with all rounds completed
        self.game_session.status = 'active'
        self.game_session.current_round_number = 3  # Equal to num_rounds
        self.game_session.save()
        
        # Add a player
        Player.objects.create(name="Test Player", game_session=self.game_session)
        
        with patch('game_sessions.services.broadcast_to_game') as mock_broadcast:
            result = self.game_service.start_round()
        
        # Check result indicates game finished
        self.assertTrue(result['success'])
        self.assertEqual(result['status'], 'game_complete')
        self.assertIn('final_scores', result)
        
        # Check game state
        self.game_session.refresh_from_db()
        self.assertEqual(self.game_session.status, 'finished')
        self.assertIsNotNone(self.game_session.finished_at)

    def test_end_round_success(self):
        """Test successfully ending a round"""
        # Set up active round
        self.game_session.status = 'active'
        self.game_session.current_round_number = 1
        self.game_session.is_round_active = True
        self.game_session.current_round_started_at = timezone.now()
        self.game_session.save()
        
        # Add player with answer
        player = Player.objects.create(name="Test Player", game_session=self.game_session)
        PlayerAnswer.objects.create(
            player=player,
            round_number=1,
            answer_text="Rose",
            is_valid=True,
            points_awarded=10
        )
        
        with patch('game_sessions.services.broadcast_round_ended') as mock_broadcast:
            result = self.game_service.end_round()
        
        # Check result
        self.assertTrue(result['success'])
        self.assertEqual(result['round_number'], 1)
        self.assertEqual(result['round_type'], 'flower_fruit_veg')
        self.assertEqual(len(result['answers']), 1)
        self.assertEqual(result['answers'][0]['player_name'], 'Test Player')
        self.assertEqual(result['answers'][0]['answer_text'], 'Rose')
        
        # Check game state
        self.game_session.refresh_from_db()
        self.assertFalse(self.game_session.is_round_active)
        
        # Check broadcast
        mock_broadcast.assert_called_once()

    def test_end_round_no_active_round(self):
        """Test ending round when no round is active"""
        result = self.game_service.end_round()
        
        # Check result
        self.assertFalse(result['success'])
        self.assertIn('No active round', result['error'])

    def test_restart_game_success(self):
        """Test successfully restarting a game"""
        # Set up finished game
        self.game_session.status = 'finished'
        self.game_session.current_round_number = 3
        self.game_session.save()
        
        # Add players with scores
        player1 = Player.objects.create(
            name="Player 1", 
            game_session=self.game_session, 
            current_score=50
        )
        player2 = Player.objects.create(
            name="Player 2", 
            game_session=self.game_session, 
            current_score=30
        )
        
        with patch('game_sessions.services.broadcast_to_game') as mock_broadcast:
            result = self.game_service.restart_game()
        
        # Check result
        self.assertTrue(result['success'])
        self.assertIn('restarted successfully', result['message'])
        
        # Check game state reset
        self.game_session.refresh_from_db()
        self.assertEqual(self.game_session.status, 'waiting')
        self.assertEqual(self.game_session.current_round_number, 0)
        self.assertFalse(self.game_session.is_round_active)
        
        # Check players reset
        player1.refresh_from_db()
        player2.refresh_from_db()
        self.assertEqual(player1.current_score, 0)
        self.assertEqual(player2.current_score, 0)
        self.assertTrue(player1.is_connected)
        self.assertTrue(player2.is_connected)

    def test_restart_game_invalid_status(self):
        """Test restarting game with invalid status"""
        # Game is still waiting
        result = self.game_service.restart_game()
        
        # Check result
        self.assertFalse(result['success'])
        self.assertIn('can only be restarted when active or finished', result['error'])

    def test_process_cached_answers(self):
        """Test processing cached answers into database with new cache service"""
        # Set up active round
        self.game_session.current_round_number = 1
        self.game_session.save()
        
        # Add player
        player = Player.objects.create(
            name="Test Player", 
            game_session=self.game_session, 
            is_connected=True
        )
        
        # Use the actual cache service to set up test data
        from game_sessions.cache_service import get_game_cache
        game_cache = get_game_cache(self.game_session.game_code)
        game_cache.cache_player_answer(1, player.id, "Rose")
        
        # Test processing
        self.game_service._process_cached_answers()
        
        # Check PlayerAnswer was created
        answer = PlayerAnswer.objects.get(player=player, round_number=1)
        self.assertEqual(answer.answer_text, "Rose")
        
        # Check cache was cleared (should return empty dict)
        cached_answers = game_cache.get_cached_answers(1)
        self.assertEqual(cached_answers, {})

    def test_format_answer_data(self):
        """Test formatting answer data for response"""
        # Create player and answer
        player = Player.objects.create(name="Test Player", game_session=self.game_session)
        answer = PlayerAnswer.objects.create(
            player=player,
            round_number=1,
            answer_text="Rose",
            points_awarded=10,
            is_valid=True,
            is_unique=True
        )
        
        # Test formatting
        result = self.game_service._format_answer_data([answer])
        
        # Check result
        self.assertEqual(len(result), 1)
        answer_data = result[0]
        self.assertEqual(answer_data['player_name'], 'Test Player')
        self.assertEqual(answer_data['answer_text'], 'Rose')
        self.assertEqual(answer_data['points_awarded'], 10)
        self.assertTrue(answer_data['is_valid'])
        self.assertTrue(answer_data['is_unique'])


class PlayerServiceTest(TestCase):
    """Test PlayerService business logic"""

    def setUp(self):
        """Set up test data"""
        self.game_type = GameType.objects.create(
            name="Flower, Fruit & Veg",
            description="Players think of items in specific categories that start with a given letter"
        )
        
        # Create a game session
        self.game_session = GameSession.objects.create()
        self.config = GameConfiguration.objects.create(
            game_session=self.game_session,
            game_type=self.game_type,
            num_rounds=3,
            round_time_seconds=30
        )

    def test_join_game_success(self):
        """Test successfully joining a game"""
        with patch('game_sessions.services.PlayerService._broadcast_player_join') as mock_broadcast:
            result = PlayerService.join_game(self.game_session.game_code, "Test Player")
        
        # Check result
        self.assertTrue(result['success'])
        self.assertIn('Joined game', result['message'])
        self.assertEqual(result['player'].name, 'Test Player')
        self.assertEqual(result['game_session'], self.game_session)
        
        # Check player was created
        player = Player.objects.get(game_session=self.game_session)
        self.assertEqual(player.name, 'Test Player')
        self.assertTrue(player.is_connected)
        
        # Check broadcast
        mock_broadcast.assert_called_once()

    def test_join_game_missing_data(self):
        """Test joining with missing game code or name"""
        # Missing game code
        result = PlayerService.join_game("", "Test Player")
        self.assertFalse(result['success'])
        self.assertIn('provide both', result['error'])
        
        # Missing player name
        result = PlayerService.join_game(self.game_session.game_code, "")
        self.assertFalse(result['success'])
        self.assertIn('provide both', result['error'])

    def test_join_nonexistent_game(self):
        """Test joining a game that doesn't exist"""
        result = PlayerService.join_game("NONEXIST", "Test Player")
        
        # Check result
        self.assertFalse(result['success'])
        self.assertIn('Game not found', result['error'])
        
        # No player should be created
        self.assertEqual(Player.objects.count(), 0)

    def test_join_full_game(self):
        """Test joining a game that's at capacity"""
        # Set max players to 1
        self.game_session.max_players = 1
        self.game_session.save()
        
        # Add one player
        Player.objects.create(name="Player 1", game_session=self.game_session)
        
        # Try to add second player
        result = PlayerService.join_game(self.game_session.game_code, "Player 2")
        
        # Check result
        self.assertFalse(result['success'])
        self.assertIn('Cannot join', result['error'])
        
        # Should still only have one player
        self.assertEqual(Player.objects.count(), 1)

    def test_join_active_game(self):
        """Test joining a game that has already started"""
        self.game_session.status = 'active'
        self.game_session.save()
        
        result = PlayerService.join_game(self.game_session.game_code, "Test Player")
        
        # Check result
        self.assertFalse(result['success'])
        self.assertIn('Cannot join', result['error'])

    def test_player_reconnection(self):
        """Test existing player reconnecting"""
        # Create existing player who was disconnected
        existing_player = Player.objects.create(
            name="Test Player",
            game_session=self.game_session,
            is_connected=False
        )
        
        with patch('game_sessions.services.PlayerService._broadcast_player_join'):
            result = PlayerService.join_game(self.game_session.game_code, "Test Player")
        
        # Check result
        self.assertTrue(result['success'])
        self.assertEqual(result['player'].id, existing_player.id)
        
        # Check player was reconnected
        existing_player.refresh_from_db()
        self.assertTrue(existing_player.is_connected)
        
        # Should still only have one player
        self.assertEqual(Player.objects.count(), 1)

    @patch('game_sessions.services.broadcast_to_game')
    def test_broadcast_player_join(self, mock_broadcast):
        """Test player join broadcast functionality"""
        # Create players
        player1 = Player.objects.create(name="Player 1", game_session=self.game_session)
        player2 = Player.objects.create(name="Player 2", game_session=self.game_session)
        
        # Test broadcast
        PlayerService._broadcast_player_join(self.game_session, player2)
        
        # Check broadcast was called with correct data
        mock_broadcast.assert_called_once()
        call_args = mock_broadcast.call_args
        
        # Check broadcast parameters
        self.assertEqual(call_args[0][0], self.game_session.game_code)
        self.assertEqual(call_args[0][1], 'game_update')
        
        broadcast_data = call_args[0][2]
        self.assertEqual(broadcast_data['player_count'], 2)
        self.assertEqual(len(broadcast_data['players']), 2)
        self.assertIn('Player 2 joined', broadcast_data['message'])


class ServiceIntegrationTest(TestCase):
    """Integration tests for service workflows"""

    def setUp(self):
        """Set up test data"""
        self.game_type = GameType.objects.create(
            name="Flower, Fruit & Veg",
            description="Players think of items in specific categories that start with a given letter"
        )
        self.category = GameCategory.objects.create(
            name="Flowers",
            game_type=self.game_type
        )

    def test_complete_game_flow(self):
        """Test complete game flow from creation to completion"""
        # 1. Create game
        game_session = GameSession.objects.create()
        config = GameConfiguration.objects.create(
            game_session=game_session,
            game_type=self.game_type,
            num_rounds=2,  # Short game for testing
            round_time_seconds=30,
            round_type_sequence=['flower_fruit_veg', 'flower_fruit_veg']
        )
        config.categories.add(self.category)
        
        # 2. Players join
        with patch('game_sessions.services.PlayerService._broadcast_player_join'):
            result1 = PlayerService.join_game(game_session.game_code, "Player 1")
            result2 = PlayerService.join_game(game_session.game_code, "Player 2")
        
        self.assertTrue(result1['success'])
        self.assertTrue(result2['success'])
        self.assertEqual(Player.objects.filter(game_session=game_session).count(), 2)
        
        # 3. Start game
        game_service = GameService(game_session)
        with patch('game_sessions.services.broadcast_to_game'):
            start_result = game_service.start_game()
        
        self.assertTrue(start_result['success'])
        game_session.refresh_from_db()
        self.assertEqual(game_session.status, 'active')
        
        # 4. Start first round
        with patch('game_sessions.services.broadcast_round_started'), \
             patch('game_sessions.services.start_timer_broadcast'):
            round1_result = game_service.start_round()
        
        self.assertTrue(round1_result['success'])
        self.assertEqual(round1_result['round_number'], 1)
        
        # 5. Players submit answers (simulate via PlayerAnswer creation)
        players = Player.objects.filter(game_session=game_session)
        PlayerAnswer.objects.create(
            player=players[0], round_number=1, answer_text="Rose", points_awarded=10
        )
        PlayerAnswer.objects.create(
            player=players[1], round_number=1, answer_text="Tulip", points_awarded=10
        )
        
        # 6. End first round
        with patch('game_sessions.services.broadcast_round_ended'):
            end1_result = game_service.end_round()
        
        self.assertTrue(end1_result['success'])
        self.assertEqual(len(end1_result['answers']), 2)
        self.assertFalse(end1_result['is_final_round'])
        
        # 7. Start second round
        with patch('game_sessions.services.broadcast_round_started'), \
             patch('game_sessions.services.start_timer_broadcast'):
            round2_result = game_service.start_round()
        
        self.assertTrue(round2_result['success'])
        self.assertEqual(round2_result['round_number'], 2)
        
        # 8. End second round (final round)
        PlayerAnswer.objects.create(
            player=players[0], round_number=2, answer_text="Daisy", points_awarded=10
        )
        
        with patch('game_sessions.services.broadcast_round_ended'):
            end2_result = game_service.end_round()
        
        self.assertTrue(end2_result['success'])
        self.assertTrue(end2_result['is_final_round'])
        
        # 9. Try to start next round (should finish game)
        with patch('game_sessions.services.broadcast_to_game'):
            finish_result = game_service.start_round()
        
        self.assertTrue(finish_result['success'])
        self.assertEqual(finish_result['status'], 'game_complete')
        self.assertIn('final_scores', finish_result)
        
        game_session.refresh_from_db()
        self.assertEqual(game_session.status, 'finished')

    def test_game_restart_flow(self):
        """Test game restart workflow"""
        # Create finished game with players and scores
        game_session = GameSession.objects.create(status='finished', current_round_number=3)
        config = GameConfiguration.objects.create(
            game_session=game_session,
            game_type=self.game_type,
            num_rounds=3,
            round_time_seconds=30
        )
        
        # Add players with scores
        player1 = Player.objects.create(
            name="Player 1", game_session=game_session, current_score=50
        )
        player2 = Player.objects.create(
            name="Player 2", game_session=game_session, current_score=30
        )
        
        # Add duplicate player (to test cleanup)
        duplicate = Player.objects.create(
            name="Player 1", game_session=game_session, current_score=0
        )
        
        # Restart game
        game_service = GameService(game_session)
        with patch('game_sessions.services.broadcast_to_game'):
            restart_result = game_service.restart_game()
        
        self.assertTrue(restart_result['success'])
        
        # Check game state reset
        game_session.refresh_from_db()
        self.assertEqual(game_session.status, 'waiting')
        self.assertEqual(game_session.current_round_number, 0)
        
        # Check players reset and duplicates removed
        remaining_players = Player.objects.filter(game_session=game_session).order_by('joined_at')
        self.assertEqual(remaining_players.count(), 2)  # Duplicate should be removed
        
        for player in remaining_players:
            self.assertEqual(player.current_score, 0)
            self.assertTrue(player.is_connected)