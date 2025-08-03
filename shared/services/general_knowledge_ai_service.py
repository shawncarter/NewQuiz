"""
General Knowledge Question AI Service

Concrete implementation of AIQuestionService for generating general knowledge questions
using the GeneralKnowledgeQuestion model for Mastermind rounds.
"""

import logging
from typing import Dict, Any, Type
from django.db import models
from django.utils import timezone

from .ai_question_service import AIQuestionService

logger = logging.getLogger('mastermind')


class GeneralKnowledgeAIService(AIQuestionService):
    """AI service for generating general knowledge questions for Mastermind rounds"""
    
    def get_question_model(self) -> Type[models.Model]:
        """Return the GeneralKnowledgeQuestion model"""
        from mastermind.models import GeneralKnowledgeQuestion
        return GeneralKnowledgeQuestion
    
    def create_question_prompt(self, category: str = "General Knowledge", **kwargs) -> str:
        """Create prompt for single general knowledge question generation"""
        return f"""Generate 1 general knowledge multiple choice question suitable for a quiz game.

Requirements:
- Medium difficulty level (not too easy, not extremely obscure)
- Focus on widely known facts from diverse categories like history, science, geography, literature, arts, sports, etc.
- Should be fair for a general audience without specialist knowledge
- Avoid questions that require very specific technical expertise
- Return as a JSON object

IMPORTANT: Return ONLY a valid JSON object with:
- "question": The question text
- "choices": Array of exactly 4 answer options
- "correct_answer": One of the choices (exact match)
- "category": "General Knowledge"

Example format:
{{
    "question": "What is the capital of Australia?",
    "choices": ["Sydney", "Melbourne", "Canberra", "Perth"],
    "correct_answer": "Canberra",
    "category": "General Knowledge"
}}

Generate 1 general knowledge question:"""
    
    def create_bulk_questions_prompt(self, category: str = "General Knowledge", count: int = 20, **kwargs) -> str:
        """Create prompt for bulk general knowledge question generation"""
        return f"""Generate {count} different general knowledge multiple choice questions suitable for a quiz game.

Requirements:
- Each question should be medium difficulty level (not too easy, not extremely obscure)
- Cover diverse categories like history, science, geography, literature, arts, sports, entertainment, etc.
- Should be fair for a general audience without specialist knowledge
- Avoid questions that require very specific technical expertise
- Ensure variety in topics and question types
- Return as a JSON array of objects

IMPORTANT: Return ONLY a valid JSON array. Each object must have:
- "question": The question text
- "choices": Array of exactly 4 answer options
- "correct_answer": One of the choices (exact match)
- "category": "General Knowledge"

Example format:
[
  {{
    "question": "What is the capital of Australia?",
    "choices": ["Sydney", "Melbourne", "Canberra", "Perth"],
    "correct_answer": "Canberra",
    "category": "General Knowledge"
  }},
  {{
    "question": "Who wrote the novel '1984'?",
    "choices": ["Aldous Huxley", "George Orwell", "Ray Bradbury", "H.G. Wells"],
    "correct_answer": "George Orwell",
    "category": "General Knowledge"
  }}
]

Generate exactly {count} diverse general knowledge questions:"""
    
    def create_question_instance(self, question_data: Dict[str, Any], **kwargs) -> models.Model:
        """Create a GeneralKnowledgeQuestion instance"""
        from mastermind.models import GeneralKnowledgeQuestion
        
        return GeneralKnowledgeQuestion.objects.create(
            question_text=question_data['question'],
            choices=question_data['choices'],
            correct_answer=question_data['correct_answer'],
            category=question_data.get('category', 'General Knowledge'),
            difficulty=kwargs.get('difficulty', 'medium'),
            is_ai_generated=True
        )
    
    def get_existing_questions_for_duplicate_check(self, category: str = "General Knowledge", **kwargs) -> models.QuerySet:
        """Get existing general knowledge questions for duplicate checking"""
        from mastermind.models import GeneralKnowledgeQuestion
        return GeneralKnowledgeQuestion.objects.all()
    
    def get_general_knowledge_questions(self, count: int = 20, exclude_question_ids: list = None) -> list:
        """
        Get general knowledge questions for mastermind rounds.
        
        Args:
            count: Number of questions to retrieve
            exclude_question_ids: List of question IDs to exclude
            
        Returns:
            List of GeneralKnowledgeQuestion instances
        """
        from mastermind.models import GeneralKnowledgeQuestion
        
        if exclude_question_ids is None:
            exclude_question_ids = []
        
        questions = GeneralKnowledgeQuestion.objects.exclude(
            id__in=exclude_question_ids
        ).order_by('usage_count', 'last_used')[:count]
        
        # Mark questions as used
        for question in questions:
            question.mark_as_used()
        
        return list(questions)
    
    def ensure_general_knowledge_questions(self, minimum_count: int = 50) -> bool:
        """
        Ensure we have enough general knowledge questions.
        
        Args:
            minimum_count: Minimum number of questions required
            
        Returns:
            True if sufficient questions exist or were generated
        """
        from mastermind.models import GeneralKnowledgeQuestion
        
        current_count = GeneralKnowledgeQuestion.objects.count()
        
        if current_count < minimum_count:
            logger.info(f"Need more general knowledge questions: {current_count}/{minimum_count}")
            questions_needed = minimum_count - current_count
            generated = self.generate_bulk_questions("General Knowledge", questions_needed)
            return generated > 0
        else:
            logger.info(f"Sufficient general knowledge questions: {current_count}")
            return True