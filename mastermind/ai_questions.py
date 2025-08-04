"""
AI Question Generation for Mastermind Specialist Questions

This module handles generation of specialist questions using the new mastermind models.
"""

import logging
from .models import Subject, SpecialistQuestion
from shared.services import get_specialist_service

logger = logging.getLogger('mastermind')


def generate_specialist_questions(specialist_subject: str, target_count: int = 20) -> int:
    """Generate multiple specialist questions for a specific subject using new mastermind models"""
    service = get_specialist_service()
    
    if not specialist_subject or not specialist_subject.strip():
        logger.error("No specialist subject provided")
        return 0
    
    specialist_subject = specialist_subject.strip()
    
    # Get or create the subject
    subject, created = Subject.objects.get_or_create(
        name=specialist_subject,
        defaults={'description': f'Specialist questions for {specialist_subject}'}
    )
    
    if created:
        logger.info(f"Created new subject: {specialist_subject}")
    
    # Check how many questions we already have for this subject
    existing_count = SpecialistQuestion.objects.filter(subject=subject).count()
    
    if existing_count >= target_count:
        logger.info(f"Already have {existing_count} specialist questions for {specialist_subject}")
        return existing_count
    
    questions_needed = target_count - existing_count
    logger.info(f"Generating {questions_needed} specialist questions for {specialist_subject}")
    
    generated_count = service.generate_bulk_questions(
        specialist_subject, 
        questions_needed,
        subject_name=specialist_subject
    )
    
    final_count = existing_count + generated_count
    logger.info(f"Generated {generated_count} new questions for {specialist_subject}. Total: {final_count}")
    
    return final_count


def get_specialist_question(specialist_subject: str, exclude_question_ids: list = None) -> SpecialistQuestion:
    """Get a specialist question for the given subject"""
    service = get_specialist_service()
    return service.get_specialist_question(specialist_subject, exclude_question_ids)


def ensure_specialist_questions(specialist_subject: str, minimum_count: int = 25) -> bool:
    """Ensure we have enough specialist questions for this subject"""
    service = get_specialist_service()
    return service.ensure_specialist_questions(specialist_subject, minimum_count)