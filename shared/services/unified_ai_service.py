"""
Unified AI Question Service

Single service class that handles both general and specialist question generation
using the unified Question model. This replaces the separate MultipleChoiceAIService
and SpecialistAIService classes.
"""

import logging
from typing import Dict, Any, Type, Optional
from django.db import models
from django.utils import timezone
from datetime import timedelta

from .ai_question_service import AIQuestionService

logger = logging.getLogger(__name__)


class UnifiedAIService(AIQuestionService):
    """Unified AI service for generating both general and specialist questions"""
    
    def get_question_model(self) -> Type[models.Model]:
        """Return the unified Question model"""
        from shared.models import Question
        return Question
    
    def create_question_prompt(self, category: str = "General Knowledge", 
                              question_type: str = "general", **kwargs) -> str:
        """Create prompt for single question generation"""
        
        if question_type == "specialist":
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
        
        elif category == "UK Sports" or category == "Sports":
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
    
    def create_bulk_questions_prompt(self, category: str, count: int, 
                                   question_type: str = "general", **kwargs) -> str:
        """Create prompt for bulk question generation"""
        
        if question_type == "specialist":
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
    
    def create_question_instance(self, question_data: Dict[str, Any], 
                               question_type: str = "general", **kwargs) -> models.Model:
        """Create a Question instance with the specified type"""
        from shared.models import Question, Subject
        
        QuestionModel = self.get_question_model()
        
        # Prepare question data
        create_kwargs = {
            'question_text': question_data['question'],
            'choices': question_data['choices'],
            'correct_answer': question_data['correct_answer'],
            'question_type': question_type,
            'difficulty': kwargs.get('difficulty', 'medium'),
            'is_ai_generated': True,
        }
        
        if question_type == 'specialist':
            # Get or create subject for specialist questions
            subject_name = question_data.get('category', kwargs.get('subject_name', 'Unknown'))
            subject, created = Subject.objects.get_or_create(
                name=subject_name,
                defaults={'description': f'Specialist questions for {subject_name}'}
            )
            
            if created:
                logger.info(f"Created new subject: {subject_name}")
            
            create_kwargs.update({
                'subject': subject,
                'category': subject_name,
            })
        else:
            # General questions
            create_kwargs.update({
                'category': question_data.get('category', 'General Knowledge'),
                'subject': None,
            })
        
        return QuestionModel.objects.create(**create_kwargs)
    
    def get_existing_questions_for_duplicate_check(self, category: str, 
                                                 question_type: str = "general", 
                                                 **kwargs) -> models.QuerySet:
        """Get existing questions for duplicate checking"""
        QuestionModel = self.get_question_model()
        
        if question_type == 'specialist':
            # For specialist questions, check within the same subject
            return QuestionModel.objects.filter(
                question_type='specialist',
                subject__name=category
            )
        else:
            # For general questions, check within the same category
            return QuestionModel.objects.filter(
                question_type='general',
                category=category
            )
    
    def get_question_for_game(self, category: str = "General Knowledge", 
                             question_type: str = "general",
                             exclude_recent_days: int = 1, 
                             force_ai_generation: bool = True,
                             **kwargs) -> Optional[models.Model]:
        """
        Get a question for the game, prioritizing AI generation to grow the database.
        
        Args:
            category: Question category or subject name
            question_type: 'general' or 'specialist'
            exclude_recent_days: Days to exclude recently used questions
            force_ai_generation: Whether to try AI generation first
            **kwargs: Additional arguments
            
        Returns:
            Question instance or None
        """
        QuestionModel = self.get_question_model()
        
        # FIRST: Try to generate a new AI question if requested
        if force_ai_generation:
            logger.info(f"Trying to generate new AI {question_type} question for {category} to grow database...")
            new_question = self.generate_single_question(
                category, 
                question_type=question_type, 
                **kwargs
            )
            
            if new_question:
                # Mark as used and return the new AI question
                new_question.mark_as_used()
                logger.info(f"✅ Generated NEW AI {question_type} question: {new_question.question_text[:50]}...")
                return new_question
        
        # SECOND: Use existing questions
        logger.info(f"Using existing {question_type} questions for {category}...")
        
        cutoff_date = timezone.now() - timedelta(days=exclude_recent_days)
        
        # Build query for existing questions
        if question_type == 'specialist':
            query_filters = {
                'question_type': 'specialist',
                'subject__name': category
            }
        else:
            query_filters = {
                'question_type': 'general',
                'category': category
            }
        
        available_questions = QuestionModel.objects.filter(
            **query_filters
        ).exclude(
            last_used__gte=cutoff_date
        ).order_by('usage_count', 'last_used')
        
        if available_questions.exists():
            question = available_questions.first()
            question.mark_as_used()
            logger.info(f"💾 Using existing {question_type} question: {question.question_text[:50]}...")
            return question
        
        # FINAL: Fallback to any existing question
        fallback_questions = QuestionModel.objects.filter(**query_filters)
        if fallback_questions.exists():
            question = fallback_questions.order_by('usage_count').first()
            question.mark_as_used()
            logger.info(f"💾 Using fallback {question_type} question: {question.question_text[:50]}...")
            return question
        
        return None
    
    def get_specialist_question(self, specialist_subject: str, 
                               exclude_question_ids: list = None) -> Optional[models.Model]:
        """
        Get a specialist question for the given subject.
        
        Args:
            specialist_subject: The specialist subject name
            exclude_question_ids: List of question IDs to exclude
            
        Returns:
            Question instance or None
        """
        if exclude_question_ids is None:
            exclude_question_ids = []
        
        QuestionModel = self.get_question_model()
        
        questions = QuestionModel.objects.filter(
            question_type='specialist',
            subject__name=specialist_subject,
            subject__is_active=True
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
        from shared.models import Subject
        
        try:
            QuestionModel = self.get_question_model()
            current_count = QuestionModel.objects.filter(
                question_type='specialist',
                subject__name=specialist_subject,
                subject__is_active=True
            ).count()
            
            if current_count < minimum_count:
                logger.info(f"Need more questions for {specialist_subject}: {current_count}/{minimum_count}")
                questions_needed = minimum_count - current_count
                generated = self.generate_bulk_questions(
                    specialist_subject, 
                    questions_needed, 
                    question_type='specialist'
                )
                return generated > 0
            else:
                logger.info(f"Sufficient questions for {specialist_subject}: {current_count}")
                return True
                
        except Exception as e:
            logger.error(f"Error ensuring specialist questions for {specialist_subject}: {str(e)}")
            logger.info(f"Subject '{specialist_subject}' not found, creating and generating questions")
            generated = self.generate_bulk_questions(
                specialist_subject, 
                minimum_count, 
                question_type='specialist'
            )
            return generated > 0
    
    def generate_single_question(self, category: str, question_type: str = "general", **kwargs) -> Optional[models.Model]:
        """Generate a single question with the specified type"""
        prompt = self.create_question_prompt(category, question_type=question_type, **kwargs)
        
        try:
            response = self.call_openai_api(prompt)
            question_data = self.parse_api_response(response)
            
            if self.is_duplicate_question(question_data, category, question_type=question_type, **kwargs):
                logger.warning(f"Generated duplicate {question_type} question for {category}, skipping")
                return None
            
            return self.create_question_instance(question_data, question_type=question_type, **kwargs)
            
        except Exception as e:
            logger.error(f"Failed to generate {question_type} question for {category}: {str(e)}")
            return None
    
    def generate_bulk_questions(self, category: str, count: int, 
                              question_type: str = "general", **kwargs) -> int:
        """Generate multiple questions with the specified type"""
        prompt = self.create_bulk_questions_prompt(category, count, question_type=question_type, **kwargs)
        
        try:
            response = self.call_openai_api(prompt)
            questions_data = self.parse_bulk_api_response(response)
            
            created_count = 0
            for question_data in questions_data:
                if not self.is_duplicate_question(question_data, category, question_type=question_type, **kwargs):
                    try:
                        self.create_question_instance(question_data, question_type=question_type, **kwargs)
                        created_count += 1
                    except Exception as e:
                        logger.error(f"Failed to create {question_type} question: {str(e)}")
                else:
                    logger.debug(f"Skipping duplicate {question_type} question for {category}")
            
            logger.info(f"Created {created_count}/{len(questions_data)} {question_type} questions for {category}")
            return created_count
            
        except Exception as e:
            logger.error(f"Failed to generate {question_type} questions for {category}: {str(e)}")
            return 0
    
    def is_duplicate_question(self, question_data: Dict[str, Any], category: str, 
                            question_type: str = "general", **kwargs) -> bool:
        """Check if a question is a duplicate with type-specific logic"""
        existing_questions = self.get_existing_questions_for_duplicate_check(
            category, 
            question_type=question_type, 
            **kwargs
        )
        
        question_text = question_data.get('question', '').strip().lower()
        
        for existing in existing_questions:
            if self.calculate_similarity(question_text, existing.question_text.strip().lower()) > 0.8:
                return True
        
        return False