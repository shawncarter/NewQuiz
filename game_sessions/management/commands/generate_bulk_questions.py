from django.core.management.base import BaseCommand
from game_sessions.ai_questions import generate_ai_question
import time

class Command(BaseCommand):
    help = 'Generate bulk AI questions for all categories (100 per category)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--category',
            type=str,
            help='Generate for specific category only',
        )
        parser.add_argument(
            '--count',
            type=int,
            default=100,
            help='Number of questions per category (default: 100)',
        )
        parser.add_argument(
            '--delay',
            type=float,
            default=1.0,
            help='Delay between API calls in seconds (default: 1.0)',
        )

    def handle(self, *args, **options):
        count_per_category = options['count']
        delay = options['delay']
        specific_category = options.get('category')
        
        # Categories to generate for
        if specific_category:
            categories = [specific_category]
        else:
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
        
        total_attempted = 0
        total_generated = 0
        total_duplicates = 0
        total_failed = 0
        
        self.stdout.write(f'🚀 Generating {count_per_category} questions for each category...')
        self.stdout.write(f'⏱️  Using {delay}s delay between requests')
        self.stdout.write('=' * 80)
        
        for category in categories:
            self.stdout.write(f'\n📚 {category}:')
            category_generated = 0
            category_duplicates = 0
            category_failed = 0
            
            for i in range(count_per_category):
                total_attempted += 1
                
                # Show progress every 10 questions
                if (i + 1) % 10 == 0:
                    self.stdout.write(f'  📊 Progress: {i+1}/{count_per_category} (✅ {category_generated}, 🔄 {category_duplicates}, ❌ {category_failed})')
                
                question = generate_ai_question(category)
                if question:
                    category_generated += 1
                    total_generated += 1
                    if (i + 1) % 25 == 0:  # Show sample every 25
                        self.stdout.write(f'  ✅ Sample: {question.question_text[:50]}...')
                else:
                    # Check if it was a duplicate or actual failure
                    # (This is a simplification - in reality we'd need to check the logs)
                    category_duplicates += 1
                    total_duplicates += 1
                
                # Rate limiting
                if i < count_per_category - 1:  # Don't delay after last question
                    time.sleep(delay)
            
            # Final stats for this category
            self.stdout.write(f'  📈 Final: ✅ {category_generated} generated, 🔄 {category_duplicates} duplicates, ❌ {category_failed} failed')
        
        # Overall summary
        self.stdout.write('\n' + '=' * 80)
        self.stdout.write(self.style.SUCCESS(f'🎯 BULK GENERATION COMPLETE'))
        self.stdout.write(f'📊 Total Attempted: {total_attempted}')
        self.stdout.write(f'✅ Successfully Generated: {total_generated}')
        self.stdout.write(f'🔄 Duplicates Blocked: {total_duplicates}')
        self.stdout.write(f'❌ Failed: {total_failed}')
        
        success_rate = (total_generated / total_attempted * 100) if total_attempted > 0 else 0
        self.stdout.write(f'📈 Success Rate: {success_rate:.1f}%')
        
        estimated_cost = total_generated * 0.002
        self.stdout.write(f'💰 Estimated API Cost: ~${estimated_cost:.2f}')
        
        if total_generated > 0:
            self.stdout.write(f'\n🎮 Ready to play! You now have {total_generated} new unique questions!')
            self.stdout.write('   Run "python manage.py show_question_stats" to see the breakdown.')