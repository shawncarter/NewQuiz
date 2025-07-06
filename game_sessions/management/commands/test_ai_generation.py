from django.core.management.base import BaseCommand
from game_sessions.ai_questions import generate_ai_question

class Command(BaseCommand):
    help = 'Test AI question generation (requires OPENAI_API_KEY in environment)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--category',
            type=str,
            default='General Knowledge',
            help='Category for the question (default: General Knowledge)',
        )

    def handle(self, *args, **options):
        category = options['category']
        
        self.stdout.write(f'Attempting to generate AI question for category: {category}')
        
        question = generate_ai_question(category)
        
        if question:
            self.stdout.write(self.style.SUCCESS('✅ Successfully generated question:'))
            self.stdout.write(f'Question: {question.question_text}')
            self.stdout.write(f'Choices: {question.choices}')
            self.stdout.write(f'Correct Answer: {question.correct_answer}')
            self.stdout.write(f'Category: {question.category}')
        else:
            self.stdout.write(self.style.WARNING('❌ Failed to generate question (check API key and logs)'))