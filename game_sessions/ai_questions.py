"""Simple AI question generation for multiple choice questions"""

import logging
from django.utils import timezone
from .models import MultipleChoiceQuestion
from shared.services import get_multiple_choice_service

logger = logging.getLogger(__name__)


def generate_ai_question(category="General Knowledge"):
    """Generate a single AI multiple choice question and store if unique"""
    service = get_multiple_choice_service()
    return service.generate_single_question(category)


# is_duplicate_question function moved to shared AIQuestionService base class


def get_question_for_game(category="General Knowledge", exclude_recent_days=1, force_ai_generation=True):
    """Get a question for the game, prioritizing AI generation to grow the database"""
    service = get_multiple_choice_service()
    return service.get_question_for_game(
        category=category,
        exclude_recent_days=exclude_recent_days,
        force_ai_generation=force_ai_generation
    )


def get_question_for_game_with_exclusions(category="General Knowledge", exclude_question_ids=None, exclude_recent_days=1, force_ai_generation=True):
    """Get a question for the game, excluding specific questions already used in this game session"""
    service = get_multiple_choice_service()

    # Get a question using the service's method
    question = service.get_question_for_game(
        category=category,
        exclude_recent_days=exclude_recent_days,
        force_ai_generation=force_ai_generation
    )

    # If we got a question but it's in the exclusion list, try to find an alternative
    exclude_question_ids = exclude_question_ids or []
    if question and question.id in exclude_question_ids:
        logger.info(f"Question {question.question_text[:50]}... already used in this game, finding alternative")

        # Try to find an unused question from the database
        from .models import MultipleChoiceQuestion
        from datetime import timedelta
        from django.utils import timezone

        cutoff_date = timezone.now() - timedelta(days=exclude_recent_days)

        alternative_questions = MultipleChoiceQuestion.objects.filter(
            category=category
        ).exclude(
            id__in=exclude_question_ids  # Exclude questions used in this game
        ).exclude(
            last_used__gte=cutoff_date  # Exclude recently used questions globally
        ).order_by('usage_count', 'last_used')

        if alternative_questions.exists():
            question = alternative_questions.first()
            # Update usage stats
            question.last_used = timezone.now()
            question.usage_count += 1
            question.save()
            logger.info(f"Found alternative unused question: {question.question_text[:50]}...")
        else:
            # If no alternatives, try any question not used in this game (ignore global usage)
            fallback_questions = MultipleChoiceQuestion.objects.filter(
                category=category
            ).exclude(
                id__in=exclude_question_ids
            ).order_by('usage_count')

            if fallback_questions.exists():
                question = fallback_questions.first()
                question.last_used = timezone.now()
                question.usage_count += 1
                question.save()
                logger.info(f"Using fallback question not used in this game: {question.question_text[:50]}...")
            else:
                logger.warning(f"No unused questions available for category {category} in this game session")

    return question


def generate_specialist_questions(specialist_subject: str, target_count: int = 20) -> int:
    """Generate multiple specialist questions for a specific subject"""
    service = get_multiple_choice_service()
    
    # Check how many questions we already have for this subject
    existing_count = MultipleChoiceQuestion.objects.filter(
        category=specialist_subject,
        is_specialist=True
    ).count()
    
    if existing_count >= target_count:
        logger.info(f"Already have {existing_count} specialist questions for {specialist_subject}")
        return existing_count
    
    questions_needed = target_count - existing_count
    logger.info(f"Generating {questions_needed} specialist questions for {specialist_subject}")
    
    generated_count = service.generate_bulk_questions(
        specialist_subject, 
        questions_needed, 
        is_specialist=True
    )
    
    return existing_count + generated_count


def get_specialist_question(specialist_subject: str, exclude_question_ids: list = None) -> 'MultipleChoiceQuestion':
    """Get a specialist question for the given subject"""
    if not specialist_subject:
        return None
    
    exclude_question_ids = exclude_question_ids or []
    
    # Get available specialist questions for this subject
    available_questions = MultipleChoiceQuestion.objects.filter(
        category=specialist_subject,
        is_specialist=True
    ).exclude(
        id__in=exclude_question_ids
    ).order_by('usage_count', 'last_used')
    
    if available_questions.exists():
        question = available_questions.first()
        # Update usage stats
        question.last_used = timezone.now()
        question.usage_count += 1
        question.save()
        logger.info(f"Using specialist question: {question.question_text[:50]}...")
        return question
    
    logger.warning(f"No specialist questions available for {specialist_subject}")
    return None