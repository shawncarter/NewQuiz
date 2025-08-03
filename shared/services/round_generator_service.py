"""
Round Generator Service

Service for generating round data based on round type and game configuration.
Extracts complex round generation logic from models and provides a clean,
testable interface for creating round content.
"""

import hashlib
import logging
import random
import time
from typing import Dict, Any, List, Optional
from django.core.cache import cache
from .round_cache_service import RoundCacheService

logger = logging.getLogger(__name__)


class RoundGeneratorService:
    """
    Service for generating round data based on configuration.
    
    Handles the creation of round-specific data including questions, categories,
    letters, and other round parameters while managing caching and consistency.
    """
    
    def __init__(self, game_session):
        self.game_session = game_session
        self.config = game_session.configuration
        self._seeding_utility = DeterministicSeedingUtility(game_session)
        self._cache_service = RoundCacheService(game_session.game_code)
    
    def generate_round_data(self, round_number: int) -> Optional[Dict[str, Any]]:
        """
        Generate data for a specific round based on configuration.
        
        Args:
            round_number: The round number to generate data for
            
        Returns:
            Dict containing round data or None if generation fails
        """
        if round_number > self.config.num_rounds:
            return None
        
        # Check cache first for consistency
        cached_data = self._cache_service.get_round_data(round_number)
        if cached_data:
            return cached_data
        
        # Determine round type
        round_type = self._get_round_type(round_number)
        
        # Generate data based on type
        if round_type == 'flower_fruit_veg':
            round_data = self._generate_flower_fruit_veg_data(round_number)
        elif round_type == 'multiple_choice':
            round_data = self._generate_multiple_choice_data(round_number)
        elif round_type == 'mastermind':
            round_data = self._generate_mastermind_data(round_number)
        else:
            logger.warning(f"Unknown round type '{round_type}' for round {round_number}")
            return None
        
        if round_data:
            # Cache the generated data
            self._cache_service.set_round_data(round_number, round_data)
        
        return round_data
    
    def clear_round_cache(self, round_number: int):
        """Clear cached data for a specific round"""
        self._cache_service.clear_round_cache(round_number)
    
    def clear_all_round_cache(self):
        """Clear all cached round data for this game"""
        self._cache_service.clear_all_round_cache(self.config.num_rounds)
    
    def _get_round_type(self, round_number: int) -> str:
        """Determine the round type for a given round number"""
        if (self.config.round_type_sequence and 
            len(self.config.round_type_sequence) >= round_number):
            return self.config.round_type_sequence[round_number - 1]
        
        # Default to flower_fruit_veg if no sequence configured
        return 'flower_fruit_veg'
    
    def _generate_flower_fruit_veg_data(self, round_number: int) -> Optional[Dict[str, Any]]:
        """Generate data for flower/fruit/vegetable rounds"""
        # Get available categories
        categories = list(self.config.categories.all())
        if not categories:
            logger.error(f"No categories available for flower_fruit_veg round {round_number}")
            return None
        
        # Use deterministic seeding for consistency
        self._seeding_utility.set_seed_for_round(round_number)
        
        # Select category (can repeat across rounds)
        category = random.choice(categories)
        
        # Select letter avoiding recent repeats
        letter = self._select_letter_for_round(round_number)
        
        return {
            'round_type': 'flower_fruit_veg',
            'round_number': round_number,
            'category': category,
            'prompt_letter': letter,
            'is_active': False,
            'time_remaining': 0,
            'started_at': None,
        }
    
    def _generate_multiple_choice_data(self, round_number: int) -> Optional[Dict[str, Any]]:
        """Generate data for multiple choice rounds"""
        # Check for cached question first
        question = self._get_or_generate_question(round_number)
        if not question:
            logger.error(f"Could not generate question for multiple choice round {round_number}")
            return None
        
        return {
            'round_type': 'multiple_choice',
            'round_number': round_number,
            'question_text': question.question_text,
            'choices': question.choices,
            'correct_answer': question.correct_answer,
            'category': question.category,
            'is_ai_generated': question.is_ai_generated,
            'is_active': False,
            'time_remaining': 0,
            'started_at': None,
        }
    
    def _generate_mastermind_data(self, round_number: int) -> Optional[Dict[str, Any]]:
        """Generate data for mastermind rounds"""
        # Mastermind rounds have specialized handling
        # This is a placeholder for mastermind-specific generation
        return {
            'round_type': 'mastermind',
            'round_number': round_number,
            'is_active': False,
            'time_remaining': 0,
            'started_at': None,
        }
    
    def _select_letter_for_round(self, round_number: int) -> str:
        """Select a letter for the round, avoiding recent repeats"""
        letters = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M',
                  'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z']
        
        # Get previously used letters
        used_letters = self._get_used_letters(round_number)
        available_letters = [l for l in letters if l not in used_letters]
        
        # If all letters used, reset and use all letters again
        if not available_letters:
            available_letters = letters
        
        return random.choice(available_letters)
    
    def _get_used_letters(self, target_round: int) -> List[str]:
        """Get letters used in previous rounds"""
        used_letters = []
        
        for round_num in range(1, target_round):
            self._seeding_utility.set_seed_for_round(round_num)
            
            letters = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M',
                      'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z']
            available = [l for l in letters if l not in used_letters]
            if available:
                used_letters.append(random.choice(available))
        
        return used_letters
    
    def _get_or_generate_question(self, round_number: int):
        """Get or generate a question for multiple choice rounds"""
        # Check cache first
        cached_question_id = self._cache_service.get_question_id(round_number)
        
        if cached_question_id:
            try:
                from game_sessions.models import MultipleChoiceQuestion
                question = MultipleChoiceQuestion.objects.get(id=cached_question_id)
                logger.info(f"Using cached question for round {round_number}: {question.question_text[:50]}")
                return question
            except MultipleChoiceQuestion.DoesNotExist:
                logger.warning(f"Cached question ID {cached_question_id} not found")
        
        # Generate new question
        question = self._generate_new_question(round_number)
        if question:
            # Add to used questions and cache
            self.game_session.used_questions.add(question)
            self._cache_service.set_question_id(round_number, question.id)
            logger.info(f"Generated new question for round {round_number}: {question.question_text[:50]}")
        
        return question
    
    def _generate_new_question(self, round_number: int):
        """Generate a new question for multiple choice rounds"""
        # Determine category
        category_name = "General Knowledge"
        if self.config.categories.exists():
            categories = list(self.config.categories.values_list('name', flat=True))
            self._seeding_utility.set_seed_for_round(round_number)
            category_name = random.choice(categories)
        
        # Use the question generator
        try:
            from game_sessions.question_generator import generate_unique_multiple_choice_question
            return generate_unique_multiple_choice_question(category=category_name)
        except ImportError:
            logger.error("Question generator not available")
            return None
    
# Cache methods moved to RoundCacheService


class DeterministicSeedingUtility:
    """
    Utility for consistent pseudo-random generation across game sessions.
    
    Ensures that the same game code and round number always generate
    the same "random" results for consistency across reconnections.
    """
    
    def __init__(self, game_session):
        self.game_session = game_session
    
    def set_seed_for_round(self, round_number: int):
        """Set deterministic seed for a specific round"""
        # Create deterministic seed using game code, round number, and creation time
        creation_hash = hashlib.md5(
            str(self.game_session.created_at.timestamp()).encode()
        ).hexdigest()[:8]
        
        seed_string = f"{self.game_session.game_code}_{round_number}_{creation_hash}_{int(time.time()) % 10000}"
        seed_hash = hashlib.md5(seed_string.encode()).hexdigest()
        
        # Use first 16 hex characters as integer seed
        random.seed(int(seed_hash[:16], 16))
    
    def get_deterministic_choice(self, choices: List[Any], round_number: int):
        """Make a deterministic choice for a given round"""
        self.set_seed_for_round(round_number)
        return random.choice(choices)
    
    def get_deterministic_sample(self, population: List[Any], k: int, round_number: int):
        """Get a deterministic sample for a given round"""
        self.set_seed_for_round(round_number)
        return random.sample(population, k)