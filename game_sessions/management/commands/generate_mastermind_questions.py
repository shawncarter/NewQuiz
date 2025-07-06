"""
Management command to pre-generate specialist questions for Mastermind rounds
"""

from django.core.management.base import BaseCommand, CommandError
from game_sessions.ai_questions import generate_specialist_questions
from game_sessions.models import MultipleChoiceQuestion


class Command(BaseCommand):
    help = 'Generate specialist questions for Mastermind rounds'

    def add_arguments(self, parser):
        parser.add_argument(
            'subjects',
            nargs='*',
            type=str,
            help='Specialist subjects to generate questions for (e.g. "Football" "Science" "History")'
        )
        parser.add_argument(
            '--count',
            type=int,
            default=20,
            help='Number of questions to generate per subject (default: 20)'
        )
        parser.add_argument(
            '--list-existing',
            action='store_true',
            help='List existing specialist subjects in the database'
        )

    def handle(self, *args, **options):
        if options['list_existing']:
            self.list_existing_subjects()
            return

        subjects = options['subjects']
        count = options['count']

        if not subjects:
            # Default subjects for testing
            subjects = [
                "Football", "Science", "History", "Movies", "Music", 
                "Geography", "Literature", "Technology", "Art", "Politics"
            ]
            self.stdout.write(
                self.style.WARNING(
                    f'No subjects specified. Generating questions for default subjects: {", ".join(subjects)}'
                )
            )

        total_generated = 0
        
        for subject in subjects:
            self.stdout.write(f'\n📚 Generating questions for "{subject}"...')
            
            try:
                generated_count = generate_specialist_questions(subject, target_count=count)
                total_generated += generated_count
                
                if generated_count >= count:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'✅ Successfully ensured {generated_count} questions for "{subject}"'
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f'⚠️  Only {generated_count} questions available for "{subject}" (target: {count})'
                        )
                    )
                    
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f'❌ Error generating questions for "{subject}": {e}'
                    )
                )

        self.stdout.write(
            self.style.SUCCESS(
                f'\n🎯 Summary: {total_generated} total specialist questions available'
            )
        )

    def list_existing_subjects(self):
        """List all existing specialist subjects in the database"""
        specialist_subjects = MultipleChoiceQuestion.objects.filter(
            is_specialist=True
        ).values_list('category', flat=True).distinct().order_by('category')
        
        if specialist_subjects:
            self.stdout.write(self.style.SUCCESS('\n📋 Existing specialist subjects:'))
            for subject in specialist_subjects:
                count = MultipleChoiceQuestion.objects.filter(
                    category=subject, 
                    is_specialist=True
                ).count()
                self.stdout.write(f'  • {subject}: {count} questions')
        else:
            self.stdout.write(self.style.WARNING('No specialist questions found in database'))