from django.core.management.base import BaseCommand
from game_sessions.models import MultipleChoiceQuestion
from collections import defaultdict

class Command(BaseCommand):
    help = 'Show statistics about questions in the database'

    def handle(self, *args, **options):
        total = MultipleChoiceQuestion.objects.count()
        ai_generated = MultipleChoiceQuestion.objects.filter(is_ai_generated=True).count()
        db_questions = total - ai_generated
        
        self.stdout.write(f'📊 Question Database Statistics')
        self.stdout.write('=' * 50)
        self.stdout.write(f'Total Questions: {total}')
        self.stdout.write(f'🤖 AI Generated: {ai_generated}')
        self.stdout.write(f'💾 Database/Legacy: {db_questions}')
        
        # Show breakdown by category
        self.stdout.write(f'\n📚 Questions by Category:')
        category_stats = defaultdict(lambda: {'total': 0, 'ai': 0, 'db': 0})
        
        for q in MultipleChoiceQuestion.objects.all():
            category_stats[q.category]['total'] += 1
            if q.is_ai_generated:
                category_stats[q.category]['ai'] += 1
            else:
                category_stats[q.category]['db'] += 1
        
        for category, stats in sorted(category_stats.items()):
            self.stdout.write(f"  {category}: {stats['total']} total (🤖 {stats['ai']}, 💾 {stats['db']})")
        
        # Show recent AI questions
        recent_ai = MultipleChoiceQuestion.objects.filter(is_ai_generated=True).order_by('-created_at')[:5]
        if recent_ai:
            self.stdout.write(f'\n🆕 Recent AI Questions:')
            for q in recent_ai:
                self.stdout.write(f"  • {q.category}: {q.question_text[:50]}...")
        
        self.stdout.write(f'\n✅ Ready for quiz games!')
        self.stdout.write(f'   - Multiple choice games will use these questions')
        self.stdout.write(f'   - AI questions show 🤖 badge in GM screen')
        self.stdout.write(f'   - Database questions show 💾 badge in GM screen')
        self.stdout.write(f'   - Duplicate detection prevents repeated questions')