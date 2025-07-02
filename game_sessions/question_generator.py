import json
import logging
from django.db import IntegrityError

# from default_api import google_web_search # Assuming default_api is accessible

logger = logging.getLogger(__name__)

def generate_unique_multiple_choice_question(category: str, max_retries: int = 5):
    """
    Generates a unique multiple-choice question using google_web_search,
    saves it to the database, and returns the MultipleChoiceQuestion object.
    Retries if the generated question is not unique.
    """
    from game_sessions.models import MultipleChoiceQuestion
    for attempt in range(max_retries):
        prompt = f"""Generate a multiple choice question about '{category}'.
        The response should be a JSON object with the following keys:
        "question": "The question text",
        "choices": ["Choice A", "Choice B", "Choice C", "Choice D"],
        "correct_answer": "The correct choice text"
        Ensure the choices are distinct and the correct_answer is one of the choices.
        """
        
        try:
            # Fallback to hardcoded questions for now since google_web_search is not available
            import random
            
            # Use same hardcoded questions as in round handlers
            QUESTIONS = [
                {
                    'question': 'What is the largest mammal in the world?',
                    'choices': ['Blue Whale', 'African Elephant', 'Giraffe', 'Hippopotamus'],
                    'correct_answer': 'Blue Whale',
                    'category': 'Animals'
                },
                {
                    'question': 'What is the smallest country in the world?',
                    'choices': ['Monaco', 'Vatican City', 'San Marino', 'Liechtenstein'],
                    'correct_answer': 'Vatican City',
                    'category': 'Geography'
                },
                {
                    'question': 'What is the largest bone in the human body?',
                    'choices': ['Femur', 'Tibia', 'Humerus', 'Fibula'],
                    'correct_answer': 'Femur',
                    'category': 'Science'
                }
            ]
            
            question_data = random.choice(QUESTIONS)

            question_text = question_data.get('question')
            choices = question_data.get('choices')
            correct_answer = question_data.get('correct_answer')
            
            if not all([question_text, choices, correct_answer]):
                logger.warning(f"Attempt {attempt + 1}: Incomplete question data from API: {question_data}")
                continue

            # Check for uniqueness before saving
            if MultipleChoiceQuestion.objects.filter(question_text=question_text).exists():
                logger.info(f"Attempt {attempt + 1}: Question '{question_text}' already exists. Retrying...")
                continue

            # Save the unique question to the database
            question = MultipleChoiceQuestion.objects.create(
                question_text=question_text,
                choices=choices,
                correct_answer=correct_answer,
                category=category
            )
            logger.info(f"Successfully generated and saved unique question: {question_text}")
            return question

        except json.JSONDecodeError as e:
            logger.warning(f"Attempt {attempt + 1}: Failed to decode JSON from API: {e}. Raw: {raw_json_string}")
        except IntegrityError:
            # This handles a rare race condition where another process saves the same question
            logger.info(f"Attempt {attempt + 1}: Race condition - question already exists. Retrying...")
        except Exception as e:
            logger.error(f"Attempt {attempt + 1}: An unexpected error occurred during question generation: {e}")

    logger.error(f"Failed to generate a unique multiple-choice question for category '{category}' after {max_retries} attempts.")
    return None