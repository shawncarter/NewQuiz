"""
Multiple Choice Question AI Service

Concrete implementation of AIQuestionService for generating general knowledge
multiple choice questions using the MultipleChoiceQuestion model.
"""

import logging
from typing import Dict, Any, Type
from django.db import models
from django.utils import timezone

from .ai_question_service import AIQuestionService

logger = logging.getLogger(__name__)


class MultipleChoiceAIService(AIQuestionService):
    """AI service for generating general multiple choice questions"""
    
    def get_question_model(self) -> Type[models.Model]:
        """Return the MultipleChoiceQuestion model"""
        from game_sessions.models import MultipleChoiceQuestion
        return MultipleChoiceQuestion
    
    def create_question_prompt(self, category: str = "General Knowledge", **kwargs) -> str:
        """Create prompt for single question generation"""
        
        if category == "UK Sports" or category == "Sports":
            return f"""Generate a multiple choice question about UK/British sports.

Focus on:
- Football (soccer), Rugby, Cricket, Tennis
- British athletes, teams, venues  
- Premier League, Wimbledon, Six Nations, The Ashes
- Avoid American sports (NFL, NBA, MLB, NHL)

AVOID typical questions like:
- "Who won Wimbledon in 2013?" (too common)
- "Which team won the most Premier League titles?" (overused)

Instead focus on:
- Lesser-known historical facts
- Specific records or achievements  
- Unusual rules or trivia
- Stadium names, kit colors, nicknames
- Memorable moments beyond the obvious

Requirements:
- Return ONLY valid JSON format
- 4 answer choices exactly
- Make it challenging but fair
- Avoid the most obvious/googled questions

Format:
{{
    "question": "Your question here?",
    "choices": ["Option A", "Option B", "Option C", "Option D"],
    "correct_answer": "Option B", 
    "category": "{category}"
}}"""
        else:
            return f"""Generate a multiple choice question for the category "{category}".

AVOID typical overused trivia questions like:
- "What is the largest planet?" (Mars/Jupiter questions)
- "Who painted Starry Night?" (van Gogh)
- "Who plays Tony Stark?" (Robert Downey Jr)
- "What is the chemical symbol for gold?" (Au)
- "What is the capital of France?" (Paris)
- "Who wrote Romeo and Juliet?" (Shakespeare)

Instead create questions about:
- Lesser-known facts within the subject
- Specific technical details
- Historical context beyond the famous events
- Connections between concepts
- Unusual or surprising information
- Deeper knowledge that's still accessible

Requirements:
- Return ONLY valid JSON format
- 4 answer choices exactly
- Make it moderately challenging but avoid the most common trivia
- Focus on interesting, less obvious aspects of {category}
- Ensure the question would make someone think "I didn't know that!"

Format:
{{
    "question": "Your question here?",
    "choices": ["Option A", "Option B", "Option C", "Option D"],
    "correct_answer": "Option B",
    "category": "{category}"
}}"""
    
    def create_bulk_questions_prompt(self, category: str, count: int, **kwargs) -> str:
        """Create prompt for bulk question generation"""
        is_specialist = kwargs.get('is_specialist', False)
        
        if is_specialist:
            return f"""Generate {count} different multiple choice questions specifically about "{category}".

Requirements:
- Each question should be medium to hard difficulty
- Focus on deeper knowledge, not basic facts
- Include technical details, historical context, or specialist terminology
- Avoid the most obvious questions that anyone might know
- Questions should be suitable for someone who considers this their specialist subject
- Return as a JSON array of objects

IMPORTANT: Return ONLY a valid JSON array. Each object must have:
- "question": The question text
- "choices": Array of exactly 4 answer options
- "correct_answer": One of the choices (exact match)
- "category": "{category}"

Example format:
[
  {{
    "question": "Your specialist question here?",
    "choices": ["Option A", "Option B", "Option C", "Option D"],
    "correct_answer": "Option B",
    "category": "{category}"
  }}
]

Generate {count} questions about {category}:"""
        else:
            return f"""Generate {count} different multiple choice questions for the category "{category}".

AVOID typical overused trivia questions and focus on:
- Lesser-known facts within the subject
- Specific technical details
- Historical context beyond the famous events
- Connections between concepts
- Unusual or surprising information
- Deeper knowledge that's still accessible

Requirements:
- Return ONLY valid JSON array
- Each question should have exactly 4 answer choices
- Make questions moderately challenging but accessible
- Focus on interesting, less obvious aspects of {category}

Format:
[
  {{
    "question": "Your question here?",
    "choices": ["Option A", "Option B", "Option C", "Option D"],
    "correct_answer": "Option B",
    "category": "{category}"
  }}
]

Generate exactly {count} questions:"""
    
    def create_question_instance(self, question_data: Dict[str, Any], **kwargs) -> models.Model:
        """Create a MultipleChoiceQuestion instance"""
        QuestionModel = self.get_question_model()
        
        is_specialist = kwargs.get('is_specialist', False)
        
        return QuestionModel.objects.create(
            question_text=question_data['question'],
            choices=question_data['choices'],
            correct_answer=question_data['correct_answer'],
            category=question_data.get('category', 'General Knowledge'),
            is_ai_generated=True,
            is_specialist=is_specialist
        )
    
    def get_existing_questions_for_duplicate_check(self, category: str, **kwargs) -> models.QuerySet:
        """Get existing questions for duplicate checking"""
        QuestionModel = self.get_question_model()
        
        # For MultipleChoiceQuestion, we check all questions regardless of specialist status
        # to avoid duplicates across both general and specialist questions
        return QuestionModel.objects.all()
    
    def get_question_for_game(self, category: str = "General Knowledge", 
                             exclude_recent_days: int = 1, 
                             force_ai_generation: bool = True,
                             is_specialist: bool = False) -> models.Model:
        """
        Get a question for the game, prioritizing AI generation to grow the database.
        
        Args:
            category: Question category
            exclude_recent_days: Days to exclude recently used questions
            force_ai_generation: Whether to try AI generation first
            is_specialist: Whether this is for specialist rounds
            
        Returns:
            Question instance or None
        """
        QuestionModel = self.get_question_model()
        
        # FIRST: Try to generate a new AI question if requested
        if force_ai_generation:
            logger.info(f"Trying to generate new AI question for {category} to grow database...")
            new_question = self.generate_single_question(category, is_specialist=is_specialist)
            
            if new_question:
                # Mark as used and return the new AI question
                new_question.last_used = timezone.now()
                new_question.usage_count = 1
                new_question.save()
                logger.info(f"✅ Generated NEW AI question: {new_question.question_text[:50]}...")
                return new_question
        
        # SECOND: Use existing questions
        logger.info(f"Using existing questions for {category}...")
        
        from datetime import timedelta
        cutoff_date = timezone.now() - timedelta(days=exclude_recent_days)
        
        # Build query for existing questions
        query_filters = {'category': category}
        if is_specialist:
            query_filters['is_specialist'] = True
        
        available_questions = QuestionModel.objects.filter(
            **query_filters
        ).exclude(
            last_used__gte=cutoff_date
        ).order_by('usage_count', 'last_used')
        
        if available_questions.exists():
            question = available_questions.first()
            question.last_used = timezone.now()
            question.usage_count += 1
            question.save()
            logger.info(f"💾 Using existing question: {question.question_text[:50]}...")
            return question
        
        # FINAL: Fallback to any existing question
        fallback_questions = QuestionModel.objects.filter(**query_filters)
        if fallback_questions.exists():
            question = fallback_questions.order_by('usage_count').first()
            question.last_used = timezone.now()
            question.usage_count += 1
            question.save()
            logger.info(f"💾 Using fallback question: {question.question_text[:50]}...")
            return question
        
        return None