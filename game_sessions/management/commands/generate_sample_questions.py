from django.core.management.base import BaseCommand
from game_sessions.ai_questions import generate_ai_question

class Command(BaseCommand):
    help = 'Generate sample AI questions for popular quiz categories'

    def add_arguments(self, parser):
        parser.add_argument(
            '--count',
            type=int,
            default=2,
            help='Number of questions per category (default: 2)',
        )

    def handle(self, *args, **options):
        count_per_category = options['count']
        
        # Popular quiz categories
        categories = [
            "Science",
            "History", 
            "Geography",
            "UK Sports",
            "Entertainment",
            "Technology",
            "Literature",
            "Art",
            "Music",
            "Food & Cooking"
        ]
        
        total_generated = 0
        total_failed = 0
        
        self.stdout.write(f'Generating {count_per_category} questions for each of {len(categories)} categories...')
        self.stdout.write('=' * 60)
        
        for category in categories:
            self.stdout.write(f'\n📚 {category}:')
            category_success = 0
            
            for i in range(count_per_category):
                question = generate_ai_question(category)
                if question:
                    category_success += 1
                    total_generated += 1
                    self.stdout.write(f'  ✅ {question.question_text[:50]}...')
                else:
                    total_failed += 1
                    self.stdout.write(f'  ❌ Failed to generate question {i+1}')
            
            self.stdout.write(f'  📊 Generated {category_success}/{count_per_category} questions')
        
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.SUCCESS(f'✅ Total generated: {total_generated}'))
        if total_failed > 0:
            self.stdout.write(self.style.WARNING(f'❌ Total failed: {total_failed}'))
        
        self.stdout.write(f'\n💰 Estimated API cost: ~${(total_generated * 0.002):.2f}')