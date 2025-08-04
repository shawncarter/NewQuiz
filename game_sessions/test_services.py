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

    def test_timer_expiry_saves_cached_answers(self):
        """Test that timer expiry logic properly saves cached answers to database (FFV bug fix)"""
        from unittest.mock import patch, MagicMock
        from game_sessions.cache_service import get_game_cache
        from players.models import PlayerAnswer
        from django.core.cache import cache

        # Set up active round
        self.game_session.status = 'active'
        self.game_session.current_round_number = 1
        self.game_session.is_round_active = True
        self.game_session.current_round_started_at = timezone.now()
        self.game_session.save()

        # Create connected player
        player = Player.objects.create(
            name="Test Player",
            game_session=self.game_session,
            is_connected=True
        )

        # Cache a player answer (simulating WebSocket submission)
        game_cache = get_game_cache(self.game_session.game_code)
        game_cache.cache_player_answer(1, player.id, "Rose")

        # Verify answer is cached but not in database yet
        cached_answers = game_cache.get_cached_answers(1)
        self.assertEqual(cached_answers[str(player.id)], "Rose")
        self.assertEqual(PlayerAnswer.objects.filter(player=player, round_number=1).count(), 0)

        # Directly test the timer expiry logic without threading to avoid database locks
        # This simulates what happens in the timer_worker function when time_remaining <= 0

        # Import the necessary modules
        from game_sessions.models import GameSession
        from game_sessions.round_handlers import get_round_handler

        # Simulate the timer expiry logic from websocket_utils.py
        current_game = GameSession.objects.get(game_code=self.game_session.game_code)
        if current_game.is_round_active:
            # End the round
            current_game.is_round_active = False
            current_game.save()

            # Get current round info
            round_info = current_game.get_current_round_info()
            if round_info:
                # Transfer cached answers to database (the fixed logic)
                cache_key = f'game_{current_game.game_code}_round_{current_game.current_round_number}_answers'
                cached_answers = cache.get(cache_key, {})

                if cached_answers:
                    # Get round handler for creating PlayerAnswer objects
                    round_handler = get_round_handler(current_game, current_game.current_round_number)

                    # Get all connected players in one query for efficiency
                    player_ids = [int(pid) for pid in cached_answers.keys() if pid.isdigit()]
                    connected_players = {
                        p.id: p for p in Player.objects.filter(
                            id__in=player_ids,
                            game_session=current_game,
                            is_connected=True
                        ).select_related('game_session')
                    }

                    # Check for existing answers to avoid duplicates
                    existing_answers = set(
                        PlayerAnswer.objects.filter(
                            player__in=connected_players.values(),
                            round_number=current_game.current_round_number
                        ).values_list('player_id', flat=True)
                    )

                    # Collect answers to create
                    answers_to_create = []

                    # Create PlayerAnswer objects for any cached answers that don't exist in DB
                    for player_id_str, answer_text in cached_answers.items():
                        try:
                            player_id = int(player_id_str)
                            player_obj = connected_players.get(player_id)

                            if player_obj and player_id not in existing_answers and answer_text.strip():
                                # Use round handler to create appropriate PlayerAnswer
                                answer_obj = round_handler.create_player_answer(player_obj, answer_text.strip())
                                if answer_obj:  # Some handlers return the object, others save directly
                                    answers_to_create.append(answer_obj)

                        except (ValueError, KeyError):
                            pass

                    # Bulk create if we have answers to create (same as manual end_round)
                    if answers_to_create:
                        PlayerAnswer.objects.bulk_create(answers_to_create, ignore_conflicts=True)

                # Clear the cache for this round
                cache.delete(cache_key)

        # Verify the cached answer was saved to database
        self.game_session.refresh_from_db()
        self.assertFalse(self.game_session.is_round_active)  # Round should be ended

        # Check that PlayerAnswer was created
        answers = PlayerAnswer.objects.filter(player=player, round_number=1)
        self.assertEqual(answers.count(), 1)
        answer = answers.first()
        self.assertEqual(answer.answer_text, "Rose")
        self.assertFalse(answer.is_valid)  # FFV answers start invalid
        self.assertEqual(answer.points_awarded, 0)

        # Verify cache was cleared
        cached_answers_after = game_cache.get_cached_answers(1)
        self.assertEqual(cached_answers_after, {})

    def test_validation_status_check(self):
        """Test the validation status endpoint for FFV rounds"""
        from django.test import Client
        from django.urls import reverse
        from players.models import PlayerAnswer, ScoreHistory

        # Set up active FFV round
        self.game_session.status = 'active'
        self.game_session.current_round_number = 1
        self.game_session.is_round_active = False  # Round ended, answers being validated
        self.game_session.save()

        # Create connected players
        player1 = Player.objects.create(
            name="Player 1",
            game_session=self.game_session,
            is_connected=True
        )
        player2 = Player.objects.create(
            name="Player 2",
            game_session=self.game_session,
            is_connected=True
        )

        # Create FFV answers (start as invalid, need validation)
        answer1 = PlayerAnswer.objects.create(
            player=player1,
            round_number=1,
            answer_text="Rose",
            is_valid=False,  # FFV answers start invalid
            points_awarded=0
        )
        answer2 = PlayerAnswer.objects.create(
            player=player2,
            round_number=1,
            answer_text="Tulip",
            is_valid=False,  # FFV answers start invalid
            points_awarded=0
        )

        client = Client()
        url = reverse('game_sessions:check_validation_status', args=[self.game_session.game_code])

        # Test 1: No answers validated yet
        response = client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertFalse(data['all_validated'])
        self.assertEqual(data['total_answers'], 2)
        self.assertEqual(data['validated_answers'], 0)
        self.assertEqual(data['round_type'], 'flower_fruit_veg')

        # Test 2: Validate one answer by creating ScoreHistory entry
        ScoreHistory.objects.create(
            player=player1,
            game_session=self.game_session,
            round_number=1,
            points_change=10,
            reason="manual_validation",
            related_answer=answer1
        )
        answer1.is_valid = True
        answer1.points_awarded = 10
        answer1.save()

        response = client.get(url)
        data = response.json()
        self.assertFalse(data['all_validated'])
        self.assertEqual(data['validated_answers'], 1)

        # Test 3: Mark second answer as invalid using the actual validation method
        # This should create a ScoreHistory entry even though the answer is invalid
        from game_sessions.round_handlers import get_round_handler
        round_handler = get_round_handler(self.game_session, 1)

        # Use the actual validation method to mark as invalid
        points_awarded = round_handler.validate_answer_manually(answer2, False)

        # Verify the answer was marked as invalid but ScoreHistory was created
        answer2.refresh_from_db()
        self.assertFalse(answer2.is_valid)  # Should be invalid
        self.assertEqual(answer2.points_awarded, 0)  # Should have 0 points
        self.assertEqual(points_awarded, 0)  # Method should return 0 points

        # Verify ScoreHistory entry was created for the invalid answer
        invalid_score_history = ScoreHistory.objects.filter(
            player=player2,
            round_number=1,
            related_answer=answer2
        )
        self.assertTrue(invalid_score_history.exists())  # ScoreHistory should exist

        response = client.get(url)
        data = response.json()
        self.assertTrue(data['all_validated'])  # Both answers now marked (one valid, one invalid)
        self.assertEqual(data['validated_answers'], 2)

        # Test 4: Test with no answers (should return all_validated=True)
        PlayerAnswer.objects.filter(player__game_session=self.game_session).delete()
        response = client.get(url)
        data = response.json()
        self.assertTrue(data['all_validated'])  # No answers to validate
        self.assertEqual(data['total_answers'], 0)
        self.assertEqual(data['validated_answers'], 0)

    def test_multiple_choice_round_creation(self):
        """Test that multiple choice rounds can be created without type errors"""
        from game_sessions.round_handlers import get_round_handler
        from game_sessions.models import MultipleChoiceQuestion

        # Create a test multiple choice question
        MultipleChoiceQuestion.objects.create(
            question_text="What is 2 + 2?",
            choices=["3", "4", "5", "6"],
            correct_answer="4",
            category="Math",
            is_ai_generated=False
        )

        # Configure game session for multiple choice rounds
        self.game_session.status = 'active'
        self.game_session.current_round_number = 1
        self.game_session.save()

        # Update configuration to use multiple choice rounds
        self.game_session.configuration.round_type_sequence = ['multiple_choice']
        self.game_session.configuration.save()

        # Get multiple choice round handler
        round_handler = get_round_handler(self.game_session, 1)

        # This should not raise a TypeError about MultipleChoiceQuestion vs Question
        try:
            round_info = round_handler.get_round_info()
            self.assertIsNotNone(round_info)
            self.assertEqual(round_info['round_type'], 'multiple_choice')
            # Should have question data
            self.assertIn('question_text', round_info)
            self.assertIn('choices', round_info)
            self.assertIn('correct_answer', round_info)
        except TypeError as e:
            if 'MultipleChoiceQuestion' in str(e) and 'Question' in str(e):
                self.fail(f"Type mismatch error in multiple choice round creation: {e}")
            else:
                raise  # Re-raise if it's a different TypeError

    def test_question_exclusion_prevents_repeats(self):
        """Test that questions used in a game session are not repeated"""
        from game_sessions.models import MultipleChoiceQuestion
        from game_sessions.ai_questions import get_question_for_game_with_exclusions

        # Create multiple test questions
        question1 = MultipleChoiceQuestion.objects.create(
            question_text="What is 2 + 2?",
            choices=["3", "4", "5", "6"],
            correct_answer="4",
            category="Math",
            is_ai_generated=False
        )
        question2 = MultipleChoiceQuestion.objects.create(
            question_text="What is 3 + 3?",
            choices=["5", "6", "7", "8"],
            correct_answer="6",
            category="Math",
            is_ai_generated=False
        )
        question3 = MultipleChoiceQuestion.objects.create(
            question_text="What is 4 + 4?",
            choices=["7", "8", "9", "10"],
            correct_answer="8",
            category="Math",
            is_ai_generated=False
        )

        # Mark question1 as used in this game session
        self.game_session.used_questions.add(question1)

        # Get a question excluding the used one
        new_question = get_question_for_game_with_exclusions(
            category="Math",
            exclude_question_ids=[question1.id],
            force_ai_generation=False  # Force use of existing questions
        )

        # Should get question2 or question3, but not question1
        self.assertIsNotNone(new_question)
        self.assertNotEqual(new_question.id, question1.id)
        self.assertIn(new_question.id, [question2.id, question3.id])

        # Verify the question was marked as used
        new_question.refresh_from_db()
        self.assertIsNotNone(new_question.last_used)
        self.assertGreater(new_question.usage_count, 0)

    def test_questions_excluded_across_different_games(self):
        """Test that questions used in one game are excluded from subsequent games"""
        from game_sessions.models import MultipleChoiceQuestion, GameSession, GameConfiguration, GameType
        from game_sessions.ai_questions import get_question_for_game_with_exclusions
        from django.utils import timezone
        from datetime import timedelta

        # Create multiple test questions
        question1 = MultipleChoiceQuestion.objects.create(
            question_text="What is 5 + 5?",
            choices=["8", "9", "10", "11"],
            correct_answer="10",
            category="Math",
            is_ai_generated=False
        )
        question2 = MultipleChoiceQuestion.objects.create(
            question_text="What is 6 + 6?",
            choices=["10", "11", "12", "13"],
            correct_answer="12",
            category="Math",
            is_ai_generated=False
        )

        # Simulate question1 being used in a previous game (mark as recently used)
        question1.last_used = timezone.now()
        question1.usage_count = 1
        question1.save()

        # Create a new game session
        new_game = GameSession.objects.create(status='active', current_round_number=1)
        GameConfiguration.objects.create(
            game_session=new_game,
            game_type=self.game_type,
            round_type_sequence=['multiple_choice']
        )

        # Try to get a question for the new game with exclude_recent_days=1
        new_question = get_question_for_game_with_exclusions(
            category="Math",
            exclude_question_ids=[],  # No game-specific exclusions
            exclude_recent_days=1,    # Exclude questions used in last 1 day
            force_ai_generation=False
        )

        # Should get question2, not question1 (which was used recently)
        self.assertIsNotNone(new_question)
        self.assertEqual(new_question.id, question2.id)
        self.assertNotEqual(new_question.id, question1.id)

        # Test with exclude_recent_days=0 (should allow recently used questions)
        question_with_no_exclusion = get_question_for_game_with_exclusions(
            category="Math",
            exclude_question_ids=[],
            exclude_recent_days=0,  # Don't exclude recently used questions
            force_ai_generation=False
        )

        # Now it could return either question (including the recently used one)
        self.assertIsNotNone(question_with_no_exclusion)
        self.assertIn(question_with_no_exclusion.id, [question1.id, question2.id])

    def test_mastermind_available_players_logic(self):
        """Test that Mastermind rounds correctly identify available players"""
        from mastermind.models import MastermindRound
        from players.models import Player

        # Create players with different specialist subject configurations
        player_with_subject = Player.objects.create(
            name="Player With Subject",
            game_session=self.game_session,
            is_connected=True,
            specialist_subject="History"
        )
        player_without_subject = Player.objects.create(
            name="Player Without Subject",
            game_session=self.game_session,
            is_connected=True,
            specialist_subject=None
        )
        player_empty_subject = Player.objects.create(
            name="Player Empty Subject",
            game_session=self.game_session,
            is_connected=True,
            specialist_subject=""
        )
        player_disconnected = Player.objects.create(
            name="Player Disconnected",
            game_session=self.game_session,
            is_connected=False,
            specialist_subject="Science"
        )

        # Create a mastermind round
        mastermind_round = MastermindRound.objects.create(
            game_session=self.game_session,
            round_number=1
        )

        # Get available players
        available_players = mastermind_round.get_available_players()

        # Should only include player_with_subject
        self.assertEqual(available_players.count(), 1)
        self.assertEqual(available_players.first().id, player_with_subject.id)

        # Verify excluded players
        available_player_ids = list(available_players.values_list('id', flat=True))
        self.assertNotIn(player_without_subject.id, available_player_ids)  # No specialist subject
        self.assertNotIn(player_empty_subject.id, available_player_ids)    # Empty specialist subject
        self.assertNotIn(player_disconnected.id, available_player_ids)     # Disconnected

    def test_set_player_subjects_endpoint(self):
        """Test the endpoint for setting player specialist subjects"""
        from django.test import Client
        from django.urls import reverse
        from players.models import Player
        import json

        # Create players without specialist subjects
        player1 = Player.objects.create(
            name="Player 1",
            game_session=self.game_session,
            is_connected=True,
            specialist_subject=None
        )
        player2 = Player.objects.create(
            name="Player 2",
            game_session=self.game_session,
            is_connected=True,
            specialist_subject=""
        )

        client = Client()
        url = reverse('game_sessions:set_player_subjects', args=[self.game_session.game_code])

        # Test setting subjects
        data = {
            'subjects': {
                str(player1.id): 'History',
                str(player2.id): 'Science'
            }
        }

        response = client.post(
            url,
            data=json.dumps(data),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        self.assertTrue(response_data['success'])
        self.assertIn('Player 1', response_data['message'])
        self.assertIn('Player 2', response_data['message'])

        # Verify players were updated
        player1.refresh_from_db()
        player2.refresh_from_db()
        self.assertEqual(player1.specialist_subject, 'History')
        self.assertEqual(player2.specialist_subject, 'Science')

    def test_gm_page_refresh_with_completed_round(self):
        """Test that GM page shows answers after refresh when round is completed"""
        from django.test import Client
        from django.urls import reverse

        # Set up completed FFV round (round ended but next round not started)
        self.game_session.status = 'active'
        self.game_session.current_round_number = 3  # Round 3 completed
        self.game_session.is_round_active = False   # Round not active (completed)
        self.game_session.save()

        # Create some answers for the completed round
        player1 = Player.objects.create(
            name="Player 1",
            game_session=self.game_session,
            is_connected=True
        )
        player2 = Player.objects.create(
            name="Player 2",
            game_session=self.game_session,
            is_connected=True
        )

        PlayerAnswer.objects.create(
            player=player1,
            round_number=3,
            answer_text="Pear",
            is_valid=True,
            points_awarded=10
        )
        PlayerAnswer.objects.create(
            player=player2,
            round_number=3,
            answer_text="Potato",
            is_valid=False,
            points_awarded=0
        )

        client = Client()
        url = reverse('game_sessions:game_master', args=[self.game_session.game_code])

        # Test that GM page loads successfully and contains the right elements
        response = client.get(url)
        self.assertEqual(response.status_code, 200)

        # Check that the page contains the completed round information
        content = response.content.decode()
        self.assertIn('Round 3', content)  # Should show current round number

        # Check that JavaScript variables are set correctly for page refresh detection
        self.assertIn('templateRoundNumber = 3', content)
        self.assertIn('isRoundActive = false', content)
        self.assertIn('gameStatus = \'active\'', content)

        # The page should contain the logic to auto-fetch answers on load
        self.assertIn('DETECTED: Completed round on page load', content)


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