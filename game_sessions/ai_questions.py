"""Simple AI question generation for multiple choice questions"""

import json
import logging
from django.conf import settings
from django.utils import timezone
from .models import MultipleChoiceQuestion
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


def generate_ai_question(category="General Knowledge"):
    """Generate a single AI multiple choice question and store if unique"""
    
    if not settings.OPENAI_API_KEY:
        logger.warning("No OpenAI API key configured")
        return None
    
    try:
        import openai
        client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
        
        # Create category-specific prompts with emphasis on unusual/interesting questions
        if category == "UK Sports" or category == "Sports":
            category_prompt = """Generate a multiple choice question about UK/British sports.

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
    "category": "UK Sports"
}}"""
        else:
            category_prompt = f"""Generate a multiple choice question for the category "{category}".

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

        # Use best performing models based on testing
        models_to_try = ["gpt-4.1-mini", "gpt-4o-mini", "gpt-3.5-turbo"]
        
        for model in models_to_try:
            try:
                # Different parameter names for different models
                if model == "o3-mini":
                    response = client.chat.completions.create(
                        model=model,
                        messages=[{"role": "user", "content": category_prompt}],
                        max_completion_tokens=300
                        # o3-mini doesn't support temperature parameter
                    )
                else:
                    response = client.chat.completions.create(
                        model=model,
                        messages=[{"role": "user", "content": category_prompt}],
                        max_tokens=300,
                        temperature=0.8  # Higher temperature for more variety
                    )
                logger.info(f"Successfully used model: {model}")
                break
            except Exception as model_error:
                logger.warning(f"Model {model} failed: {model_error}")
                if model == models_to_try[-1]:  # Last model failed
                    raise model_error
                continue
        
        ai_response = response.choices[0].message.content.strip()
        logger.info(f"AI response: {ai_response}")
        
        # Parse JSON response
        try:
            question_data = json.loads(ai_response)
        except json.JSONDecodeError:
            # Try to extract JSON from response if it's wrapped in other text (common with newer models)
            import re
            # Remove markdown code blocks
            cleaned_response = re.sub(r'```json\s*|\s*```', '', ai_response, flags=re.IGNORECASE)
            cleaned_response = cleaned_response.strip()
            
            try:
                question_data = json.loads(cleaned_response)
            except json.JSONDecodeError:
                # Try to find JSON in the response
                json_match = re.search(r'\{.*\}', cleaned_response, re.DOTALL)
                if json_match:
                    try:
                        question_data = json.loads(json_match.group())
                    except json.JSONDecodeError:
                        logger.error(f"Could not parse JSON from AI response: {ai_response[:200]}...")
                        return None
                else:
                    logger.error(f"Could not find JSON in AI response: {ai_response[:200]}...")
                    return None
        
        # Validate required fields
        required_fields = ['question', 'choices', 'correct_answer', 'category']
        if not all(field in question_data for field in required_fields):
            logger.error(f"Missing required fields in AI response: {question_data}")
            return None
        
        if len(question_data['choices']) != 4:
            logger.error(f"Expected 4 choices, got {len(question_data['choices'])}")
            return None
        
        if question_data['correct_answer'] not in question_data['choices']:
            logger.error(f"Correct answer not in choices: {question_data}")
            return None
        
        # Check for duplicate using fuzzy matching
        if is_duplicate_question(question_data):
            logger.info(f"Question is duplicate, skipping: {question_data['question'][:50]}...")
            return None
        
        # Create new question
        question = MultipleChoiceQuestion.objects.create(
            question_text=question_data['question'],
            choices=question_data['choices'],
            correct_answer=question_data['correct_answer'],
            category=question_data['category'],
            is_ai_generated=True
        )
        
        logger.info(f"Created new AI question: {question.question_text[:50]}...")
        return question
        
    except Exception as e:
        logger.error(f"Error generating AI question: {e}")
        return None


def is_duplicate_question(question_data):
    """Check if question is duplicate using fuzzy matching on answer sets + correct answer"""
    
    # Create a normalized answer set for comparison
    new_choices = sorted([choice.lower().strip() for choice in question_data['choices']])
    new_correct = question_data['correct_answer'].lower().strip()
    
    # Check against existing questions
    existing_questions = MultipleChoiceQuestion.objects.all()
    
    for existing in existing_questions:
        existing_choices = sorted([choice.lower().strip() for choice in existing.choices])
        existing_correct = existing.correct_answer.lower().strip()
        
        # Check if answer sets are very similar
        choices_similarity = SequenceMatcher(None, str(new_choices), str(existing_choices)).ratio()
        correct_similarity = SequenceMatcher(None, new_correct, existing_correct).ratio()
        
        # Consider duplicate if answer sets are >80% similar AND correct answers are >90% similar
        if choices_similarity > 0.8 and correct_similarity > 0.9:
            logger.info(f"Found similar question: {choices_similarity:.2f} choices, {correct_similarity:.2f} correct")
            return True
    
    return False


def get_question_for_game(category="General Knowledge", exclude_recent_days=1, force_ai_generation=True):
    """Get a question for the game, prioritizing AI generation to grow the database"""
    
    # FIRST: Always try to generate a new AI question to grow our database
    logger.info(f"Trying to generate new AI question for {category} to grow database...")
    new_question = generate_ai_question(category)
    
    if new_question:
        # Mark as used and return the new AI question
        new_question.last_used = timezone.now()
        new_question.usage_count = 1
        new_question.save()
        logger.info(f"✅ Generated NEW AI question: {new_question.question_text[:50]}...")
        return new_question
    
    # SECOND: AI generation failed or duplicate detected, use existing questions
    logger.info(f"AI generation failed/duplicate for {category}, using existing questions...")
    
    # Try to get an existing question that hasn't been used recently
    from datetime import timedelta
    cutoff_date = timezone.now() - timedelta(days=exclude_recent_days)
    
    available_questions = MultipleChoiceQuestion.objects.filter(
        category=category
    ).exclude(
        last_used__gte=cutoff_date
    ).order_by('usage_count', 'last_used')
    
    if available_questions.exists():
        question = available_questions.first()
        # Update usage stats
        question.last_used = timezone.now()
        question.usage_count += 1
        question.save()
        logger.info(f"💾 Using existing question: {question.question_text[:50]}...")
        return question
    
    # FINAL: Fallback to any existing question if no recent ones available
    fallback_questions = MultipleChoiceQuestion.objects.filter(category=category)
    if fallback_questions.exists():
        question = fallback_questions.order_by('usage_count').first()
        question.last_used = timezone.now()
        question.usage_count += 1
        question.save()
        logger.info(f"💾 Using fallback question: {question.question_text[:50]}...")
        return question
    
    return None


def generate_specialist_questions(specialist_subject: str, target_count: int = 20) -> int:
    """Generate multiple specialist questions for a specific subject"""
    
    if not settings.OPENAI_API_KEY:
        logger.warning("No OpenAI API key configured for specialist question generation")
        return 0
    
    if not specialist_subject or not specialist_subject.strip():
        logger.error("No specialist subject provided")
        return 0
    
    specialist_subject = specialist_subject.strip()
    generated_count = 0
    
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
    
    try:
        import openai
        client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
        
        # Create specialist subject prompt for high-quality questions
        specialist_prompt = f"""Generate {questions_needed} different multiple choice questions specifically about "{specialist_subject}".

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
- "category": "{specialist_subject}"

Example format:
[
  {{
    "question": "Your specialist question here?",
    "choices": ["Option A", "Option B", "Option C", "Option D"],
    "correct_answer": "Option B",
    "category": "{specialist_subject}"
  }}
]

Generate {questions_needed} questions about {specialist_subject}:"""

        # Use best performing models
        models_to_try = ["gpt-4o-mini", "gpt-3.5-turbo"]
        
        for model in models_to_try:
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": specialist_prompt}],
                    max_tokens=2000,  # More tokens for multiple questions
                    temperature=0.8
                )
                logger.info(f"Successfully used model: {model} for specialist questions")
                break
            except Exception as model_error:
                logger.warning(f"Model {model} failed: {model_error}")
                if model == models_to_try[-1]:
                    raise model_error
                continue
        
        ai_response = response.choices[0].message.content.strip()
        logger.info(f"AI response received for {specialist_subject}: {len(ai_response)} characters")
        
        # Parse JSON response
        try:
            questions_data = json.loads(ai_response)
        except json.JSONDecodeError:
            # Try to extract JSON from response
            import re
            cleaned_response = re.sub(r'```json\s*|\s*```', '', ai_response, flags=re.IGNORECASE)
            cleaned_response = cleaned_response.strip()
            
            try:
                questions_data = json.loads(cleaned_response)
            except json.JSONDecodeError:
                json_match = re.search(r'\[.*\]', cleaned_response, re.DOTALL)
                if json_match:
                    try:
                        questions_data = json.loads(json_match.group())
                    except json.JSONDecodeError:
                        logger.error(f"Could not parse JSON from specialist AI response")
                        return generated_count
                else:
                    logger.error(f"Could not find JSON array in specialist AI response")
                    return generated_count
        
        if not isinstance(questions_data, list):
            logger.error(f"Expected list of questions, got {type(questions_data)}")
            return generated_count
        
        # Process each question
        for question_data in questions_data:
            if not isinstance(question_data, dict):
                continue
                
            # Validate required fields
            required_fields = ['question', 'choices', 'correct_answer', 'category']
            if not all(field in question_data for field in required_fields):
                logger.warning(f"Missing required fields in specialist question: {question_data}")
                continue
            
            if len(question_data['choices']) != 4:
                logger.warning(f"Expected 4 choices, got {len(question_data['choices'])}")
                continue
            
            if question_data['correct_answer'] not in question_data['choices']:
                logger.warning(f"Correct answer not in choices: {question_data}")
                continue
            
            # Check for duplicate using existing function
            if is_duplicate_question(question_data):
                logger.info(f"Specialist question is duplicate, skipping: {question_data['question'][:50]}...")
                continue
            
            # Create new specialist question
            try:
                question = MultipleChoiceQuestion.objects.create(
                    question_text=question_data['question'],
                    choices=question_data['choices'],
                    correct_answer=question_data['correct_answer'],
                    category=specialist_subject,  # Use consistent category
                    is_ai_generated=True,
                    is_specialist=True  # Mark as specialist question
                )
                generated_count += 1
                logger.info(f"Created specialist question #{generated_count}: {question.question_text[:50]}...")
                
            except Exception as e:
                logger.error(f"Error creating specialist question: {e}")
                continue
        
        logger.info(f"Generated {generated_count} new specialist questions for {specialist_subject}")
        return existing_count + generated_count
        
    except Exception as e:
        logger.error(f"Error generating specialist questions for {specialist_subject}: {e}")
        return generated_count


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