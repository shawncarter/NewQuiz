"""
Backward Compatibility Layer for Question Model Unification

This module provides compatibility classes and utilities to maintain backward
compatibility during the transition from separate MultipleChoiceQuestion and
SpecialistQuestion models to the unified Question model.

Key features:
- Proxy models that maintain the original API
- Automatic question_type setting based on usage
- Transparent migration between old and new models
- Type hints for smooth IDE integration
"""

from typing import Type, Optional, Union, Any
from django.db import models
from django.core.exceptions import ObjectDoesNotExist

import logging

logger = logging.getLogger(__name__)


class QuestionCompatibilityManager:
    """Manager to handle compatibility between old and new question models"""
    
    def __init__(self):
        self._old_models_available = True
        self._check_old_models()
    
    def _check_old_models(self):
        """Check if old models are still available"""
        try:
            from game_sessions.models import MultipleChoiceQuestion
            from mastermind.models import SpecialistQuestion
            self._old_models_available = True
        except ImportError:
            self._old_models_available = False
            logger.info("Old question models not available - using unified models only")
    
    def get_question_by_id(self, question_id: int, question_type: str = None) -> Optional[models.Model]:
        """
        Get a question by ID, checking both old and new models
        
        Args:
            question_id: The question ID
            question_type: 'general' or 'specialist' (optional hint)
            
        Returns:
            Question instance from either old or new model
        """
        from shared.models import Question
        
        # First try the unified model
        try:
            question = Question.objects.get(id=question_id)
            return question
        except Question.DoesNotExist:
            pass
        
        if not self._old_models_available:
            return None
        
        # Try old models if unified model doesn't have it
        try:
            if question_type == 'specialist':
                from mastermind.models import SpecialistQuestion
                return SpecialistQuestion.objects.get(id=question_id)
            else:
                from game_sessions.models import MultipleChoiceQuestion
                return MultipleChoiceQuestion.objects.get(id=question_id)
        except (ObjectDoesNotExist, ImportError):
            return None
    
    def migrate_question_to_unified(self, old_question: models.Model) -> Optional[models.Model]:
        """
        Migrate a question from old model to unified model
        
        Args:
            old_question: Instance from MultipleChoiceQuestion or SpecialistQuestion
            
        Returns:
            New Question instance or None if migration failed
        """
        from shared.models import Question, Subject
        
        try:
            # Determine question type
            if hasattr(old_question, 'subject'):
                # This is a SpecialistQuestion
                question_type = 'specialist'
                subject, _ = Subject.objects.get_or_create(
                    name=old_question.subject.name,
                    defaults={
                        'description': old_question.subject.description,
                        'is_active': old_question.subject.is_active
                    }
                )
                category = old_question.subject.name
            else:
                # This is a MultipleChoiceQuestion
                question_type = 'general'
                subject = None
                category = old_question.category
            
            # Create unified question
            new_question = Question.objects.create(
                question_text=old_question.question_text,
                choices=old_question.choices,
                correct_answer=old_question.correct_answer,
                question_type=question_type,
                category=category,
                subject=subject,
                difficulty=getattr(old_question, 'difficulty', 'medium'),
                created_at=old_question.created_at,
                last_used=old_question.last_used,
                usage_count=old_question.usage_count,
                is_ai_generated=old_question.is_ai_generated,
            )
            
            logger.info(f"Migrated {question_type} question: {old_question.question_text[:50]}...")
            return new_question
            
        except Exception as e:
            logger.error(f"Failed to migrate question {old_question.id}: {str(e)}")
            return None


# Global compatibility manager instance
compat_manager = QuestionCompatibilityManager()


class MultipleChoiceQuestionProxy(models.Model):
    """
    Proxy model to maintain backward compatibility for MultipleChoiceQuestion
    
    This model provides the same interface as the original MultipleChoiceQuestion
    but delegates to the unified Question model with question_type='general'
    """
    
    class Meta:
        proxy = True
        app_label = 'shared'
    
    @classmethod
    def get_model_class(cls):
        """Get the actual model class (Question)"""
        from shared.models import Question
        return Question
    
    @classmethod
    def objects_manager(cls):
        """Get a manager that filters for general questions"""
        Question = cls.get_model_class()
        return Question.objects.filter(question_type='general')
    
    @property
    def objects(self):
        """Property to access the filtered manager"""
        return self.objects_manager()
    
    def save(self, *args, **kwargs):
        """Override save to ensure question_type is set correctly"""
        if not hasattr(self, 'question_type'):
            self.question_type = 'general'
        super().save(*args, **kwargs)
    
    @property
    def is_specialist(self):
        """Backward compatibility property"""
        return False


class SpecialistQuestionProxy(models.Model):
    """
    Proxy model to maintain backward compatibility for SpecialistQuestion
    
    This model provides the same interface as the original SpecialistQuestion
    but delegates to the unified Question model with question_type='specialist'
    """
    
    class Meta:
        proxy = True
        app_label = 'shared'
    
    @classmethod
    def get_model_class(cls):
        """Get the actual model class (Question)"""
        from shared.models import Question
        return Question
    
    @classmethod
    def objects_manager(cls):
        """Get a manager that filters for specialist questions"""
        Question = cls.get_model_class()
        return Question.objects.filter(question_type='specialist')
    
    @property
    def objects(self):
        """Property to access the filtered manager"""
        return self.objects_manager()
    
    def save(self, *args, **kwargs):
        """Override save to ensure question_type is set correctly"""
        if not hasattr(self, 'question_type'):
            self.question_type = 'specialist'
        super().save(*args, **kwargs)
    
    def mark_as_used(self):
        """Backward compatibility method"""
        self.usage_count += 1
        from django.utils import timezone
        self.last_used = timezone.now()
        self.save(update_fields=['usage_count', 'last_used'])


def get_question_model(question_type: str = 'general') -> Type[models.Model]:
    """
    Get the appropriate question model class
    
    Args:
        question_type: 'general' or 'specialist'
        
    Returns:
        Model class for the specified question type
    """
    from shared.models import Question
    return Question


def create_general_question(**kwargs) -> models.Model:
    """
    Create a general knowledge question using the unified model
    
    Args:
        **kwargs: Question field values
        
    Returns:
        Question instance with question_type='general'
    """
    from shared.models import Question
    kwargs['question_type'] = 'general'
    return Question.objects.create(**kwargs)


def create_specialist_question(subject_name: str, **kwargs) -> models.Model:
    """
    Create a specialist question using the unified model
    
    Args:
        subject_name: Name of the specialist subject
        **kwargs: Question field values
        
    Returns:
        Question instance with question_type='specialist'
    """
    from shared.models import Question, Subject
    
    # Get or create subject
    subject, _ = Subject.objects.get_or_create(
        name=subject_name,
        defaults={'description': f'Specialist questions for {subject_name}'}
    )
    
    kwargs.update({
        'question_type': 'specialist',
        'subject': subject,
        'category': subject_name
    })
    
    return Question.objects.create(**kwargs)


def get_questions_for_category(category: str, is_specialist: bool = False) -> models.QuerySet:
    """
    Get questions for a specific category
    
    Args:
        category: Category name
        is_specialist: Whether to get specialist questions
        
    Returns:
        QuerySet of Question instances
    """
    from shared.models import Question
    
    if is_specialist:
        return Question.objects.filter(
            question_type='specialist',
            subject__name=category
        )
    else:
        return Question.objects.filter(
            question_type='general',
            category=category
        )


def ensure_unified_models_populated() -> bool:
    """
    Ensure unified models have data migrated from old models
    
    Returns:
        True if unified models are populated or migration succeeded
    """
    from shared.models import Question
    
    # Check if unified model has data
    if Question.objects.exists():
        return True
    
    # Check if old models exist and have data
    if not compat_manager._old_models_available:
        return True  # No old data to migrate
    
    try:
        from game_sessions.models import MultipleChoiceQuestion
        from mastermind.models import SpecialistQuestion
        
        old_general_count = MultipleChoiceQuestion.objects.count()
        old_specialist_count = SpecialistQuestion.objects.count()
        
        if old_general_count > 0 or old_specialist_count > 0:
            logger.warning(
                f"Unified Question model is empty but old models have data: "
                f"{old_general_count} general, {old_specialist_count} specialist. "
                f"Run 'python manage.py migrate_questions' to migrate data."
            )
            return False
        
    except ImportError:
        pass
    
    return True