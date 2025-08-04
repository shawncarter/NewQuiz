"""
Shared AI Question Generation Service

Base class providing common AI question generation functionality with support for
polymorphic question creation across different question types and models.
"""

import json
import logging
import re
from abc import ABC, abstractmethod
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Type, Any, Tuple

from django.conf import settings
from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)


class AIQuestionService(ABC):
    """
    Abstract base class for AI question generation services.
    
    Provides common functionality for OpenAI API interaction, response parsing,
    validation, and duplicate detection while allowing subclasses to implement
    question-type-specific logic.
    """
    
    # Default models to try in order of preference
    DEFAULT_MODELS = ["gpt-4o-mini", "gpt-3.5-turbo", "gpt-4.1-mini"]
    
    # Default OpenAI parameters
    DEFAULT_TEMPERATURE = 0.8
    DEFAULT_MAX_TOKENS = 300
    BULK_MAX_TOKENS = 2000
    
    # Duplicate detection thresholds
    CHOICES_SIMILARITY_THRESHOLD = 0.8
    CORRECT_ANSWER_SIMILARITY_THRESHOLD = 0.9
    TEXT_SIMILARITY_THRESHOLD = 0.8
    
    def __init__(self, models_to_try: Optional[List[str]] = None):
        """
        Initialize the AI question service.
        
        Args:
            models_to_try: List of OpenAI models to try in order. Uses DEFAULT_MODELS if None.
        """
        self.models_to_try = models_to_try or self.DEFAULT_MODELS.copy()
        self._client = None
    
    @property
    def client(self):
        """Lazy initialization of OpenAI client"""
        if self._client is None:
            if not settings.OPENAI_API_KEY:
                raise ValueError("No OpenAI API key configured")
            
            import openai
            self._client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
        
        return self._client
    
    @abstractmethod
    def get_question_model(self) -> Type[models.Model]:
        """Return the Django model class for storing questions"""
        pass
    
    @abstractmethod
    def create_question_prompt(self, category: str, **kwargs) -> str:
        """Create the prompt for AI question generation"""
        pass
    
    @abstractmethod
    def create_bulk_questions_prompt(self, category: str, count: int, **kwargs) -> str:
        """Create the prompt for bulk AI question generation"""
        pass
    
    @abstractmethod
    def create_question_instance(self, question_data: Dict[str, Any], **kwargs) -> models.Model:
        """Create a question instance from validated question data"""
        pass
    
    @abstractmethod
    def get_existing_questions_for_duplicate_check(self, category: str, **kwargs) -> models.QuerySet:
        """Get existing questions to check for duplicates"""
        pass
    
    def generate_single_question(self, category: str = "General Knowledge", **kwargs) -> Optional[models.Model]:
        """
        Generate a single AI question and store if unique.
        
        Args:
            category: Question category/subject
            **kwargs: Additional parameters passed to subclass methods
            
        Returns:
            Created question instance or None if generation failed
        """
        if not settings.OPENAI_API_KEY:
            logger.warning("No OpenAI API key configured")
            return None
        
        try:
            prompt = self.create_question_prompt(category, **kwargs)
            response_text = self._make_openai_request(
                prompt, 
                max_tokens=self.DEFAULT_MAX_TOKENS,
                temperature=self.DEFAULT_TEMPERATURE
            )
            
            question_data = self._parse_single_question_response(response_text)
            if not question_data:
                return None
            
            if not self._validate_question_data(question_data):
                return None
            
            if self._is_duplicate_question(question_data, category, **kwargs):
                logger.info(f"Question is duplicate, skipping: {question_data['question'][:50]}...")
                return None
            
            question = self.create_question_instance(question_data, **kwargs)
            logger.info(f"Created new AI question: {question_data['question'][:50]}...")
            return question
            
        except Exception as e:
            logger.error(f"Error generating AI question: {e}")
            return None
    
    def generate_bulk_questions(self, category: str, target_count: int, **kwargs) -> int:
        """
        Generate multiple questions for a specific category.
        
        Args:
            category: Question category/subject
            target_count: Number of questions to generate
            **kwargs: Additional parameters passed to subclass methods
            
        Returns:
            Number of successfully created questions
        """
        if not settings.OPENAI_API_KEY:
            logger.warning("No OpenAI API key configured for bulk question generation")
            return 0
        
        if not category or not category.strip():
            logger.error("No category provided")
            return 0
        
        category = category.strip()
        generated_count = 0
        
        try:
            prompt = self.create_bulk_questions_prompt(category, target_count, **kwargs)
            response_text = self._make_openai_request(
                prompt,
                max_tokens=self.BULK_MAX_TOKENS,
                temperature=self.DEFAULT_TEMPERATURE
            )
            
            questions_data = self._parse_bulk_questions_response(response_text)
            if not questions_data:
                return generated_count
            
            for question_data in questions_data:
                if not self._validate_question_data(question_data):
                    continue
                
                if self._is_duplicate_question(question_data, category, **kwargs):
                    logger.info(f"Skipping duplicate question: {question_data['question'][:50]}...")
                    continue
                
                try:
                    question = self.create_question_instance(question_data, **kwargs)
                    generated_count += 1
                    logger.info(f"Created question #{generated_count}: {question_data['question'][:50]}...")
                except Exception as e:
                    logger.error(f"Error creating question: {e}")
                    continue
            
            logger.info(f"Generated {generated_count} new questions for {category}")
            return generated_count
            
        except Exception as e:
            logger.error(f"Error generating bulk questions for {category}: {e}")
            return generated_count
    
    def _make_openai_request(self, prompt: str, max_tokens: int, temperature: float) -> str:
        """
        Make OpenAI API request with model fallback logic.
        
        Args:
            prompt: The prompt to send to OpenAI
            max_tokens: Maximum tokens for response
            temperature: Temperature for response generation
            
        Returns:
            Response text from OpenAI
            
        Raises:
            Exception: If all models fail
        """
        for model in self.models_to_try:
            try:
                # Handle o3-mini model which doesn't support temperature
                if model == "o3-mini":
                    response = self.client.chat.completions.create(
                        model=model,
                        messages=[{"role": "user", "content": prompt}],
                        max_completion_tokens=max_tokens
                    )
                else:
                    response = self.client.chat.completions.create(
                        model=model,
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=max_tokens,
                        temperature=temperature
                    )
                
                logger.info(f"Successfully used model: {model}")
                return response.choices[0].message.content.strip()
                
            except Exception as model_error:
                logger.warning(f"Model {model} failed: {model_error}")
                if model == self.models_to_try[-1]:  # Last model failed
                    raise model_error
                continue
        
        raise Exception("All models failed")
    
    def _parse_single_question_response(self, response_text: str) -> Optional[Dict[str, Any]]:
        """Parse single question from AI response"""
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            return self._extract_json_from_text(response_text, expect_array=False)
    
    def _parse_bulk_questions_response(self, response_text: str) -> Optional[List[Dict[str, Any]]]:
        """Parse multiple questions from AI response"""
        try:
            questions_data = json.loads(response_text)
            if not isinstance(questions_data, list):
                logger.error(f"Expected list of questions, got {type(questions_data)}")
                return None
            return questions_data
        except json.JSONDecodeError:
            return self._extract_json_from_text(response_text, expect_array=True)
    
    def _extract_json_from_text(self, text: str, expect_array: bool = False) -> Optional[Any]:
        """
        Extract JSON from text that may contain markdown or other formatting.
        
        Args:
            text: Text potentially containing JSON
            expect_array: Whether to expect a JSON array or object
            
        Returns:
            Parsed JSON data or None if extraction failed
        """
        # Remove markdown code blocks
        cleaned_text = re.sub(r'```json\s*|\s*```', '', text, flags=re.IGNORECASE)
        cleaned_text = cleaned_text.strip()
        
        try:
            return json.loads(cleaned_text)
        except json.JSONDecodeError:
            # Try to find JSON in the response
            pattern = r'\[.*\]' if expect_array else r'\{.*\}'
            json_match = re.search(pattern, cleaned_text, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except json.JSONDecodeError:
                    logger.error(f"Could not parse extracted JSON: {json_match.group()[:200]}...")
                    return None
            else:
                logger.error(f"Could not find JSON in response: {text[:200]}...")
                return None
    
    def _validate_question_data(self, question_data: Dict[str, Any]) -> bool:
        """
        Validate that question data has all required fields and correct structure.
        
        Args:
            question_data: Dictionary containing question data
            
        Returns:
            True if valid, False otherwise
        """
        required_fields = ['question', 'choices', 'correct_answer']
        
        if not all(field in question_data for field in required_fields):
            logger.error(f"Missing required fields in question data: {question_data}")
            return False
        
        if not isinstance(question_data['choices'], list) or len(question_data['choices']) != 4:
            logger.error(f"Expected 4 choices, got {len(question_data.get('choices', []))}")
            return False
        
        if question_data['correct_answer'] not in question_data['choices']:
            logger.error(f"Correct answer not in choices: {question_data}")
            return False
        
        return True
    
    def _is_duplicate_question(self, question_data: Dict[str, Any], category: str, **kwargs) -> bool:
        """
        Check if question is duplicate using fuzzy matching.
        
        Args:
            question_data: New question data to check
            category: Question category
            **kwargs: Additional parameters for subclass filtering
            
        Returns:
            True if duplicate found, False otherwise
        """
        # Create normalized data for comparison
        new_choices = sorted([choice.lower().strip() for choice in question_data['choices']])
        new_correct = question_data['correct_answer'].lower().strip()
        new_text = question_data['question'].lower().strip()
        
        # Get existing questions for comparison
        existing_questions = self.get_existing_questions_for_duplicate_check(category, **kwargs)
        
        for existing in existing_questions:
            # Check text similarity first (most specific)
            text_similarity = SequenceMatcher(None, new_text, existing.question_text.lower().strip()).ratio()
            if text_similarity > self.TEXT_SIMILARITY_THRESHOLD:
                logger.info(f"Found similar question text: {text_similarity:.2f}")
                return True
            
            # Check answer set similarity
            existing_choices = sorted([choice.lower().strip() for choice in existing.choices])
            existing_correct = existing.correct_answer.lower().strip()
            
            choices_similarity = SequenceMatcher(None, str(new_choices), str(existing_choices)).ratio()
            correct_similarity = SequenceMatcher(None, new_correct, existing_correct).ratio()
            
            # Consider duplicate if answer sets are similar AND correct answers are very similar
            if (choices_similarity > self.CHOICES_SIMILARITY_THRESHOLD and 
                correct_similarity > self.CORRECT_ANSWER_SIMILARITY_THRESHOLD):
                logger.info(f"Found similar question: {choices_similarity:.2f} choices, {correct_similarity:.2f} correct")
                return True
        
        return False