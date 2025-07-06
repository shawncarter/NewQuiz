"""
Comprehensive tests for Mastermind round functionality.

These tests cover the complete mastermind round flow including:
- Player selection
- Ready responses  
- Rapid-fire questions
- Progress tracking
- Player completion
- WebSocket communication
"""

import asyncio
import json
from django.test import TestCase
from django.core.cache import cache
from channels.testing import WebsocketCommunicator
from unittest.mock import patch, MagicMock

from .models import GameSession, GameType, GameCategory, GameConfiguration, MultipleChoiceQuestion
from players.models import Player, PlayerAnswer
from .consumers import GameConsumer
from .round_handlers import MastermindRoundHandler
from .services import GameService


class MastermindRoundHandlerTest(TestCase):
    """Test MastermindRoundHandler business logic"""

    def setUp(self):
        """Set up test data"""
        self.game_type = GameType.objects.create(
            name="Quiz Game",
            description="Multiple choice quiz game"
        )
        
        # Create a game session
        self.game_session = GameSession.objects.create()
        self.config = GameConfiguration.objects.create(
            game_session=self.game_session,
            game_type=self.game_type,
            num_rounds=3,
            round_time_seconds=30,
            round_type_sequence=['mastermind', 'mastermind', 'mastermind']
        )
        
        # Create test players
        self.player1 = Player.objects.create(
            name="Alice",
            game_session=self.game_session,
            specialist_subject="Science"
        )
        self.player2 = Player.objects.create(
            name="Bob", 
            game_session=self.game_session,
            specialist_subject="History"
        )
        
        # Create test questions
        self.question1 = MultipleChoiceQuestion.objects.create(
            question_text="What is the capital of France?",
            choices=["London", "Berlin", "Paris", "Madrid"],
            correct_answer="Paris",
            category="Geography",
            is_specialist=True
        )
        self.question2 = MultipleChoiceQuestion.objects.create(
            question_text="What is 2+2?",
            choices=["3", "4", "5", "6"],
            correct_answer="4",
            category="Math",
            is_specialist=True
        )
        
        self.handler = MastermindRoundHandler(self.game_session, 1)

    def tearDown(self):
        """Clean up cache after each test"""
        cache.clear()

    def test_initial_state(self):
        """Test initial mastermind round state"""
        round_data = self.handler.generate_round_data()
        
        self.assertEqual(round_data['state'], 'waiting_for_player_selection')
        self.assertIn('available_players', round_data)
        self.assertIn('all_players', round_data)
        self.assertEqual(len(round_data['available_players']), 2)

    def test_player_selection(self):
        """Test selecting a player for mastermind round"""
        # Select player 1
        result = self.handler.select_player(self.player1.id)
        
        self.assertTrue(result['success'])
        self.assertEqual(result['selected_player']['name'], 'Alice')
        
        # Check state changed
        round_data = self.handler.generate_round_data()
        self.assertEqual(round_data['state'], 'asking_ready')
        self.assertEqual(round_data['current_player']['name'], 'Alice')

    def test_player_ready_response_yes(self):
        """Test player responding ready=yes"""
        # First select a player
        self.handler.select_player(self.player1.id)
        
        # Player responds ready
        with patch('game_sessions.round_handlers.MastermindRoundHandler.preload_player_questions') as mock_preload:
            mock_preload.return_value = [
                {
                    'question_text': 'Test question?',
                    'choices': ['A', 'B', 'C', 'D'],
                    'correct_answer': 'A',
                    'category': 'Test',
                    'is_ai_generated': False,
                    'question_id': 1
                }
            ]
            result = self.handler.player_ready_response(True)
        
        self.assertTrue(result['success'])
        
        # Check state changed to playing
        round_data = self.handler.generate_round_data()
        self.assertEqual(round_data['state'], 'playing')
        self.assertIn('question_text', round_data)

    def test_player_ready_response_no(self):
        """Test player responding ready=no"""
        # First select a player
        self.handler.select_player(self.player1.id)
        
        # Player responds not ready
        result = self.handler.player_ready_response(False)
        
        self.assertTrue(result['success'])
        
        # Check state returns to player selection
        round_data = self.handler.generate_round_data()
        self.assertEqual(round_data['state'], 'waiting_for_player_selection')

    def test_advance_to_next_question(self):
        """Test advancing through rapid-fire questions"""
        # Set up playing state
        self.handler.select_player(self.player1.id)
        
        with patch('game_sessions.round_handlers.MastermindRoundHandler.preload_player_questions') as mock_preload:
            mock_preload.return_value = [
                {'question_text': 'Q1', 'choices': ['A', 'B'], 'correct_answer': 'A', 'category': 'Test', 'is_ai_generated': False, 'question_id': 1},
                {'question_text': 'Q2', 'choices': ['C', 'D'], 'correct_answer': 'C', 'category': 'Test', 'is_ai_generated': False, 'question_id': 2}
            ]
            self.handler.player_ready_response(True)
        
        # Advance to next question
        self.handler.advance_to_next_question()
        
        round_data = self.handler.generate_round_data()
        self.assertEqual(round_data['current_question_index'], 1)
        self.assertEqual(round_data['question_text'], 'Q2')

    def test_player_completion(self):
        """Test player completing their rapid-fire round"""
        # Set up playing state with only 1 question
        self.handler.select_player(self.player1.id)
        
        with patch('game_sessions.round_handlers.MastermindRoundHandler.preload_player_questions') as mock_preload:
            mock_preload.return_value = [
                {'question_text': 'Q1', 'choices': ['A', 'B'], 'correct_answer': 'A', 'category': 'Test', 'is_ai_generated': False, 'question_id': 1}
            ]
            self.handler.player_ready_response(True)
        
        # Advance past the last question
        self.handler.advance_to_next_question()
        
        round_data = self.handler.generate_round_data()
        self.assertEqual(round_data['state'], 'player_complete')
        self.assertIn(self.player1.id, round_data['completed_players'])

    def test_all_players_complete(self):
        """Test when all players have completed their rounds"""
        # Mark both players as complete
        state = self.handler._get_round_state()
        state['completed_players'] = [self.player1.id, self.player2.id]
        state['state'] = 'all_complete'
        self.handler._save_round_state(state)
        
        round_data = self.handler.generate_round_data()
        self.assertEqual(round_data['state'], 'all_complete')
        self.assertEqual(round_data['phase'], 'general_knowledge')

    def test_question_preloading(self):
        """Test question pre-loading for players"""
        # Create enough questions for the test
        for i in range(25):
            MultipleChoiceQuestion.objects.create(
                question_text=f"Science question {i}?",
                choices=["A", "B", "C", "D"],
                correct_answer="A",
                category="Science",
                is_specialist=True
            )

        questions = self.handler.preload_player_questions(self.player1.id)

        self.assertIsInstance(questions, list)
        self.assertEqual(len(questions), self.handler.questions_per_player)

        # Check questions are cached
        cache_key = f'mastermind_questions_{self.game_session.game_code}_{self.player1.id}'
        cached_questions = cache.get(cache_key)
        self.assertIsNotNone(cached_questions)
        self.assertEqual(len(cached_questions), self.handler.questions_per_player)


class MastermindWebSocketTest(TestCase):
    """Test WebSocket communication for mastermind rounds"""

    def setUp(self):
        """Set up test data"""
        self.game_type = GameType.objects.create(
            name="Quiz Game",
            description="Multiple choice quiz game"
        )
        
        self.game_session = GameSession.objects.create()
        self.config = GameConfiguration.objects.create(
            game_session=self.game_session,
            game_type=self.game_type,
            num_rounds=1,
            round_time_seconds=30,
            round_type_sequence=['mastermind']
        )
        
        self.player = Player.objects.create(
            name="TestPlayer",
            game_session=self.game_session,
            specialist_subject="Science"
        )

    def tearDown(self):
        """Clean up cache after each test"""
        cache.clear()

    async def test_mastermind_select_player_message(self):
        """Test mastermind player selection via WebSocket"""
        # Set up active game and round
        self.game_session.status = 'active'
        self.game_session.current_round_number = 1
        self.game_session.is_round_active = True
        await self.sync_to_async_save(self.game_session)

        communicator = WebsocketCommunicator(
            GameConsumer.as_asgi(),
            f"/ws/game/{self.game_session.game_code}/"
        )

        connected, subprotocol = await communicator.connect()
        self.assertTrue(connected)

        # Consume initial game state
        await communicator.receive_json_from()

        # Send player selection message
        await communicator.send_json_to({
            'type': 'mastermind_select_player',
            'player_id': self.player.id
        })

        # Should receive round update
        response = await communicator.receive_json_from()
        self.assertEqual(response['type'], 'round_update')
        self.assertEqual(response['data']['state'], 'asking_ready')

        await communicator.disconnect()

    @staticmethod
    def sync_to_async_save(obj):
        """Helper to save objects in async context"""
        from asgiref.sync import sync_to_async
        return sync_to_async(obj.save)()

    async def test_mastermind_ready_response_message(self):
        """Test mastermind ready response via WebSocket"""
        # Set up active game and round
        self.game_session.status = 'active'
        self.game_session.current_round_number = 1
        self.game_session.is_round_active = True
        await self.sync_to_async_save(self.game_session)

        communicator = WebsocketCommunicator(
            GameConsumer.as_asgi(),
            f"/ws/game/{self.game_session.game_code}/"
        )

        connected, subprotocol = await communicator.connect()
        self.assertTrue(connected)

        # Consume initial game state
        await communicator.receive_json_from()

        # First select a player
        await communicator.send_json_to({
            'type': 'mastermind_select_player',
            'player_id': self.player.id
        })
        await communicator.receive_json_from()  # Consume round update

        # Send ready response
        with patch('game_sessions.round_handlers.MastermindRoundHandler.preload_player_questions') as mock_preload:
            mock_preload.return_value = [{'question_text': 'Test?', 'choices': ['A'], 'correct_answer': 'A', 'category': 'Test', 'is_ai_generated': False, 'question_id': 1}]

            await communicator.send_json_to({
                'type': 'mastermind_gm_ready_response',
                'is_ready': True
            })

        # Should receive round started
        response = await communicator.receive_json_from()
        self.assertIn(response['type'], ['round_started', 'round_update'])

        await communicator.disconnect()

    def test_mastermind_select_player_sync(self):
        """Synchronous wrapper for mastermind player selection test"""
        asyncio.run(self.test_mastermind_select_player_message())

    def test_mastermind_ready_response_sync(self):
        """Synchronous wrapper for mastermind ready response test"""
        asyncio.run(self.test_mastermind_ready_response_message())


class MastermindIntegrationTest(TestCase):
    """Integration tests for complete mastermind flows"""

    def setUp(self):
        """Set up test data"""
        self.game_type = GameType.objects.create(
            name="Quiz Game",
            description="Multiple choice quiz game"
        )
        
        self.game_session = GameSession.objects.create()
        self.config = GameConfiguration.objects.create(
            game_session=self.game_session,
            game_type=self.game_type,
            num_rounds=1,
            round_time_seconds=30,
            round_type_sequence=['mastermind']
        )
        
        self.player1 = Player.objects.create(
            name="Alice",
            game_session=self.game_session,
            specialist_subject="Science"
        )
        self.player2 = Player.objects.create(
            name="Bob",
            game_session=self.game_session,
            specialist_subject="History"
        )

    def tearDown(self):
        """Clean up cache after each test"""
        cache.clear()

    def test_complete_mastermind_flow(self):
        """Test complete mastermind round from start to finish"""
        # Start the game
        self.game_session.status = 'active'
        self.game_session.save()
        
        game_service = GameService(self.game_session)
        
        # Start mastermind round
        with patch('game_sessions.services.broadcast_round_started'), \
             patch('game_sessions.services.start_timer_broadcast'):
            result = game_service.start_round()
        
        self.assertTrue(result['success'])
        self.assertEqual(result['round_type'], 'mastermind')
        
        # Get round handler
        from .round_handlers import get_round_handler
        handler = get_round_handler(self.game_session, 1)
        
        # Select first player
        select_result = handler.select_player(self.player1.id)
        self.assertTrue(select_result['success'])
        
        # Player responds ready
        with patch('game_sessions.round_handlers.MastermindRoundHandler.preload_player_questions') as mock_preload:
            mock_preload.return_value = [
                {'question_text': 'Q1', 'choices': ['A', 'B'], 'correct_answer': 'A', 'category': 'Test', 'is_ai_generated': False, 'question_id': 1},
                {'question_text': 'Q2', 'choices': ['C', 'D'], 'correct_answer': 'C', 'category': 'Test', 'is_ai_generated': False, 'question_id': 2}
            ]
            ready_result = handler.player_ready_response(True)
        
        self.assertTrue(ready_result['success'])
        
        # Simulate rapid-fire completion
        handler.advance_to_next_question()  # Complete Q1
        handler.advance_to_next_question()  # Complete Q2, should mark player complete
        
        round_data = handler.generate_round_data()
        self.assertEqual(round_data['state'], 'player_complete')
        self.assertIn(self.player1.id, round_data['completed_players'])
