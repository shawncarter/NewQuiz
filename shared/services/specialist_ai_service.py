"""
Specialist Question AI Service

Concrete implementation of AIQuestionService for generating specialist questions
using the SpecialistQuestion model for Mastermind rounds.
"""

import logging
from typing import Dict, Any, Type
from django.db import models
from django.utils import timezone

from .ai_question_service import AIQuestionService

logger = logging.getLogger('mastermind')


class SpecialistAIService(AIQuestionService):
    """AI service for generating specialist questions for Mastermind rounds"""
    
    def get_question_model(self) -> Type[models.Model]:
        """Return the SpecialistQuestion model"""
        from mastermind.models import SpecialistQuestion
        return SpecialistQuestion
    
    def create_question_prompt(self, category: str, **kwargs) -> str:
        """Create prompt for single specialist question generation"""
        return f"""Generate 1 multiple choice question specifically about "{category}".

Requirements:
- Medium to hard difficulty level
- Focus on deeper knowledge, not basic facts
- Include technical details, historical context, or specialist terminology
- Avoid the most obvious questions that anyone might know
- Question should be suitable for someone who considers this their specialist subject
- Return as a JSON object

IMPORTANT: Return ONLY a valid JSON object with:
- "question": The question text
- "choices": Array of exactly 4 answer options
- "correct_answer": One of the choices (exact match)
- "category": "{category}"

Example format:
{{
    "question": "What is...",
    "choices": ["Option A", "Option B", "Option C", "Option D"],
    "correct_answer": "Option B",
    "category": "{category}"
}}

Generate 1 specialist question about {category}:"""
    
    def create_bulk_questions_prompt(self, category: str, count: int, **kwargs) -> str:
        """Create prompt for bulk specialist question generation"""
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
    "question": "What is...",
    "choices": ["Option A", "Option B", "Option C", "Option D"],
    "correct_answer": "Option B",
    "category": "{category}"
  }}
]

Generate exactly {count} questions:"""
    
    def create_question_instance(self, question_data: Dict[str, Any], **kwargs) -> models.Model:
        """Create a SpecialistQuestion instance"""
        from mastermind.models import Subject, SpecialistQuestion
        
        subject_name = question_data.get('category', kwargs.get('subject_name', 'Unknown'))
        
        # Get or create the subject
        subject, created = Subject.objects.get_or_create(
            name=subject_name,
            defaults={'description': f'Specialist questions for {subject_name}'}
        )
        
        if created:
            logger.info(f"Created new subject: {subject_name}")
        
        return SpecialistQuestion.objects.create(
            subject=subject,
            question_text=question_data['question'],
            choices=question_data['choices'],
            correct_answer=question_data['correct_answer'],
            difficulty=kwargs.get('difficulty', 'medium'),
            is_ai_generated=True
        )
    
    def get_existing_questions_for_duplicate_check(self, category: str, **kwargs) -> models.QuerySet:
        """Get existing specialist questions for duplicate checking"""
        from mastermind.models import Subject, SpecialistQuestion
        
        try:
            subject = Subject.objects.get(name=category)
            return SpecialistQuestion.objects.filter(subject=subject)
        except Subject.DoesNotExist:
            # If subject doesn't exist yet, return empty queryset
            return SpecialistQuestion.objects.none()
    
    def get_specialist_question(self, specialist_subject: str, 
                               exclude_question_ids: list = None) -> models.Model:
        """
        Get a specialist question for the given subject.
        
        Args:
            specialist_subject: The specialist subject name
            exclude_question_ids: List of question IDs to exclude
            
        Returns:
            SpecialistQuestion instance or None
        """
        from mastermind.models import Subject, SpecialistQuestion
        
        if exclude_question_ids is None:
            exclude_question_ids = []
        
        try:
            subject = Subject.objects.get(name=specialist_subject, is_active=True)
            
            questions = SpecialistQuestion.objects.filter(
                subject=subject
            ).exclude(
                id__in=exclude_question_ids
            ).order_by('usage_count', 'last_used')
            
            if questions.exists():
                question = questions.first()
                question.mark_as_used()
                return question
            else:
                logger.warning(f"No specialist questions available for {specialist_subject}")
                return None
                
        except Subject.DoesNotExist:
            logger.error(f"Subject '{specialist_subject}' not found")
            return None
    
    def ensure_specialist_questions(self, specialist_subject: str, 
                                  minimum_count: int = 25) -> bool:
        """
        Ensure we have enough specialist questions for this subject.
        
        Args:
            specialist_subject: The specialist subject name
            minimum_count: Minimum number of questions required
            
        Returns:
            True if sufficient questions exist or were generated
        """
        from mastermind.models import Subject, SpecialistQuestion
        
        try:
            subject = Subject.objects.get(name=specialist_subject, is_active=True)
            current_count = SpecialistQuestion.objects.filter(subject=subject).count()
            
            if current_count < minimum_count:
                logger.info(f"Need more questions for {specialist_subject}: {current_count}/{minimum_count}")
                questions_needed = minimum_count - current_count
                generated = self.generate_bulk_questions(specialist_subject, questions_needed)
                return generated > 0
            else:
                logger.info(f"Sufficient questions for {specialist_subject}: {current_count}")
                return True
                
        except Subject.DoesNotExist:
            logger.info(f"Subject '{specialist_subject}' not found, creating and generating questions")
            generated = self.generate_bulk_questions(specialist_subject, minimum_count)
            return generated > 0