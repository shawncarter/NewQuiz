"""
Management command to migrate existing MultipleChoiceQuestion and SpecialistQuestion
data to the new unified Question model.

This command performs the data migration in phases:
1. Copy Subject data from mastermind.models to shared.models
2. Migrate MultipleChoiceQuestion records to Question (general type)
3. Migrate SpecialistQuestion records to Question (specialist type)
4. Verify data integrity and relationships

Usage:
    python manage.py migrate_questions [--dry-run] [--force]
"""

import logging
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.conf import settings

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Migrate MultipleChoiceQuestion and SpecialistQuestion to unified Question model'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be migrated without making changes',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force migration even if unified model already has data',
        )
        parser.add_argument(
            '--verify-only',
            action='store_true',
            help='Only verify data integrity, do not migrate',
        )
    
    def handle(self, *args, **options):
        self.dry_run = options['dry_run']
        self.force = options['force']
        self.verify_only = options['verify_only']
        
        self.stdout.write(self.style.SUCCESS('Question Model Migration Tool'))
        self.stdout.write('=' * 50)
        
        if self.verify_only:
            self.verify_migration()
            return
        
        try:
            # Import models
            self.load_models()
            
            # Pre-migration checks
            self.pre_migration_checks()
            
            if self.dry_run:
                self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
                self.stdout.write('')
            
            # Perform migration in transaction
            with transaction.atomic():
                # Phase 1: Migrate subjects
                subjects_migrated = self.migrate_subjects()
                
                # Phase 2: Migrate general questions
                general_migrated = self.migrate_general_questions()
                
                # Phase 3: Migrate specialist questions
                specialist_migrated = self.migrate_specialist_questions()
                
                # Phase 4: Verify relationships
                self.verify_relationships()
                
                if self.dry_run:
                    self.stdout.write(self.style.WARNING('Rolling back transaction (dry run)'))
                    raise transaction.TransactionManagementError("Dry run rollback")
            
            # Summary
            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS('Migration completed successfully!'))
            self.stdout.write(f'  • Subjects migrated: {subjects_migrated}')
            self.stdout.write(f'  • General questions migrated: {general_migrated}')
            self.stdout.write(f'  • Specialist questions migrated: {specialist_migrated}')
            self.stdout.write(f'  • Total questions: {general_migrated + specialist_migrated}')
            
        except transaction.TransactionManagementError:
            if self.dry_run:
                self.stdout.write(self.style.SUCCESS('Dry run completed - no changes made'))
            else:
                raise
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Migration failed: {str(e)}'))
            raise CommandError(f'Migration failed: {str(e)}')
    
    def load_models(self):
        """Import all required models"""
        try:
            # Old models
            from game_sessions.models import MultipleChoiceQuestion
            from mastermind.models import Subject as OldSubject, SpecialistQuestion
            
            # New models
            from shared.models import Subject as NewSubject, Question
            
            self.MultipleChoiceQuestion = MultipleChoiceQuestion
            self.OldSubject = OldSubject
            self.SpecialistQuestion = SpecialistQuestion
            self.NewSubject = NewSubject
            self.Question = Question
            
        except ImportError as e:
            raise CommandError(f'Failed to import models: {str(e)}')
    
    def pre_migration_checks(self):
        """Perform pre-migration validation"""
        self.stdout.write('Performing pre-migration checks...')
        
        # Check if unified model already has data
        existing_questions = self.Question.objects.count()
        existing_subjects = self.NewSubject.objects.count()
        
        if existing_questions > 0 or existing_subjects > 0:
            if not self.force:
                raise CommandError(
                    f'Unified models already contain data: {existing_questions} questions, '
                    f'{existing_subjects} subjects. Use --force to override.'
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f'Unified models already have data ({existing_questions} questions, '
                        f'{existing_subjects} subjects) - continuing with --force'
                    )
                )
        
        # Count source data
        old_general_count = self.MultipleChoiceQuestion.objects.count()
        old_specialist_count = self.SpecialistQuestion.objects.count()
        old_subjects_count = self.OldSubject.objects.count()
        
        self.stdout.write(f'Source data:')
        self.stdout.write(f'  • MultipleChoiceQuestion: {old_general_count}')
        self.stdout.write(f'  • SpecialistQuestion: {old_specialist_count}')
        self.stdout.write(f'  • Subjects: {old_subjects_count}')
        self.stdout.write('')
    
    def migrate_subjects(self):
        """Migrate Subject data from mastermind to shared"""
        self.stdout.write('Phase 1: Migrating subjects...')
        
        subjects_migrated = 0
        
        for old_subject in self.OldSubject.objects.all():
            if not self.dry_run:
                new_subject, created = self.NewSubject.objects.get_or_create(
                    name=old_subject.name,
                    defaults={
                        'description': old_subject.description,
                        'is_active': old_subject.is_active,
                        'created_at': old_subject.created_at,
                    }
                )
                if created:
                    subjects_migrated += 1
                    self.stdout.write(f'  ✓ Migrated subject: {old_subject.name}')
                else:
                    self.stdout.write(f'  → Subject exists: {old_subject.name}')
            else:
                subjects_migrated += 1
                self.stdout.write(f'  [DRY RUN] Would migrate subject: {old_subject.name}')
        
        return subjects_migrated
    
    def migrate_general_questions(self):
        """Migrate MultipleChoiceQuestion to Question (general type)"""
        self.stdout.write('Phase 2: Migrating general questions...')
        
        questions_migrated = 0
        
        for old_question in self.MultipleChoiceQuestion.objects.all():
            if not self.dry_run:
                # Check if already exists
                existing = self.Question.objects.filter(
                    question_text=old_question.question_text,
                    question_type='general'
                ).first()
                
                if not existing:
                    new_question = self.Question.objects.create(
                        question_text=old_question.question_text,
                        choices=old_question.choices,
                        correct_answer=old_question.correct_answer,
                        question_type='general',
                        category=old_question.category,
                        subject=None,
                        difficulty='medium',  # Default for migrated questions
                        created_at=old_question.created_at,
                        last_used=old_question.last_used,
                        usage_count=old_question.usage_count,
                        is_ai_generated=old_question.is_ai_generated,
                    )
                    questions_migrated += 1
                    if questions_migrated % 100 == 0:
                        self.stdout.write(f'  ✓ Migrated {questions_migrated} general questions...')
                else:
                    self.stdout.write(f'  → General question exists: {old_question.question_text[:50]}...')
            else:
                questions_migrated += 1
                if questions_migrated % 100 == 0:
                    self.stdout.write(f'  [DRY RUN] Would migrate {questions_migrated} general questions...')
        
        self.stdout.write(f'  ✓ Completed: {questions_migrated} general questions')
        return questions_migrated
    
    def migrate_specialist_questions(self):
        """Migrate SpecialistQuestion to Question (specialist type)"""
        self.stdout.write('Phase 3: Migrating specialist questions...')
        
        questions_migrated = 0
        
        for old_question in self.SpecialistQuestion.objects.select_related('subject'):
            if not self.dry_run:
                # Get corresponding new subject
                try:
                    new_subject = self.NewSubject.objects.get(name=old_question.subject.name)
                except self.NewSubject.DoesNotExist:
                    self.stdout.write(
                        self.style.ERROR(f'  ✗ Subject not found: {old_question.subject.name}')
                    )
                    continue
                
                # Check if already exists
                existing = self.Question.objects.filter(
                    question_text=old_question.question_text,
                    question_type='specialist',
                    subject=new_subject
                ).first()
                
                if not existing:
                    new_question = self.Question.objects.create(
                        question_text=old_question.question_text,
                        choices=old_question.choices,
                        correct_answer=old_question.correct_answer,
                        question_type='specialist',
                        category=old_question.subject.name,  # Use subject name as category
                        subject=new_subject,
                        difficulty=old_question.difficulty,
                        created_at=old_question.created_at,
                        last_used=old_question.last_used,
                        usage_count=old_question.usage_count,
                        is_ai_generated=old_question.is_ai_generated,
                    )
                    questions_migrated += 1
                    if questions_migrated % 50 == 0:
                        self.stdout.write(f'  ✓ Migrated {questions_migrated} specialist questions...')
                else:
                    self.stdout.write(f'  → Specialist question exists: {old_question.question_text[:50]}...')
            else:
                questions_migrated += 1
                if questions_migrated % 50 == 0:
                    self.stdout.write(f'  [DRY RUN] Would migrate {questions_migrated} specialist questions...')
        
        self.stdout.write(f'  ✓ Completed: {questions_migrated} specialist questions')
        return questions_migrated
    
    def verify_relationships(self):
        """Verify data integrity after migration"""
        self.stdout.write('Phase 4: Verifying relationships...')
        
        if self.dry_run:
            self.stdout.write('  [DRY RUN] Skipping relationship verification')
            return
        
        # Check all specialist questions have valid subjects
        orphaned_specialist = self.Question.objects.filter(
            question_type='specialist',
            subject__isnull=True
        ).count()
        
        if orphaned_specialist > 0:
            raise CommandError(f'Found {orphaned_specialist} specialist questions without subjects')
        
        # Check all general questions have categories
        missing_category = self.Question.objects.filter(
            question_type='general',
            category__isnull=True
        ).count() + self.Question.objects.filter(
            question_type='general',
            category=''
        ).count()
        
        if missing_category > 0:
            raise CommandError(f'Found {missing_category} general questions without categories')
        
        self.stdout.write('  ✓ All relationships verified')
    
    def verify_migration(self):
        """Verify completed migration integrity"""
        self.stdout.write('Verifying migration integrity...')
        
        # Load models for verification
        self.load_models()
        
        # Count records
        old_general = self.MultipleChoiceQuestion.objects.count()
        old_specialist = self.SpecialistQuestion.objects.count()
        old_subjects = self.OldSubject.objects.count()
        
        new_general = self.Question.objects.filter(question_type='general').count()
        new_specialist = self.Question.objects.filter(question_type='specialist').count()
        new_subjects = self.NewSubject.objects.count()
        
        self.stdout.write('Record counts:')
        self.stdout.write(f'  General questions: {old_general} → {new_general}')
        self.stdout.write(f'  Specialist questions: {old_specialist} → {new_specialist}')
        self.stdout.write(f'  Subjects: {old_subjects} → {new_subjects}')
        
        # Check integrity
        issues = []
        
        if new_general != old_general:
            issues.append(f'General question count mismatch: {old_general} → {new_general}')
        
        if new_specialist != old_specialist:
            issues.append(f'Specialist question count mismatch: {old_specialist} → {new_specialist}')
        
        if new_subjects != old_subjects:
            issues.append(f'Subject count mismatch: {old_subjects} → {new_subjects}')
        
        if issues:
            self.stdout.write(self.style.ERROR('Issues found:'))
            for issue in issues:
                self.stdout.write(self.style.ERROR(f'  ✗ {issue}'))
            return False
        else:
            self.stdout.write(self.style.SUCCESS('✓ Migration verification passed'))
            return True