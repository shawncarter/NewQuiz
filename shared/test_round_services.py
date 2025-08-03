"""
Tests for Round Services

Comprehensive test suite for the round management services including
round generation, caching, and state management functionality.
"""

import time
from unittest.mock import Mock, patch, MagicMock
from django.test import TestCase
from django.utils import timezone
from django.core.cache import cache

from .services import (
    RoundService,
    RoundGeneratorService, 
    DeterministicSeedingUtility,
    RoundCacheService,
    get_round_service,
    get_round_generator
)


class MockGameSession:
    """Mock game session for testing"""
    def __init__(self):
        self.id = 1
        self.game_code = "ABC123"
        self.current_round_number = 0
        self.is_round_active = False
        self.current_round_started_at = None
        self.status = 'waiting'
        self.created_at = timezone.now()
        self.used_questions = Mock()
        self.used_questions.add = Mock()
        self.used_questions.clear = Mock()
        self.save = Mock()
        
        # Mock configuration
        self.configuration = Mock()
        self.configuration.num_rounds = 10
        self.configuration.round_time_seconds = 30
        self.configuration.round_type_sequence = ['flower_fruit_veg', 'multiple_choice']
        self.configuration.categories = Mock()
        self.configuration.categories.all.return_value = [
            Mock(name="Flowers", id=1),
            Mock(name="Fruits", id=2)
        ]
        self.configuration.categories.exists.return_value = True
        self.configuration.categories.values_list.return_value = ["Flowers", "Fruits"]


class RoundServiceTest(TestCase):
    """Test the RoundService class"""
    
    def setUp(self):
        self.game_session = MockGameSession()
        self.service = RoundService(self.game_session)
    
    def test_initialization(self):
        """Test service initialization"""
        self.assertEqual(self.service.game_session, self.game_session)
        self.assertEqual(self.service.config, self.game_session.configuration)
    
    def test_lazy_generator_initialization(self):
        """Test that generator is created lazily"""
        # Generator should not exist initially
        self.assertIsNone(self.service._generator)
        
        # Accessing generator should create it
        generator = self.service.generator
        self.assertIsInstance(generator, RoundGeneratorService)
        
        # Second access should return the same instance
        self.assertIs(self.service.generator, generator)
    
    def test_get_current_round_info_no_round(self):
        """Test get_current_round_info when no round is active"""
        self.game_session.current_round_number = 0
        result = self.service.get_current_round_info()
        self.assertIsNone(result)
    
    @patch('shared.services.round_service.get_round_handler')
    def test_get_current_round_info_with_round(self, mock_get_handler):
        """Test get_current_round_info with active round"""
        self.game_session.current_round_number = 1
        
        # Mock the round handler
        mock_handler = Mock()
        mock_round_info = {'round_number': 1, 'round_type': 'flower_fruit_veg'}
        mock_handler.get_round_info.return_value = mock_round_info
        mock_get_handler.return_value = mock_handler
        
        result = self.service.get_current_round_info()
        
        self.assertEqual(result, mock_round_info)
        mock_get_handler.assert_called_once_with(self.game_session, 1)
        mock_handler.get_round_info.assert_called_once()
    
    def test_get_next_round_info_game_complete(self):
        """Test get_next_round_info when game is complete"""
        self.game_session.current_round_number = 10  # Equals num_rounds
        result = self.service.get_next_round_info()
        self.assertIsNone(result)
    
    @patch.object(RoundGeneratorService, 'generate_round_data')
    def test_get_next_round_info_success(self, mock_generate):
        """Test successful get_next_round_info"""
        self.game_session.current_round_number = 1
        mock_round_data = {'round_number': 2, 'round_type': 'multiple_choice'}
        mock_generate.return_value = mock_round_data
        
        result = self.service.get_next_round_info()
        
        self.assertEqual(result, mock_round_data)
        mock_generate.assert_called_once_with(2)
    
    def test_is_game_complete_false(self):
        """Test is_game_complete returns False when game not complete"""
        self.game_session.current_round_number = 5
        result = self.service.is_game_complete()
        self.assertFalse(result)
    
    def test_is_game_complete_true(self):
        """Test is_game_complete returns True when game complete"""
        self.game_session.current_round_number = 10
        result = self.service.is_game_complete()
        self.assertTrue(result)
    
    def test_get_round_progress(self):
        """Test get_round_progress returns correct information"""
        self.game_session.current_round_number = 3
        self.game_session.is_round_active = True
        
        result = self.service.get_round_progress()
        
        expected = {
            'current_round': 3,
            'total_rounds': 10,
            'is_complete': False,
            'is_round_active': True,
            'rounds_remaining': 7
        }
        self.assertEqual(result, expected)
    
    def test_end_current_round_no_active_round(self):
        """Test ending round when no round is active"""
        self.game_session.is_round_active = False
        result = self.service.end_current_round()
        
        self.assertFalse(result['success'])
        self.assertIn('No active round', result['error'])
    
    @patch.object(RoundGeneratorService, 'clear_round_cache')
    def test_end_current_round_success(self, mock_clear_cache):
        """Test successful round ending"""
        self.game_session.is_round_active = True
        self.game_session.current_round_number = 2
        
        result = self.service.end_current_round()
        
        self.assertTrue(result['success'])
        self.assertFalse(self.game_session.is_round_active)
        self.game_session.save.assert_called_once()
        mock_clear_cache.assert_called_once_with(2)
    
    @patch.object(RoundGeneratorService, 'clear_all_round_cache')
    def test_restart_rounds(self, mock_clear_all):
        """Test restarting rounds"""
        self.game_session.current_round_number = 5
        self.game_session.is_round_active = True
        
        result = self.service.restart_rounds()
        
        self.assertTrue(result['success'])
        self.assertEqual(self.game_session.current_round_number, 0)
        self.assertFalse(self.game_session.is_round_active)
        self.assertIsNone(self.game_session.current_round_started_at)
        self.game_session.used_questions.clear.assert_called_once()
        mock_clear_all.assert_called_once()


class RoundGeneratorServiceTest(TestCase):
    """Test the RoundGeneratorService class"""
    
    def setUp(self):
        self.game_session = MockGameSession()
        self.service = RoundGeneratorService(self.game_session)
        cache.clear()  # Clear cache between tests
    
    def test_initialization(self):
        """Test service initialization"""
        self.assertEqual(self.service.game_session, self.game_session)
        self.assertEqual(self.service.config, self.game_session.configuration)
        self.assertIsInstance(self.service._seeding_utility, DeterministicSeedingUtility)
        self.assertIsInstance(self.service._cache_service, RoundCacheService)
    
    def test_get_round_type_with_sequence(self):
        """Test getting round type from configured sequence"""
        self.game_session.configuration.round_type_sequence = ['flower_fruit_veg', 'multiple_choice', 'mastermind']
        
        self.assertEqual(self.service._get_round_type(1), 'flower_fruit_veg')
        self.assertEqual(self.service._get_round_type(2), 'multiple_choice')
        self.assertEqual(self.service._get_round_type(3), 'mastermind')
    
    def test_get_round_type_without_sequence(self):
        """Test getting round type when no sequence configured"""
        self.game_session.configuration.round_type_sequence = []
        result = self.service._get_round_type(1)
        self.assertEqual(result, 'flower_fruit_veg')
    
    def test_get_round_type_beyond_sequence(self):
        """Test getting round type beyond configured sequence"""
        self.game_session.configuration.round_type_sequence = ['flower_fruit_veg']
        result = self.service._get_round_type(2)
        self.assertEqual(result, 'flower_fruit_veg')
    
    def test_generate_round_data_beyond_max_rounds(self):
        """Test generating data beyond maximum rounds"""
        result = self.service.generate_round_data(15)  # Beyond 10 rounds
        self.assertIsNone(result)
    
    @patch.object(RoundCacheService, 'get_round_data')
    def test_generate_round_data_uses_cache(self, mock_get_cache):
        """Test that cached data is used when available"""
        cached_data = {'round_number': 1, 'round_type': 'flower_fruit_veg', 'cached': True}
        mock_get_cache.return_value = cached_data
        
        result = self.service.generate_round_data(1)
        
        self.assertEqual(result, cached_data)
        mock_get_cache.assert_called_once_with(1)
    
    @patch.object(RoundCacheService, 'get_round_data')
    @patch.object(RoundCacheService, 'set_round_data')
    def test_generate_flower_fruit_veg_data(self, mock_set_cache, mock_get_cache):
        """Test generating flower/fruit/vegetable round data"""
        mock_get_cache.return_value = None  # No cached data
        self.game_session.configuration.round_type_sequence = ['flower_fruit_veg']
        
        result = self.service.generate_round_data(1)
        
        self.assertIsNotNone(result)
        self.assertEqual(result['round_type'], 'flower_fruit_veg')
        self.assertEqual(result['round_number'], 1)
        self.assertIn('category', result)
        self.assertIn('prompt_letter', result)
        self.assertIn(result['prompt_letter'], 'ABCDEFGHIJKLMNOPQRSTUVWXYZ')
        mock_set_cache.assert_called_once()
    
    def test_generate_flower_fruit_veg_no_categories(self):
        """Test flower/fruit/veg generation with no categories"""
        self.game_session.configuration.categories.all.return_value = []
        self.game_session.configuration.round_type_sequence = ['flower_fruit_veg']
        
        result = self.service.generate_round_data(1)
        self.assertIsNone(result)
    
    @patch('shared.services.round_generator_service.generate_unique_multiple_choice_question')
    def test_generate_multiple_choice_data(self, mock_generate_question):
        """Test generating multiple choice round data"""
        # Mock question
        mock_question = Mock()
        mock_question.question_text = "Test question?"
        mock_question.choices = ["A", "B", "C", "D"]
        mock_question.correct_answer = "B"
        mock_question.category = "Science"
        mock_question.is_ai_generated = True
        mock_question.id = 123
        
        mock_generate_question.return_value = mock_question
        self.game_session.configuration.round_type_sequence = ['multiple_choice']
        
        result = self.service.generate_round_data(1)
        
        self.assertIsNotNone(result)
        self.assertEqual(result['round_type'], 'multiple_choice')
        self.assertEqual(result['question_text'], "Test question?")
        self.assertEqual(result['choices'], ["A", "B", "C", "D"])
        self.assertEqual(result['correct_answer'], "B")
        self.assertEqual(result['category'], "Science")
        self.assertTrue(result['is_ai_generated'])
    
    def test_generate_mastermind_data(self):
        """Test generating mastermind round data"""
        self.game_session.configuration.round_type_sequence = ['mastermind']
        
        result = self.service.generate_round_data(1)
        
        self.assertIsNotNone(result)
        self.assertEqual(result['round_type'], 'mastermind')
        self.assertEqual(result['round_number'], 1)
    
    def test_generate_unknown_round_type(self):
        """Test generating data for unknown round type"""
        self.game_session.configuration.round_type_sequence = ['unknown_type']
        
        result = self.service.generate_round_data(1)
        self.assertIsNone(result)
    
    def test_select_letter_for_round_deterministic(self):
        """Test that letter selection is deterministic"""
        # First call
        letter1 = self.service._select_letter_for_round(1)
        
        # Second call should return same letter
        letter2 = self.service._select_letter_for_round(1)
        
        self.assertEqual(letter1, letter2)
        self.assertIn(letter1, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ')
    
    def test_get_used_letters_progression(self):
        """Test that used letters builds up correctly"""
        used_1 = self.service._get_used_letters(1)
        used_2 = self.service._get_used_letters(2)
        used_3 = self.service._get_used_letters(3)
        
        self.assertEqual(len(used_1), 0)  # No letters used before round 1
        self.assertEqual(len(used_2), 1)  # One letter used before round 2
        self.assertEqual(len(used_3), 2)  # Two letters used before round 3
    
    def test_clear_round_cache(self):
        """Test clearing cache for specific round"""
        self.service.clear_round_cache(1)
        # This should not raise an exception
    
    def test_clear_all_round_cache(self):
        """Test clearing all round cache"""
        self.service.clear_all_round_cache()
        # This should not raise an exception


class DeterministicSeedingUtilityTest(TestCase):
    """Test the DeterministicSeedingUtility class"""
    
    def setUp(self):
        self.game_session = MockGameSession()
        self.utility = DeterministicSeedingUtility(self.game_session)
    
    def test_deterministic_choice_consistency(self):
        """Test that deterministic choice is consistent"""
        choices = ['A', 'B', 'C', 'D', 'E']
        
        # Multiple calls should return same result
        choice1 = self.utility.get_deterministic_choice(choices, 1)
        choice2 = self.utility.get_deterministic_choice(choices, 1)
        
        self.assertEqual(choice1, choice2)
        self.assertIn(choice1, choices)
    
    def test_deterministic_choice_different_rounds(self):
        """Test that different rounds can produce different choices"""
        choices = ['A', 'B', 'C', 'D', 'E']
        
        choice_round_1 = self.utility.get_deterministic_choice(choices, 1)
        choice_round_2 = self.utility.get_deterministic_choice(choices, 2)
        
        # They might be the same, but at least check they're valid
        self.assertIn(choice_round_1, choices)
        self.assertIn(choice_round_2, choices)
    
    def test_deterministic_sample_consistency(self):
        """Test that deterministic sample is consistent"""
        population = ['A', 'B', 'C', 'D', 'E', 'F', 'G']
        
        sample1 = self.utility.get_deterministic_sample(population, 3, 1)
        sample2 = self.utility.get_deterministic_sample(population, 3, 1)
        
        self.assertEqual(sample1, sample2)
        self.assertEqual(len(sample1), 3)
        for item in sample1:
            self.assertIn(item, population)


class RoundCacheServiceTest(TestCase):
    """Test the RoundCacheService class"""
    
    def setUp(self):
        self.service = RoundCacheService("TEST123")
        cache.clear()
    
    def test_round_data_caching(self):
        """Test caching and retrieving round data"""
        round_data = {'round_number': 1, 'round_type': 'flower_fruit_veg'}
        
        # Initially no cached data
        self.assertIsNone(self.service.get_round_data(1))
        
        # Cache the data
        success = self.service.set_round_data(1, round_data)
        self.assertTrue(success)
        
        # Retrieve cached data
        cached_data = self.service.get_round_data(1)
        self.assertEqual(cached_data, round_data)
    
    def test_question_id_caching(self):
        """Test caching and retrieving question IDs"""
        question_id = 42
        
        # Initially no cached ID
        self.assertIsNone(self.service.get_question_id(1))
        
        # Cache the ID
        success = self.service.set_question_id(1, question_id)
        self.assertTrue(success)
        
        # Retrieve cached ID
        cached_id = self.service.get_question_id(1)
        self.assertEqual(cached_id, question_id)
    
    def test_round_state_caching(self):
        """Test caching and retrieving round state"""
        state_data = {'is_active': True, 'players_answered': ['player1']}
        
        # Cache the state
        success = self.service.set_round_state(1, state_data)
        self.assertTrue(success)
        
        # Retrieve cached state
        cached_state = self.service.get_round_state(1)
        self.assertEqual(cached_state, state_data)
    
    def test_used_letters_caching(self):
        """Test caching and retrieving used letters"""
        used_letters = ['A', 'B', 'C']
        
        # Initially empty list
        self.assertEqual(self.service.get_used_letters(), [])
        
        # Cache the letters
        success = self.service.set_used_letters(used_letters)
        self.assertTrue(success)
        
        # Retrieve cached letters
        cached_letters = self.service.get_used_letters()
        self.assertEqual(cached_letters, used_letters)
    
    def test_clear_round_cache(self):
        """Test clearing cache for specific round"""
        # Cache some data
        self.service.set_round_data(1, {'test': 'data'})
        self.service.set_question_id(1, 42)
        self.service.set_round_state(1, {'test': 'state'})
        
        # Clear the cache
        success = self.service.clear_round_cache(1)
        self.assertTrue(success)
        
        # Verify data is cleared
        self.assertIsNone(self.service.get_round_data(1))
        self.assertIsNone(self.service.get_question_id(1))
        self.assertIsNone(self.service.get_round_state(1))
    
    def test_clear_all_round_cache(self):
        """Test clearing all round cache"""
        # Cache data for multiple rounds
        for round_num in range(1, 4):
            self.service.set_round_data(round_num, {'round': round_num})
            self.service.set_question_id(round_num, round_num * 10)
        
        self.service.set_used_letters(['A', 'B'])
        
        # Clear all cache
        success = self.service.clear_all_round_cache(5)
        self.assertTrue(success)
        
        # Verify all data is cleared
        for round_num in range(1, 4):
            self.assertIsNone(self.service.get_round_data(round_num))
            self.assertIsNone(self.service.get_question_id(round_num))
        
        self.assertEqual(self.service.get_used_letters(), [])
    
    def test_get_cache_stats(self):
        """Test getting cache statistics"""
        # Cache some data
        self.service.set_round_data(1, {'test': 'data'})
        self.service.set_question_id(2, 42)
        self.service.set_round_state(3, {'test': 'state'})
        self.service.set_used_letters(['A'])
        
        stats = self.service.get_cache_stats(5)
        
        self.assertEqual(stats['game_code'], 'TEST123')
        self.assertIn(1, stats['cached_rounds'])
        self.assertIn(2, stats['cached_questions'])
        self.assertIn(3, stats['cached_states'])
        self.assertTrue(stats['has_used_letters'])


class RoundServiceFactoryTest(TestCase):
    """Test the factory functions"""
    
    def setUp(self):
        self.game_session = MockGameSession()
    
    def test_get_round_service(self):
        """Test factory function for round service"""
        service = get_round_service(self.game_session)
        self.assertIsInstance(service, RoundService)
        self.assertEqual(service.game_session, self.game_session)
    
    def test_get_round_generator(self):
        """Test factory function for round generator"""
        generator = get_round_generator(self.game_session)
        self.assertIsInstance(generator, RoundGeneratorService)
        self.assertEqual(generator.game_session, self.game_session)