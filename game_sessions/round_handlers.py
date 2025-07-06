"""
Round Handler System for Different Game Types

This module provides a clean separation of concerns for different round types,
allowing each game type to have its own logic for scoring, validation, and player feedback.
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, List
from collections import Counter

logger = logging.getLogger(__name__)


class DynamicCategory:
    """Simple category object for compatibility with template system"""
    def __init__(self, name):
        self.name = name
        self.id = hash(name) % 1000  # Simple ID for consistency
    
    def __str__(self):
        return self.name


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
        """Generate category and letter for this round with caching for browser refresh consistency"""
        # Check cache first for consistency - critical for browser refresh handling
        from django.core.cache import cache
        
        cache_key = f'game_{self.game_session.game_code}_round_{self.round_number}_ffv_data'
        cached_data = cache.get(cache_key)
        if cached_data:
            logger.info(f"Using CACHED FFV data for game {self.game_session.game_code}, round {self.round_number}: {cached_data['category'].name} - {cached_data['prompt_letter']}")
            return cached_data
        
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

        # Use consistent seeding that doesn't vary with time - critical for browser refresh handling
        import random
        import hashlib
        
        # Create consistent seed that varies between games but stays consistent within rounds
        creation_hash = hashlib.md5(str(self.game_session.created_at.timestamp()).encode()).hexdigest()[:8]
        seed_string = f"{self.game_session.game_code}_{self.round_number}_{creation_hash}"
        seed_hash = hashlib.md5(seed_string.encode()).hexdigest()
        
        # Use full hash as integer seed for better distribution
        random.seed(int(seed_hash[:16], 16))

        # Random category selection from available categories
        category_name = random.choice(available_categories)
        
        # Create a simple category object for compatibility
        category = DynamicCategory(category_name)

        # Random letter but avoid repeats by tracking used letters
        used_letters = self._get_used_letters()
        available_letters = [l for l in letters if l not in used_letters]

        # If all letters used, reset and use all letters again
        if not available_letters:
            available_letters = letters

        letter = random.choice(available_letters)

        result = {
            'category': category,
            'prompt_letter': letter,
            'prompt': f"{category.name} that start with {letter}",
        }
        
        # Cache the result for browser refresh consistency
        cache.set(cache_key, result, timeout=3600)
        logger.info(f"Cached FFV data for game {self.game_session.game_code}, round {self.round_number}: {category.name} - {letter}")
        
        return result
    
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
            # Use the same consistent seeding approach as the main round generation
            creation_hash = hashlib.md5(str(self.game_session.created_at.timestamp()).encode()).hexdigest()[:8]
            seed_string = f"{self.game_session.game_code}_{round_num}_{creation_hash}"
            seed_hash = hashlib.md5(seed_string.encode()).hexdigest()
            random.seed(int(seed_hash[:16], 16))
            
            letters = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M',
                      'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z']
            available = [l for l in letters if l not in used_letters]
            if available:
                used_letters.append(random.choice(available))

        return used_letters


class MastermindRoundHandler(BaseRoundHandler):
    """Handler for Mastermind rounds - 1-on-1 specialist subject rounds"""
    
    ROUND_TYPE = 'mastermind'
    DISPLAY_NAME = 'Mastermind'
    
    def __init__(self, game_session, round_number: int):
        super().__init__(game_session, round_number)
        self.questions_per_player = 25  # Number of questions for rapid-fire 90-second round
        
    def generate_round_data(self) -> Dict[str, Any]:
        """Generate Mastermind round data - much simpler approach"""
        from django.core.cache import cache
        
        # Get round state
        round_state = self._get_round_state()
        
        # Check what state we're in
        state = round_state.get('state', 'waiting_for_player_selection')
        
        if state == 'waiting_for_player_selection':
            # GM needs to select which player goes next
            return self._get_player_selection_data()
        elif state == 'asking_ready':
            # Asking current player if they're ready
            return self._get_ready_check_data(round_state)
        elif state == 'playing':
            # Active question round for current player
            return self._get_active_question_data(round_state)
        elif state == 'player_complete':
            # Current player finished, show results
            return self._get_player_complete_data(round_state)
        elif state == 'all_complete':
            # All players finished, move to general knowledge
            return self._generate_general_knowledge_data()
        else:
            # Default fallback
            return self._get_player_selection_data()
    
    def _get_round_state(self) -> Dict[str, Any]:
        """Get the current round state from cache"""
        from django.core.cache import cache
        state_key = f'game_{self.game_session.game_code}_round_{self.round_number}_mastermind_state'
        return cache.get(state_key, {
            'state': 'waiting_for_player_selection',
            'completed_players': [],
            'current_player_id': None,
            'current_question_index': 0,
            'used_question_ids': []
        })
    
    def _save_round_state(self, state: Dict[str, Any]):
        """Save the current round state to cache"""
        from django.core.cache import cache
        state_key = f'game_{self.game_session.game_code}_round_{self.round_number}_mastermind_state'
        cache.set(state_key, state, timeout=3600)
    
    def _get_player_selection_data(self) -> Dict[str, Any]:
        """GM selects which player goes next"""
        # Get players with specialist subjects who haven't gone yet
        round_state = self._get_round_state()
        completed_players = round_state.get('completed_players', [])
        
        available_players = self.game_session.players.filter(
            is_connected=True,
            specialist_subject__isnull=False
        ).exclude(
            specialist_subject='',
            id__in=completed_players
        ).order_by('joined_at')
        
        if not available_players.exists():
            # All players completed, move to general knowledge
            round_state['state'] = 'all_complete'
            self._save_round_state(round_state)
            return self._generate_general_knowledge_data()
        
        # Get all connected players for GM screen display
        all_players = self.game_session.players.filter(is_connected=True).order_by('joined_at')
        
        return {
            'state': 'waiting_for_player_selection',
            'available_players': [
                {
                    'id': p.id,
                    'name': p.name,
                    'specialist_subject': p.specialist_subject
                } for p in available_players
            ],
            'completed_players': completed_players,
            'all_players': [
                {
                    'id': p.id,
                    'name': p.name,
                    'specialist_subject': p.specialist_subject or '',
                    'current_score': p.current_score or 0
                } for p in all_players
            ],
            'message': 'Game Master: Select the next player for their specialist round'
        }
    
    def _get_ready_check_data(self, round_state: Dict[str, Any]) -> Dict[str, Any]:
        """Ask current player if they're ready"""
        from players.models import Player
        
        current_player_id = round_state.get('current_player_id')
        if not current_player_id:
            return self._get_player_selection_data()
        
        try:
            current_player = Player.objects.get(id=current_player_id)
        except Player.DoesNotExist:
            return self._get_player_selection_data()
        
        return {
            'state': 'asking_ready',
            'current_player': {
                'id': current_player.id,
                'name': current_player.name,
                'specialist_subject': current_player.specialist_subject
            },
            'message': f'{current_player.name}, are you ready for your specialist round on {current_player.specialist_subject}?'
        }
    
    def _get_active_question_data(self, round_state: Dict[str, Any]) -> Dict[str, Any]:
        """Get current question for active player - rapid-fire mode with pre-loaded questions"""
        from players.models import Player
        from django.core.cache import cache
        
        current_player_id = round_state.get('current_player_id')
        current_question_index = round_state.get('current_question_index', 0)
        
        if not current_player_id:
            return self._get_player_selection_data()
        
        try:
            current_player = Player.objects.get(id=current_player_id)
        except Player.DoesNotExist:
            return self._get_player_selection_data()
        
        # Get pre-loaded questions for this player
        cache_key = f'mastermind_questions_{self.game_session.game_code}_{current_player_id}'
        pre_loaded_questions = cache.get(cache_key)
        
        if not pre_loaded_questions:
            logger.warning(f"No pre-loaded questions found for player {current_player.name}")
            # Fallback: pre-load questions now
            pre_loaded_questions = self.preload_player_questions(current_player_id)
        
        # Check if we've reached the end of questions or 90 seconds
        if current_question_index >= len(pre_loaded_questions):
            # All questions answered, player is complete
            round_state['state'] = 'player_complete'
            self._save_round_state(round_state)
            return self._get_player_complete_data(round_state)
        
        # Get the current question from pre-loaded set
        current_question = pre_loaded_questions[current_question_index]
        
        # Get all connected players for GM screen display
        all_players = self.game_session.players.filter(is_connected=True).order_by('joined_at')
        
        return {
            'state': 'playing',
            'current_player': {
                'id': current_player.id,
                'name': current_player.name,
                'specialist_subject': current_player.specialist_subject
            },
            'question_text': current_question['question_text'],
            'choices': current_question['choices'],
            'correct_answer': current_question['correct_answer'],
            'category': current_question['category'],
            'is_ai_generated': current_question['is_ai_generated'],
            'question_id': current_question['question_id'],
            'current_question_index': current_question_index + 1,
            'questions_per_player': len(pre_loaded_questions),
            'rapid_fire_mode': True,  # Flag to indicate this is rapid-fire
            'all_questions': pre_loaded_questions,  # Send all questions for client-side rapid delivery
            'all_players': [
                {
                    'id': p.id,
                    'name': p.name,
                    'specialist_subject': p.specialist_subject or '',
                    'current_score': p.current_score or 0
                } for p in all_players
            ],
        }
    
    def _get_player_complete_data(self, round_state: Dict[str, Any]) -> Dict[str, Any]:
        """Current player finished their round"""
        from players.models import Player
        
        current_player_id = round_state.get('current_player_id')
        
        if current_player_id:
            try:
                current_player = Player.objects.get(id=current_player_id)
            except Player.DoesNotExist:
                current_player = None
        else:
            current_player = None
        
        return {
            'state': 'player_complete',
            'current_player': {
                'id': current_player.id,
                'name': current_player.name,
                'specialist_subject': current_player.specialist_subject
            } if current_player else None,
            'message': f'{current_player.name} has completed their specialist round!' if current_player else 'Player completed their round!'
        }
    
    def _get_specialist_question(self, specialist_subject: str, used_question_ids: list):
        """Get a specialist question for the given subject"""
        from .ai_questions import get_specialist_question
        
        # Ensure we have questions
        self._ensure_specialist_questions(specialist_subject)
        
        return get_specialist_question(specialist_subject, exclude_question_ids=used_question_ids)
    
    def _ensure_specialist_questions(self, specialist_subject: str):
        """Ensure we have enough specialist questions for this subject"""
        from .ai_questions import generate_specialist_questions
        
        # Check if we have enough questions
        from .models import MultipleChoiceQuestion
        question_count = MultipleChoiceQuestion.objects.filter(
            category=specialist_subject,
            is_specialist=True
        ).count()
        
        if question_count < self.questions_per_player:
            logger.info(f"Generating {self.questions_per_player} specialist questions for {specialist_subject}")
            # Generate questions synchronously to ensure they're ready for rapid-fire
            generate_specialist_questions(specialist_subject, target_count=self.questions_per_player)
    
    def preload_all_specialist_questions(self):
        """Pre-load specialist questions for all players before MasterMind rounds start"""
        from .ai_questions import generate_specialist_questions
        from .models import MultipleChoiceQuestion
        
        # Get all unique specialist subjects from connected players
        specialist_subjects = set()
        for player in self.game_session.players.filter(is_connected=True):
            if player.specialist_subject and player.specialist_subject.strip():
                specialist_subjects.add(player.specialist_subject.strip())
        
        logger.info(f"Pre-loading specialist questions for subjects: {list(specialist_subjects)}")
        
        # Pre-generate questions for each subject
        for subject in specialist_subjects:
            question_count = MultipleChoiceQuestion.objects.filter(
                category=subject,
                is_specialist=True
            ).count()
            
            if question_count < self.questions_per_player:
                logger.info(f"Pre-loading {self.questions_per_player} specialist questions for {subject}")
                generate_specialist_questions(subject, target_count=self.questions_per_player)
            else:
                logger.info(f"Already have {question_count} questions for {subject}")
    
    def preload_player_questions(self, player_id: int) -> List[Dict[str, Any]]:
        """Pre-load all 25 questions for a player's rapid-fire session"""
        from django.core.cache import cache
        from .models import MultipleChoiceQuestion
        from players.models import Player
        
        # Get the player and their specialist subject
        try:
            player = Player.objects.get(id=player_id, game_session=self.game_session)
            specialist_subject = player.specialist_subject
        except Player.DoesNotExist:
            logger.error(f"Player {player_id} not found")
            return []
        
        if not specialist_subject:
            logger.error(f"Player {player.name} has no specialist subject")
            return []
        
        # Cache key for this player's question set
        cache_key = f'mastermind_questions_{self.game_session.game_code}_{player_id}'
        
        # Check if already cached
        cached_questions = cache.get(cache_key)
        if cached_questions:
            logger.info(f"Using cached questions for {player.name}")
            return cached_questions
        
        # Get 25 questions for this specialist subject
        questions = list(MultipleChoiceQuestion.objects.filter(
            category=specialist_subject,
            is_specialist=True
        ).order_by('usage_count', 'last_used')[:self.questions_per_player])
        
        if len(questions) < self.questions_per_player:
            logger.warning(f"Only {len(questions)} questions available for {specialist_subject}, need {self.questions_per_player}")
        
        # Convert to serializable format
        question_data = []
        for i, question in enumerate(questions):
            question_data.append({
                'question_id': question.id,
                'question_text': question.question_text,
                'choices': question.choices,
                'correct_answer': question.correct_answer,
                'category': specialist_subject,
                'is_ai_generated': question.is_ai_generated,
                'question_number': i + 1,
                'total_questions': len(questions)
            })
        
        # Cache for the duration of the round (10 minutes)
        cache.set(cache_key, question_data, timeout=600)
        logger.info(f"Pre-loaded {len(question_data)} questions for {player.name} ({specialist_subject})")
        
        return question_data
    
    def _generate_general_knowledge_data(self) -> Dict[str, Any]:
        """Generate general knowledge question for final round"""
        # Use the existing multiple choice logic but with hard/medium difficulty
        from .ai_questions import get_question_for_game
        
        # Get a challenging general knowledge question
        categories = ["Science", "History", "Geography", "Literature", "Art", "Philosophy", "Technology"]
        import random
        random.seed(f"{self.game_session.game_code}_{self.round_number}_general")
        category = random.choice(categories)
        
        question = get_question_for_game(category=category)
        
        if question:
            return {
                'phase': 'general',
                'question_text': question.question_text,
                'choices': question.choices,
                'correct_answer': question.correct_answer,
                'category': f"General Knowledge ({question.category})",
                'is_ai_generated': question.is_ai_generated,
                'question_id': question.id
            }
        else:
            return {
                'phase': 'general',
                'question_text': 'What is the largest planet in our solar system?',
                'choices': ['Earth', 'Jupiter', 'Saturn', 'Mars'],
                'correct_answer': 'Jupiter',
                'category': 'General Knowledge (Science)',
                'is_ai_generated': False
            }
    
    def advance_to_next_question(self):
        """Advance to the next question for current player"""
        round_state = self._get_round_state()
        
        state = round_state.get('state')
        if state == 'playing':
            current_question_index = round_state.get('current_question_index', 0)
            used_question_ids = round_state.get('used_question_ids', [])
            
            # Add current question to used list
            if hasattr(self, 'current_question_id'):
                used_question_ids.append(self.current_question_id)
            
            round_state['current_question_index'] = current_question_index + 1
            round_state['used_question_ids'] = used_question_ids
            
            # Check if player has answered enough questions
            if round_state['current_question_index'] >= self.questions_per_player:
                round_state['state'] = 'player_complete'
                # Add current player to completed list
                completed_players = round_state.get('completed_players', [])
                current_player_id = round_state.get('current_player_id')
                if current_player_id and current_player_id not in completed_players:
                    completed_players.append(current_player_id)
                    round_state['completed_players'] = completed_players
        
        self._save_round_state(round_state)
        
        # Clear cache to force regeneration
        from django.core.cache import cache
        cache_key = f'game_{self.game_session.game_code}_round_{self.round_number}_mastermind_data'
        cache.delete(cache_key)
    
    def select_player(self, player_id: int) -> Dict[str, Any]:
        """
        Selects a player to begin their specialist round in Mastermind and updates the round state.
        
        Verifies the player exists, is connected, and has a specialist subject. Prevents selection if the player has already completed their round. Updates the round state to initiate the ready check for the selected player and broadcasts the state change.
        
        Parameters:
            player_id (int): The ID of the player to select.
        
        Returns:
            Dict[str, Any]: A dictionary indicating success or failure, and an error message or confirmation message.
        """
        round_state = self._get_round_state()
        
        # Verify player exists and has specialist subject
        from players.models import Player
        try:
            player = Player.objects.get(
                id=player_id,
                game_session=self.game_session,
                is_connected=True
            )
            if not player.specialist_subject or player.specialist_subject.strip() == '':
                return {'success': False, 'error': 'Player has no specialist subject'}
        except Player.DoesNotExist:
            return {'success': False, 'error': 'Player not found'}
        
        # Check if player already completed
        if player_id in round_state.get('completed_players', []):
            return {'success': False, 'error': 'Player has already completed their round'}
        
        # Set up state for ready check
        round_state['state'] = 'asking_ready'
        round_state['current_player_id'] = player_id
        round_state['current_question_index'] = 0
        round_state['used_question_ids'] = []
        
        self._save_round_state(round_state)

        # Broadcast state change
        from .websocket_utils import broadcast_mastermind_state_change
        round_info = self.get_round_info()
        broadcast_mastermind_state_change(self.game_session, round_info)

        return {
            'success': True,
            'message': f'Selected {player.name} for their specialist round on {player.specialist_subject}'
        }
    
    def player_ready_response(self, is_ready: bool) -> Dict[str, Any]:
        """
        Processes the player's response to the readiness prompt in a Mastermind round.
        
        If the player is ready, preloads specialist questions and transitions the round state to the rapid-fire session, broadcasting the update. If not ready, reverts to player selection and broadcasts the change.
        
        Parameters:
            is_ready (bool): Indicates whether the player is ready to begin the rapid-fire round.
        
        Returns:
            Dict[str, Any]: A dictionary indicating success or failure, with an appropriate message or error.
        """
        round_state = self._get_round_state()
        
        if round_state.get('state') != 'asking_ready':
            return {'success': False, 'error': 'Not waiting for ready response'}
        
        if is_ready:
            # Pre-load all 25 questions for rapid-fire session
            current_player_id = round_state.get('current_player_id')
            if current_player_id:
                logger.info(f"Pre-loading questions for player {current_player_id} rapid-fire session")
                questions = self.preload_player_questions(current_player_id)
                if not questions:
                    return {
                        'success': False,
                        'error': 'Failed to prepare questions for your specialist subject'
                    }
            
            # Start the round for this player
            round_state['state'] = 'playing'
            round_state['current_question_index'] = 0
            round_state['used_question_ids'] = []
            
            self._save_round_state(round_state)

            # Broadcast state change to playing
            from .websocket_utils import broadcast_mastermind_state_change
            round_info = self.get_round_info()
            broadcast_mastermind_state_change(self.game_session, round_info)

            return {
                'success': True,
                'message': f'Starting rapid-fire specialist round! {len(questions) if current_player_id else self.questions_per_player} questions in 90 seconds!'
            }
        else:
            # Player not ready, go back to player selection
            round_state['state'] = 'waiting_for_player_selection'
            round_state['current_player_id'] = None

            self._save_round_state(round_state)

            # Broadcast state change back to player selection
            from .websocket_utils import broadcast_mastermind_state_change
            round_info = self.get_round_info()
            broadcast_mastermind_state_change(self.game_session, round_info)

            return {
                'success': True,
                'message': 'Player not ready, select another player or try again later'
            }
    
    def continue_to_next_player(self) -> Dict[str, Any]:
        """Move from player complete back to player selection"""
        round_state = self._get_round_state()
        
        # Reset to player selection state
        round_state['state'] = 'waiting_for_player_selection'
        round_state['current_player_id'] = None
        round_state['current_question_index'] = 0
        round_state['used_question_ids'] = []
        
        self._save_round_state(round_state)
        
        return {
            'success': True,
            'message': 'Ready to select next player'
        }
    
    def create_player_answer(self, player, answer_text: str):
        """Create PlayerAnswer for Mastermind rounds - auto-scored"""
        from players.models import PlayerAnswer
        
        return PlayerAnswer.objects.create(
            player=player,
            round_number=self.round_number,
            answer_text=answer_text.strip(),
            is_valid=True,  # Will be scored automatically
            points_awarded=0
        )
    
    def perform_automatic_scoring(self, answers):
        """Perform automatic scoring for Mastermind questions"""
        round_data = self.generate_round_data()
        correct_answer_text = round_data.get('correct_answer', '').lower().strip()
        
        if not correct_answer_text:
            logger.error(f"Mastermind round {self.round_number} has no correct answer defined.")
            return

        for answer in answers:
            player_answer_text = answer.answer_text.lower().strip()
            is_correct = (player_answer_text == correct_answer_text)

            points = 0
            reason = ""
            player = answer.player

            if is_correct:
                if round_data.get('phase') == 'specialist':
                    points = 15  # Higher points for specialist questions
                else:
                    points = 10  # Standard points for general knowledge
                    
                player.correct_answer_streak += 1
                reason = "mastermind_correct_answer"

                # Bonus for streak
                if player.correct_answer_streak > 1:
                    streak_bonus = (player.correct_answer_streak - 1) * 3
                    points += streak_bonus
                    reason += f"_streak_{player.correct_answer_streak}"
            else:
                player.correct_answer_streak = 0
                points = 0
                reason = "mastermind_incorrect_answer"

            player.save()

            # Update answer record
            old_points = answer.points_awarded
            answer.is_valid = is_correct
            answer.points_awarded = points
            answer.save()

            # Award points
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
        """Mastermind rounds provide immediate feedback"""
        return True
    
    def supports_manual_validation(self) -> bool:
        """Mastermind rounds don't support manual validation"""
        return False
    
    def get_player_feedback_message(self, player_answer, is_correct: bool, points: int) -> str:
        """Generate feedback message for Mastermind rounds"""
        round_data = self.generate_round_data()
        correct_answer = round_data.get('correct_answer')
        phase = round_data.get('phase', 'specialist')
        
        if is_correct:
            if phase == 'specialist':
                message = f"🧠 Excellent specialist knowledge! You earned {points} points."
            else:
                message = f"🎯 Correct! You earned {points} points."
                
            if player_answer.player.correct_answer_streak > 1:
                message += f" ({player_answer.player.correct_answer_streak} answer streak!)"
                
            message += f"\\n\\nThe correct answer was: {correct_answer}"
            message += f"\\nYour answer: {player_answer.answer_text}"
        else:
            message = f"❌ Incorrect. The correct answer was: {correct_answer}"
            message += f"\\n\\nYour answer: {player_answer.answer_text}"
        
        return message


class MultipleChoiceRoundHandler(BaseRoundHandler):
    """Handler for Multiple Choice quiz rounds"""
    
    ROUND_TYPE = 'multiple_choice'
    DISPLAY_NAME = 'Multiple Choice'
    
    def generate_round_data(self) -> Dict[str, Any]:
        """Generate or retrieve multiple choice question with consistent caching and browser refresh support"""
        # Check cache first for consistency - this is critical for browser refresh handling
        from django.core.cache import cache
        import time
        
        cache_key = f'game_{self.game_session.game_code}_round_{self.round_number}_question_data'
        lock_key = f'game_{self.game_session.game_code}_round_{self.round_number}_lock'
        
        # First check if we have cached question data (includes full question info)
        cached_data = cache.get(cache_key)
        if cached_data:
            logger.info(f"Using CACHED question data for game {self.game_session.game_code}, round {self.round_number}: {cached_data['question_text']}")
            return cached_data
        
        # Simple locking mechanism to prevent race conditions during question generation
        for attempt in range(10):  # Max 10 attempts
            if cache.add(lock_key, 'locked', timeout=30):  # Acquire lock for 30 seconds
                break
            time.sleep(0.1)  # Wait 100ms before retry
        else:
            logger.warning(f"Could not acquire lock for round {self.round_number} in game {self.game_session.game_code}")
        
        try:
            # Double-check cache after acquiring lock (another thread might have populated it)
            cached_data = cache.get(cache_key)
            if cached_data:
                logger.info(f"Using CACHED question data (post-lock) for game {self.game_session.game_code}, round {self.round_number}: {cached_data['question_text']}")
                return cached_data
            
            # Check if we have a cached question ID for backward compatibility
            question_id_cache_key = f'game_{self.game_session.game_code}_round_{self.round_number}_question_id'
            cached_question_id = cache.get(question_id_cache_key)
            
            question = None
            if cached_question_id:
                try:
                    from game_sessions.models import MultipleChoiceQuestion
                    question = MultipleChoiceQuestion.objects.get(id=cached_question_id)
                    logger.info(f"Using CACHED question ID for game {self.game_session.game_code}, round {self.round_number}: {question.question_text}")
                except MultipleChoiceQuestion.DoesNotExist:
                    logger.warning(f"Cached question ID {cached_question_id} not found")
            
            if not question:
                # Use a single, deterministic approach for question selection
                # First try to generate a new question
                question = self._generate_new_question()
                if question:
                    # Add to used questions and cache
                    self.game_session.used_questions.add(question)
                    cache.set(question_id_cache_key, question.id, timeout=3600)
                    logger.info(f"Generated and cached NEW question for game {self.game_session.game_code}, round {self.round_number}: {question.question_text}")
                else:
                    # If generation fails, use deterministic fallback
                    fallback_data = self._get_fallback_question_data()
                    # Cache the fallback data directly
                    cache.set(cache_key, fallback_data, timeout=3600)
                    logger.info(f"Using FALLBACK question data for game {self.game_session.game_code}, round {self.round_number}: {fallback_data['question_text']}")
                    return fallback_data
            
            if question:
                result = {
                    'question_text': question.question_text,
                    'choices': question.choices,
                    'correct_answer': question.correct_answer,
                    'category': question.category,
                    'is_ai_generated': question.is_ai_generated,
                    'question_id': question.id
                }
                # Cache the complete question data for browser refresh consistency
                cache.set(cache_key, result, timeout=3600)
                logger.info(f"Cached complete question data for game {self.game_session.game_code}, round {self.round_number}")
            else:
                # This should never happen, but provide ultimate fallback
                result = {
                    'question_text': 'What is 2 + 2?',
                    'choices': ['3', '4', '5', '6'],
                    'correct_answer': '4',
                    'category': 'Math',
                }
                cache.set(cache_key, result, timeout=3600)
            
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
        """Generate a new multiple choice question using AI"""
        from .ai_questions import get_question_for_game
        
        # Try to get a question (either existing or AI-generated)
        # Use a variety of categories for better question diversity
        import random
        random.seed(f"{self.game_session.game_code}_{self.round_number}_category")
        
        # Categories we have good AI questions for
        categories = ["Science", "History", "Geography", "UK Sports", "Technology", 
                     "Entertainment", "Literature", "Art", "Music", "Food & Cooking", "General Knowledge"]
        category = random.choice(categories)
        
        question_obj = get_question_for_game(category=category)
        
        if question_obj:
            logger.info(f"Got question for game {self.game_session.game_code}, round {self.round_number}: {question_obj.question_text[:50]}...")
            return question_obj  # Return the actual question object
        else:
            logger.warning(f"Could not get AI question for game {self.game_session.game_code}, using fallback")
            return None
    
    def _get_fallback_question_data(self):
        """Get fallback question from database as last resort"""
        # Try to get any question from database as absolute fallback
        from .models import MultipleChoiceQuestion
        import random
        
        # Use a deterministic seed for this round
        random.seed(f"{self.game_session.game_code}_{self.round_number}_fallback")
        
        all_questions = list(MultipleChoiceQuestion.objects.all())
        if all_questions:
            question = random.choice(all_questions)
            logger.info(f"Using fallback database question: {question.question_text[:50]}...")
            return {
                'question_text': question.question_text,
                'choices': question.choices,
                'correct_answer': question.correct_answer,
                'category': question.category,
                'is_ai_generated': question.is_ai_generated,
                'question_id': question.id
            }
        else:
            logger.error("No questions available in database for fallback!")
            return None


# Round handler registry
ROUND_HANDLERS = {
    'flower_fruit_veg': FlowerFruitVegRoundHandler,
    'multiple_choice': MultipleChoiceRoundHandler,
    'mastermind': MastermindRoundHandler,
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