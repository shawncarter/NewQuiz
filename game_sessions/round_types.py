"""
Round type handlers for different game modes.
Provides a pluggable architecture for various round types.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Type
import random


class BaseRoundHandler(ABC):
    """
    Abstract base class for all round type handlers.
    Each round type must implement this interface.
    """
    
    def __init__(self, game_session, round_number: int, seed: Optional[int] = None):
        self.game_session = game_session
        self.round_number = round_number
        if game_session and hasattr(game_session, 'game_code'):
            self.seed = seed or hash(game_session.game_code)
            self.random = random.Random(self.seed + round_number)
        else:
            # For registry initialization or testing
            self.seed = seed or 0
            self.random = random.Random(self.seed)
    
    @property
    @abstractmethod
    def round_type_name(self) -> str:
        """Human readable name for this round type"""
        pass
    
    @property
    @abstractmethod
    def round_type_id(self) -> str:
        """Unique identifier for this round type"""
        pass
    
    @abstractmethod
    def generate_round_data(self) -> Dict[str, Any]:
        """
        Generate the data needed for this round.
        Returns a dictionary with round-specific data.
        """
        pass
    
    @abstractmethod
    def validate_answer(self, answer: str) -> Dict[str, Any]:
        """
        Validate a player's answer for this round.
        Returns validation result with score and feedback.
        """
        pass
    
    def get_template_context(self) -> Dict[str, Any]:
        """
        Additional context data for rendering templates.
        Override in subclasses to provide round-specific template data.
        """
        return {}
    
    def get_client_data(self) -> Dict[str, Any]:
        """
        Data to send to clients via WebSocket.
        Override in subclasses to provide round-specific client data.
        """
        round_data = self.generate_round_data()
        return {
            'round_type': self.round_type_id,
            'round_type_name': self.round_type_name,
            **round_data
        }


class CategoryLetterRoundHandler(BaseRoundHandler):
    """
    Handler for the original category + letter round type.
    Players name items in a category starting with a specific letter.
    """
    
    @property
    def round_type_name(self) -> str:
        return "Category & Letter"
    
    @property
    def round_type_id(self) -> str:
        return "category_letter"
    
    def generate_round_data(self) -> Dict[str, Any]:
        """Generate category and letter for this round"""
        import logging
        logger = logging.getLogger(__name__)
        
        # Get categories from game configuration
        categories = []
        if self.game_session:
            try:
                config = self.game_session.configuration
                categories = list(config.categories.all()) if config.categories.exists() else []
                logger.info(f"Retrieved {len(categories)} categories from config")
                if categories:
                    logger.info(f"First category type: {type(categories[0])}, content: {categories[0]}")
            except Exception as e:
                logger.error(f"Error getting categories from config: {e}")
                categories = []
        
        if not categories:
            # Fallback to hardcoded categories (existing behavior)
            available_categories = [
                'Animals', 'Countries', 'Cities', 'Foods', 'Movies', 'Books', 'TV Shows',
                'Sports', 'Cars', 'Colors', 'Fruits', 'Vegetables', 'Clothing',
                'Household Items', 'School Subjects', 'Jobs', 'Hobbies', 'Tools',
                'Musical Instruments', 'Board Games'
            ]
            # Create category-like object for consistency
            category_name = self.random.choice(available_categories)
            category = type('Category', (), {'name': category_name, 'id': None})()
            logger.info(f"Using fallback category: {category_name}")
        else:
            category = self.random.choice(categories)
            logger.info(f"Selected category type: {type(category)}, content: {category}")
        
        # Generate prompt letter (A-Z, excluding difficult letters)
        available_letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        prompt_letter = self.random.choice(available_letters)
        
        # Extract category name safely
        try:
            if hasattr(category, 'name'):
                category_name = category.name
                category_id = getattr(category, 'id', None)
                logger.info(f"Category has name attribute: {category_name}")
            elif isinstance(category, dict):
                category_name = category.get('name', 'Unknown Category')
                category_id = category.get('id', None)
                logger.info(f"Category is dict with name: {category_name}")
            else:
                category_name = str(category)
                category_id = None
                logger.info(f"Category converted to string: {category_name}")
        except Exception as e:
            logger.error(f"Error extracting category name: {e}, category type: {type(category)}, category: {category}")
            category_name = "Unknown Category"
            category_id = None
        
        return {
            'category': {
                'id': category_id,
                'name': category_name
            },
            'prompt_letter': prompt_letter,
            'instruction': f'Name a {category_name.lower()} starting with "{prompt_letter}"'
        }
    
    def validate_answer(self, answer: str) -> Dict[str, Any]:
        """
        Basic validation for category/letter answers.
        More sophisticated validation can be added later.
        """
        if not answer or not answer.strip():
            return {
                'is_valid': False,
                'points': 0,
                'feedback': 'No answer provided'
            }
        
        round_data = self.generate_round_data()
        prompt_letter = round_data['prompt_letter']
        
        answer_clean = answer.strip().upper()
        if not answer_clean.startswith(prompt_letter):
            return {
                'is_valid': False,
                'points': 0,
                'feedback': f'Answer must start with "{prompt_letter}"'
            }
        
        # Basic validation - assume valid if starts with correct letter
        # In future, this could check against dictionaries or use AI validation
        return {
            'is_valid': True,
            'points': None,  # Points calculated by scoring system
            'feedback': 'Valid answer'
        }


class MultipleChoiceRoundHandler(BaseRoundHandler):
    """
    Handler for multiple choice questions.
    Players select from predefined answer choices.
    """
    
    # Hardcoded questions for now - will be replaced with AI generation later
    QUESTIONS = [
        {
            'question': 'What is the capital of France?',
            'choices': ['London', 'Berlin', 'Paris', 'Madrid'],
            'correct_answer': 'Paris',
            'category': 'Geography'
        },
        {
            'question': 'Which planet is known as the Red Planet?',
            'choices': ['Venus', 'Mars', 'Jupiter', 'Saturn'],
            'correct_answer': 'Mars',
            'category': 'Science'
        },
        {
            'question': 'Who wrote "Romeo and Juliet"?',
            'choices': ['Charles Dickens', 'William Shakespeare', 'Jane Austen', 'Mark Twain'],
            'correct_answer': 'William Shakespeare',
            'category': 'Literature'
        },
        {
            'question': 'What is 7 × 8?',
            'choices': ['54', '56', '64', '48'],
            'correct_answer': '56',
            'category': 'Mathematics'
        },
        {
            'question': 'Which ocean is the largest?',
            'choices': ['Atlantic', 'Indian', 'Arctic', 'Pacific'],
            'correct_answer': 'Pacific',
            'category': 'Geography'
        },
        {
            'question': 'What is the chemical symbol for gold?',
            'choices': ['Go', 'Gd', 'Au', 'Ag'],
            'correct_answer': 'Au',
            'category': 'Science'
        },
        {
            'question': 'In which year did World War II end?',
            'choices': ['1944', '1945', '1946', '1947'],
            'correct_answer': '1945',
            'category': 'History'
        },
        {
            'question': 'What is the largest mammal?',
            'choices': ['Elephant', 'Blue Whale', 'Giraffe', 'Hippopotamus'],
            'correct_answer': 'Blue Whale',
            'category': 'Animals'
        },
        {
            'question': 'Which programming language was created by Guido van Rossum?',
            'choices': ['Java', 'Python', 'C++', 'JavaScript'],
            'correct_answer': 'Python',
            'category': 'Technology'
        },
        {
            'question': 'What is the smallest country in the world?',
            'choices': ['Monaco', 'Vatican City', 'San Marino', 'Liechtenstein'],
            'correct_answer': 'Vatican City',
            'category': 'Geography'
        }
    ]
    
    @property
    def round_type_name(self) -> str:
        return "Multiple Choice"
    
    @property
    def round_type_id(self) -> str:
        return "multiple_choice"
    
    def generate_round_data(self) -> Dict[str, Any]:
        """Generate a multiple choice question for this round"""
        question_data = self.random.choice(self.QUESTIONS)
        
        # Shuffle the choices for this round
        choices = question_data['choices'].copy()
        self.random.shuffle(choices)
        
        return {
            'question': question_data['question'],
            'choices': choices,
            'category': question_data['category'],
            'instruction': 'Select the correct answer',
            'correct_answer': question_data['correct_answer']  # Don't send to client
        }
    
    def validate_answer(self, answer: str) -> Dict[str, Any]:
        """
        Validate multiple choice answer.
        Answer should be exact match to one of the choices.
        """
        if not answer or not answer.strip():
            return {
                'is_valid': False,
                'points': 0,
                'feedback': 'No answer selected'
            }
        
        round_data = self.generate_round_data()
        correct_answer = round_data['correct_answer']
        choices = round_data['choices']
        
        answer_clean = answer.strip()
        
        if answer_clean not in choices:
            return {
                'is_valid': False,
                'points': 0,
                'feedback': 'Invalid choice selected'
            }
        
        is_correct = answer_clean == correct_answer
        return {
            'is_valid': True,
            'is_correct': is_correct,
            'points': 10 if is_correct else 0,  # Fixed points, no speed bonus
            'feedback': 'Correct!' if is_correct else f'Incorrect. The answer was: {correct_answer}'
        }
    
    def get_client_data(self) -> Dict[str, Any]:
        """
        Override to exclude correct answer from client data
        """
        round_data = self.generate_round_data()
        client_data = round_data.copy()
        client_data.pop('correct_answer', None)  # Remove correct answer
        
        return {
            'round_type': self.round_type_id,
            'round_type_name': self.round_type_name,
            **client_data
        }


class RoundTypeRegistry:
    """
    Registry for all available round types.
    Provides factory methods to create round handlers.
    """
    
    _handlers: Dict[str, Type[BaseRoundHandler]] = {}
    
    @classmethod
    def register(cls, handler_class: Type[BaseRoundHandler]):
        """Register a round handler class"""
        handler_instance = handler_class(None, 0)  # Temporary instance for metadata
        cls._handlers[handler_instance.round_type_id] = handler_class
    
    @classmethod
    def get_handler(cls, round_type_id: str, game_session, round_number: int, seed: Optional[int] = None) -> BaseRoundHandler:
        """Get a handler instance for the specified round type"""
        if round_type_id not in cls._handlers:
            raise ValueError(f"Unknown round type: {round_type_id}")
        
        handler_class = cls._handlers[round_type_id]
        return handler_class(game_session, round_number, seed)
    
    @classmethod
    def get_available_types(cls) -> List[Dict[str, str]]:
        """Get list of all available round types"""
        types = []
        for handler_class in cls._handlers.values():
            # Create temporary instance to get metadata
            temp_instance = handler_class(None, 0)
            types.append({
                'id': temp_instance.round_type_id,
                'name': temp_instance.round_type_name
            })
        return types


# Register available round types
RoundTypeRegistry.register(CategoryLetterRoundHandler)
RoundTypeRegistry.register(MultipleChoiceRoundHandler)