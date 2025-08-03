"""
Management command to migrate existing specialist questions from game_sessions to mastermind app
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from game_sessions.models import MultipleChoiceQuestion
from mastermind.models import Subject, SpecialistQuestion


class Command(BaseCommand):
    help = 'Migrate existing specialist questions from game_sessions to mastermind app'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be migrated without actually doing it'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(self.style.WARNING('🔍 DRY RUN MODE - No changes will be made'))
        
        # Get all specialist questions from the old system
        old_questions = MultipleChoiceQuestion.objects.filter(is_specialist=True)
        
        if not old_questions.exists():
            self.stdout.write(self.style.WARNING('No specialist questions found in old system'))
            return
        
        self.stdout.write(f'Found {old_questions.count()} specialist questions to migrate')
        
        # Group by category (which becomes subject)
        categories = old_questions.values_list('category', flat=True).distinct()
        
        migrated_count = 0
        skipped_count = 0
        
        for category in categories:
            self.stdout.write(f'\n📚 Processing category: {category}')
            
            # Get or create subject
            if not dry_run:
                subject, created = Subject.objects.get_or_create(
                    name=category,
                    defaults={'description': f'Migrated from game_sessions: {category}'}
                )
                if created:
                    self.stdout.write(f'  ✨ Created new subject: {category}')
                else:
                    self.stdout.write(f'  📖 Using existing subject: {category}')
            else:
                try:
                    subject = Subject.objects.get(name=category)
                    self.stdout.write(f'  📖 Subject exists: {category}')
                except Subject.DoesNotExist:
                    self.stdout.write(f'  ✨ Would create subject: {category}')
                    subject = None
            
            # Get questions for this category
            category_questions = old_questions.filter(category=category)
            
            for old_question in category_questions:
                try:
                    # Check if question already exists in new system
                    if subject and SpecialistQuestion.objects.filter(
                        subject=subject,
                        question_text=old_question.question_text
                    ).exists():
                        self.stdout.write(f'  ⏭️  Skipping duplicate: {old_question.question_text[:50]}...')
                        skipped_count += 1
                        continue
                    
                    if not dry_run:
                        # Create new specialist question
                        SpecialistQuestion.objects.create(
                            subject=subject,
                            question_text=old_question.question_text,
                            choices=old_question.choices,
                            correct_answer=old_question.correct_answer,
                            difficulty='medium',  # Default difficulty
                            usage_count=old_question.usage_count,
                            last_used=old_question.last_used,
                            is_ai_generated=old_question.is_ai_generated
                        )
                        self.stdout.write(f'  ✅ Migrated: {old_question.question_text[:50]}...')
                    else:
                        self.stdout.write(f'  📝 Would migrate: {old_question.question_text[:50]}...')
                    
                    migrated_count += 1
                    
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f'  ❌ Error migrating question: {e}')
                    )
        
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f'\n🎯 DRY RUN Summary: Would migrate {migrated_count} questions, skip {skipped_count} duplicates'
                )
            )
            self.stdout.write('Run without --dry-run to perform actual migration')
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'\n🎯 Migration Complete: {migrated_count} questions migrated, {skipped_count} skipped'
                )
            )
            
            # Show final counts
            total_subjects = Subject.objects.count()
            total_questions = SpecialistQuestion.objects.count()
            self.stdout.write(f'📊 Total subjects: {total_subjects}')
            self.stdout.write(f'📊 Total specialist questions: {total_questions}')