"""
Round Handler System for Different Game Types

This module provides a clean separation of concerns for different round types,
allowing each game type to have its own logic for scoring, validation, and player feedback.
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from collections import Counter

logger = logging.getLogger(__name__)


class BaseRoundHandler(ABC):
    """Base class for all round handlers"""
    
    # Round type identifiers
    ROUND_TYPE = None  # Must be overridden
    DISPLAY_NAME = None  # Must be overridden
    
    def __init__(self, game_session, round_number: int):
        self.game_session = game_session
        self.round_number = round_number
        self.config = game_session.configuration
    
    @abstractmethod
    def generate_round_data(self) -> Dict[str, Any]:
        """Generate the round data (question, choices, etc.)"""
        pass
    
    @abstractmethod
    def create_player_answer(self, player, answer_text: str):
        """Create a PlayerAnswer object with appropriate initial values"""
        pass
    
    @abstractmethod
    def perform_automatic_scoring(self, answers):
        """Perform automatic scoring for this round type"""
        pass
    
    @abstractmethod
    def should_send_immediate_feedback(self) -> bool:
        """Whether to send immediate feedback to players when round ends"""
        pass
    
    @abstractmethod
    def supports_manual_validation(self) -> bool:
        """Whether this round type supports manual validation by GM"""
        pass
    
    @abstractmethod
    def get_player_feedback_message(self, player_answer, is_correct: bool, points: int) -> str:
        """Generate personalized feedback message for a player"""
        pass
    
    def get_round_info(self) -> Dict[str, Any]:
        """Get complete round information including type and data"""
        round_data = self.generate_round_data()
        round_data.update({
            'round_type': self.ROUND_TYPE,
            'round_number': self.round_number,
            'is_active': self.game_session.is_round_active,
            'time_remaining': self._calculate_time_remaining(),
            'started_at': self.game_session.current_round_started_at,
        })
        return round_data
    
    def _calculate_time_remaining(self) -> int:
        """Calculate time remaining for active rounds"""
        if not self.game_session.is_round_active or not self.game_session.current_round_started_at:
            return 0
        
        from django.utils import timezone
        elapsed = (timezone.now() - self.game_session.current_round_started_at).total_seconds()
        return max(0, self.config.round_time_seconds - int(elapsed))


class FlowerFruitVegRoundHandler(BaseRoundHandler):
    """Handler for 'Flower, Fruit & Veg' rounds (starts with letter)"""
    
    ROUND_TYPE = 'flower_fruit_veg'
    DISPLAY_NAME = 'Flower, Fruit & Veg'
    
    def generate_round_data(self) -> Dict[str, Any]:
        """Generate category and letter for this round"""
        # Use selected categories from game configuration, with fallback to dynamic list
        try:
            config = self.game_session.configuration
            selected_categories = list(config.categories.values_list('name', flat=True))
            
            if selected_categories:
                available_categories = selected_categories
            else:
                # Fallback to dynamic categories if none selected
                available_categories = [
                    'Animals', 'Countries', 'Cities', 'Foods', 'Movies', 'Books', 'TV Shows',
                    'Sports', 'Cars', 'Colors', 'Fruits', 'Vegetables', 'Flowers', 'Clothing',
                    'Musical Instruments', 'Board Games', 'Video Games', 'Celebrities', 
                    'Fictional Characters', 'Superheroes', 'School Subjects', 'Job Titles',
                    'Things in a Kitchen', 'Things in a Bedroom', 'Things at the Beach',
                    'Things that Fly', 'Things that are Round', 'Things that are Red',
                    'Boys Names', 'Girls Names', 'Last Names', 'Brand Names', 'Restaurants',
                    'Hobbies', 'Toys', 'Cartoon Characters', 'Disney Movies', 'Pizza Toppings',
                    'Ice Cream Flavors', 'Things in Space', 'Ocean Creatures', 'Farm Animals',
                    'Wild Animals', 'Types of Birds', 'Types of Fish', 'Insects', 'Trees',
                    'Things Made of Metal', 'Things Made of Wood', 'Electronics', 'Tools',
                    'Things in a Hospital', 'Things in a School', 'Types of Weather'
                ]
        except:
            # Fallback if no configuration exists
            available_categories = ['Animals', 'Countries', 'Movies', 'Foods', 'Sports']

        letters = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M',
                  'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z']

        # Use varied seeding to prevent predictable patterns across games
        import random
        import hashlib
        import time
        
        # Create truly random seed that varies between games but stays consistent within rounds
        creation_hash = hashlib.md5(str(self.game_session.created_at.timestamp()).encode()).hexdigest()[:8]
        seed_string = f"{self.game_session.game_code}_{self.round_number}_{creation_hash}_{int(time.time()) % 10000}"
        seed_hash = hashlib.md5(seed_string.encode()).hexdigest()
        
        # Use full hash as integer seed for better distribution
        random.seed(int(seed_hash[:16], 16))

        # Random category selection from available categories
        category_name = random.choice(available_categories)
        
        # Create a simple category object for compatibility
        class DynamicCategory:
            def __init__(self, name):
                self.name = name
                self.id = hash(name) % 1000  # Simple ID for consistency
            
            def __str__(self):
                return self.name
        
        category = DynamicCategory(category_name)

        # Random letter but avoid repeats by tracking used letters
        used_letters = self._get_used_letters()
        available_letters = [l for l in letters if l not in used_letters]

        # If all letters used, reset and use all letters again
        if not available_letters:
            available_letters = letters

        letter = random.choice(available_letters)

        return {
            'category': category,
            'prompt_letter': letter,
            'prompt': f"{category.name} that start with {letter}",
        }
    
    def create_player_answer(self, player, answer_text: str):
        """Create PlayerAnswer for Flower, Fruit & Veg rounds - starts invalid"""
        from players.models import PlayerAnswer
        
        return PlayerAnswer.objects.create(
            player=player,
            round_number=self.round_number,
            answer_text=answer_text.strip(),
            is_valid=False,  # Starts invalid, requires manual validation
            points_awarded=0
        )
    
    def perform_automatic_scoring(self, answers):
        """For Flower, Fruit & Veg rounds, we don't auto-score - requires manual validation"""
        # Count answer frequencies for duplicate detection when manually validated
        answer_counts = Counter()
        for answer in answers:
            normalized_answer = answer.answer_text.lower().strip()
            answer_counts[normalized_answer] += 1

        # Update is_unique field for all answers (used during manual validation)
        for answer in answers:
            normalized_answer = answer.answer_text.lower().strip()
            answer.is_unique = answer_counts[normalized_answer] == 1
            answer.save()
        
        logger.info(f"Prepared {len(answers)} Flower, Fruit & Veg answers for manual validation")
    
    def should_send_immediate_feedback(self) -> bool:
        """Flower, Fruit & Veg rounds require manual validation"""
        return False
    
    def supports_manual_validation(self) -> bool:
        """Flower, Fruit & Veg rounds support manual validation"""
        return True
    
    def get_player_feedback_message(self, player_answer, is_correct: bool, points: int) -> str:
        """Generate feedback message for manual validation"""
        if is_correct:
            if getattr(player_answer, 'is_unique', False):
                message = f"🌟 Unique answer! You earned {points} points."
            else:
                message = f"✅ Valid answer! You earned {points} points."
        else:
            message = f"❌ Invalid answer. No points awarded."
        
        message += f"\\n\\nYour answer: {player_answer.answer_text}"
        return message
    
    def validate_answer_manually(self, player_answer, is_valid: bool) -> int:
        """Manually validate an answer and return points awarded"""
        # Recalculate points based on validation and uniqueness
        if is_valid:
            if getattr(player_answer, 'is_unique', False):
                points = self.config.unique_answer_points
                reason = "unique_correct_answer"
            else:
                points = self.config.valid_answer_points
                reason = "duplicate_correct_answer"
        else:
            points = self.config.invalid_answer_points
            reason = "invalid_answer"

        # Update answer record
        player_answer.is_valid = is_valid
        old_points = player_answer.points_awarded
        player_answer.points_awarded = points
        player_answer.save()

        # Award points using scoring system
        points_difference = points - old_points
        if points_difference != 0:
            if points_difference > 0:
                player_answer.player.award_points(
                    points_difference,
                    reason=reason,
                    round_number=self.round_number,
                    related_answer=player_answer
                )
            else:
                player_answer.player.deduct_points(
                    abs(points_difference),
                    reason=f"correction_{reason}",
                    round_number=self.round_number
                )
        
        return points
    
    def _get_used_letters(self):
        """Get letters that have been used in previous rounds"""
        used_letters = []

        import random
        import hashlib
        import time
        
        for round_num in range(1, self.round_number):
            # Use the same improved seeding approach as the main round generation
            creation_hash = hashlib.md5(str(self.game_session.created_at.timestamp()).encode()).hexdigest()[:8]
            seed_string = f"{self.game_session.game_code}_{round_num}_{creation_hash}_{int(time.time()) % 10000}"
            seed_hash = hashlib.md5(seed_string.encode()).hexdigest()
            random.seed(int(seed_hash[:16], 16))
            
            letters = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M',
                      'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z']
            available = [l for l in letters if l not in used_letters]
            if available:
                used_letters.append(random.choice(available))

        return used_letters


class MultipleChoiceRoundHandler(BaseRoundHandler):
    """Handler for Multiple Choice quiz rounds"""
    
    ROUND_TYPE = 'multiple_choice'
    DISPLAY_NAME = 'Multiple Choice'
    
    def generate_round_data(self) -> Dict[str, Any]:
        """Generate or retrieve multiple choice question with consistent caching"""
        # Check cache first for consistency
        from django.core.cache import cache
        import time
        
        cache_key = f'game_{self.game_session.game_code}_round_{self.round_number}_question_id'
        lock_key = f'game_{self.game_session.game_code}_round_{self.round_number}_lock'
        
        # Simple locking mechanism to prevent race conditions
        for attempt in range(10):  # Max 10 attempts
            if cache.add(lock_key, 'locked', timeout=30):  # Acquire lock for 30 seconds
                break
            time.sleep(0.1)  # Wait 100ms before retry
        else:
            logger.warning(f"Could not acquire lock for round {self.round_number} in game {self.game_session.game_code}")
        
        try:
            cached_question_id = cache.get(cache_key)
            
            question = None
            if cached_question_id:
                try:
                    from game_sessions.models import MultipleChoiceQuestion
                    question = MultipleChoiceQuestion.objects.get(id=cached_question_id)
                    logger.info(f"Using CACHED question for game {self.game_session.game_code}, round {self.round_number}: {question.question_text}")
                except MultipleChoiceQuestion.DoesNotExist:
                    logger.warning(f"Cached question ID {cached_question_id} not found")
            
            if not question:
                # Use a single, deterministic approach for question selection
                # First try to generate a new question
                question = self._generate_new_question()
                if question:
                    # Add to used questions and cache
                    self.game_session.used_questions.add(question)
                    cache.set(cache_key, question.id, timeout=3600)
                    logger.info(f"Generated and cached NEW question for game {self.game_session.game_code}, round {self.round_number}: {question.question_text}")
                else:
                    # If generation fails, use deterministic fallback
                    fallback_data = self._get_fallback_question_data()
                    # Try to find existing fallback question
                    try:
                        from game_sessions.models import MultipleChoiceQuestion
                        question = MultipleChoiceQuestion.objects.filter(
                            question_text=fallback_data['question_text']
                        ).first()
                        
                        if not question:
                            # Create the fallback question
                            question = MultipleChoiceQuestion.objects.create(
                                question_text=fallback_data['question_text'],
                                choices=fallback_data['choices'],
                                correct_answer=fallback_data['correct_answer'],
                                category=fallback_data['category']
                            )
                            logger.info(f"Created FALLBACK question for game {self.game_session.game_code}, round {self.round_number}: {question.question_text}")
                        else:
                            logger.info(f"Reusing existing FALLBACK question for game {self.game_session.game_code}, round {self.round_number}: {question.question_text}")
                        
                        # Add to used questions and cache
                        self.game_session.used_questions.add(question)
                        cache.set(cache_key, question.id, timeout=3600)
                        
                    except Exception as e:
                        logger.error(f"Failed to create/retrieve fallback question: {e}")
                        # Return the fallback data directly as last resort
                        return fallback_data
            
            if question:
                result = {
                    'question_text': question.question_text,
                    'choices': question.choices,
                    'correct_answer': question.correct_answer,
                    'category': question.category,
                }
            else:
                # This should never happen, but provide ultimate fallback
                result = {
                    'question_text': 'What is 2 + 2?',
                    'choices': ['3', '4', '5', '6'],
                    'correct_answer': '4',
                    'category': 'Math',
                }
            
            return result
            
        finally:
            # Always release the lock
            cache.delete(lock_key)
    
    def create_player_answer(self, player, answer_text: str):
        """Create PlayerAnswer for Multiple Choice rounds - starts valid for auto-scoring"""
        from players.models import PlayerAnswer
        
        return PlayerAnswer.objects.create(
            player=player,
            round_number=self.round_number,
            answer_text=answer_text.strip(),
            is_valid=True,  # Will be scored automatically
            points_awarded=0
        )
    
    def perform_automatic_scoring(self, answers):
        """Perform automatic scoring for multiple choice questions"""
        round_data = self.generate_round_data()
        correct_answer_text = round_data.get('correct_answer', '').lower().strip()
        
        if not correct_answer_text:
            logger.error(f"Multiple choice round {self.round_number} for game {self.game_session.game_code} has no correct answer defined.")
            return

        for answer in answers:
            player_answer_text = answer.answer_text.lower().strip()
            is_correct = (player_answer_text == correct_answer_text)

            points = 0
            reason = ""
            player = answer.player

            if is_correct:
                points = 10  # Base points for correct answer
                player.correct_answer_streak += 1
                reason = "correct_answer"

                # Calculate streak bonus
                if player.correct_answer_streak > 1:
                    streak_bonus = (player.correct_answer_streak - 1) * 5
                    points += streak_bonus
                    reason += f"_streak_{player.correct_answer_streak}"
            else:
                player.correct_answer_streak = 0  # Reset streak on incorrect answer
                points = 0
                reason = "incorrect_answer"

            player.save()  # Save player to update streak

            # Update answer record
            old_points = answer.points_awarded
            answer.is_valid = is_correct
            answer.points_awarded = points
            answer.save()

            # Award points using scoring system
            points_difference = points - old_points
            if points_difference != 0:
                if points_difference > 0:
                    player.award_points(
                        points_difference,
                        reason=reason,
                        round_number=self.round_number,
                        related_answer=answer
                    )
                else:
                    player.deduct_points(
                        abs(points_difference),
                        reason=f"correction_{reason}",
                        round_number=self.round_number
                    )
    
    def should_send_immediate_feedback(self) -> bool:
        """Multiple Choice rounds provide immediate feedback"""
        return True
    
    def supports_manual_validation(self) -> bool:
        """Multiple Choice rounds don't support manual validation"""
        return False
    
    def get_player_feedback_message(self, player_answer, is_correct: bool, points: int) -> str:
        """Generate feedback message for automatic scoring"""
        round_data = self.generate_round_data()
        correct_answer = round_data.get('correct_answer')
        
        if is_correct:
            message = f"🎉 Correct! You earned {points} points."
            if player_answer.player.correct_answer_streak > 1:
                message += f" ({player_answer.player.correct_answer_streak} answer streak!)"
            message += f"\\n\\nThe correct answer was: {correct_answer}"
            message += f"\\nYour answer: {player_answer.answer_text}"
        else:
            message = f"❌ Incorrect. The correct answer was: {correct_answer}"
            message += f"\\n\\nYour answer: {player_answer.answer_text}"
        
        return message
    
    def _generate_new_question(self):
        """Generate a new multiple choice question"""
        category_name = "General Knowledge"
        if self.config.categories.exists():
            import random
            random.seed(f"{self.game_session.game_code}_{self.round_number}")
            category_name = random.choice(list(self.config.categories.values_list('name', flat=True)))

        try:
            from game_sessions.question_generator import generate_unique_multiple_choice_question
            question = generate_unique_multiple_choice_question(category=category_name)
            if question:
                logger.info(f"Generated new question for game {self.game_session.game_code}, round {self.round_number}: {question.question_text}")
                return question
        except ImportError:
            logger.warning("Question generator not available, using fallback")
        
        return None
    
    def _get_fallback_question_data(self):
        """Get deterministic fallback question data (without creating DB objects)"""
        import random
        
        # Use a deterministic seed for this round
        random.seed(f"{self.game_session.game_code}_{self.round_number}_hardcoded")
        
        # Hardcoded questions as fallback
        QUESTIONS = [
            {
                'question_text': 'What is the largest mammal in the world?',
                'choices': ['Blue Whale', 'African Elephant', 'Giraffe', 'Hippopotamus'],
                'correct_answer': 'Blue Whale',
                'category': 'Animals'
            },
            {
                'question_text': 'What is the smallest country in the world?',
                'choices': ['Monaco', 'Vatican City', 'San Marino', 'Liechtenstein'],
                'correct_answer': 'Vatican City',
                'category': 'Geography'
            },
            {
                'question_text': 'What is the largest bone in the human body?',
                'choices': ['Femur', 'Tibia', 'Humerus', 'Fibula'],
                'correct_answer': 'Femur',
                'category': 'Science'
            }
        ]
        
        hardcoded_question = random.choice(QUESTIONS)
        return hardcoded_question


# Round handler registry
ROUND_HANDLERS = {
    'flower_fruit_veg': FlowerFruitVegRoundHandler,
    'multiple_choice': MultipleChoiceRoundHandler,
}

# Legacy mapping for backward compatibility
LEGACY_ROUND_TYPE_MAPPING = {
    'starts_with': 'flower_fruit_veg',
    'multiple_choice': 'multiple_choice',
}


def get_round_handler(game_session, round_number: int, round_type: str = None) -> BaseRoundHandler:
    """Get the appropriate round handler for a game session and round"""
    if round_type is None:
        # Determine round type from game configuration
        try:
            config = game_session.configuration
            if config.round_type_sequence and len(config.round_type_sequence) >= round_number:
                round_type = config.round_type_sequence[round_number - 1]
            else:
                round_type = 'flower_fruit_veg'  # Default
        except:
            round_type = 'flower_fruit_veg'  # Fallback
    
    # Handle legacy round types
    round_type = LEGACY_ROUND_TYPE_MAPPING.get(round_type, round_type)
    
    # Get handler class
    handler_class = ROUND_HANDLERS.get(round_type)
    if not handler_class:
        logger.warning(f"Unknown round type '{round_type}', using FlowerFruitVegRoundHandler as fallback")
        handler_class = FlowerFruitVegRoundHandler
    
    return handler_class(game_session, round_number)