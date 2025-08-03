"""
Django management command to bulk-generate questions for mastermind games.

This command pre-generates both specialist and general knowledge questions
to ensure sufficient question pools are available for gameplay.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from mastermind.models import Subject, SpecialistQuestion, GeneralKnowledgeQuestion
from shared.services.specialist_ai_service import SpecialistAIService
from shared.services.general_knowledge_ai_service import GeneralKnowledgeAIService
import logging

logger = logging.getLogger('mastermind')


class Command(BaseCommand):
    help = 'Bulk generate questions for mastermind games (both specialist and general knowledge)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--general-knowledge',
            type=int,
            default=100,
            help='Number of general knowledge questions to generate (default: 100)'
        )
        parser.add_argument(
            '--specialist-subject',
            type=str,
            help='Generate questions for a specific specialist subject'
        )
        parser.add_argument(
            '--specialist-count',
            type=int,
            default=50,
            help='Number of specialist questions to generate per subject (default: 50)'
        )
        parser.add_argument(
            '--all-subjects',
            action='store_true',
            help='Generate questions for all existing subjects'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be generated without actually generating'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Generate questions even if sufficient questions already exist'
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting bulk question generation...'))
        
        # Initialize AI services
        specialist_ai_service = SpecialistAIService()
        general_knowledge_ai_service = GeneralKnowledgeAIService()
        
        total_generated = 0
        
        try:
            with transaction.atomic():
                # Generate general knowledge questions
                total_generated += self._generate_general_knowledge_questions(
                    general_knowledge_ai_service,
                    options['general_knowledge'],
                    options['dry_run'],
                    options['force']
                )
                
                # Generate specialist questions
                if options['specialist_subject']:
                    # Single subject
                    total_generated += self._generate_specialist_questions_for_subject(
                        specialist_ai_service,
                        options['specialist_subject'],
                        options['specialist_count'],
                        options['dry_run'],
                        options['force']
                    )
                elif options['all_subjects']:
                    # All existing subjects
                    subjects = Subject.objects.filter(is_active=True)
                    for subject in subjects:
                        total_generated += self._generate_specialist_questions_for_subject(
                            specialist_ai_service,
                            subject.name,
                            options['specialist_count'],
                            options['dry_run'],
                            options['force']
                        )
                
                if options['dry_run']:
                    self.stdout.write(
                        self.style.WARNING(f'DRY RUN: Would generate {total_generated} questions')
                    )
                    # Don't commit the transaction in dry run mode
                    raise CommandError("Dry run completed (no questions generated)")
                else:
                    self.stdout.write(
                        self.style.SUCCESS(f'Successfully generated {total_generated} questions')
                    )
                    
        except CommandError:
            # This is expected for dry runs
            pass
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error during bulk generation: {e}')
            )
            raise CommandError(f'Bulk generation failed: {e}')
    
    def _generate_general_knowledge_questions(self, ai_service, count, dry_run, force):
        """Generate general knowledge questions"""
        current_count = GeneralKnowledgeQuestion.objects.count()
        
        self.stdout.write(f'Current general knowledge questions: {current_count}')
        
        if not force and current_count >= count:
            self.stdout.write(
                self.style.WARNING(
                    f'Sufficient general knowledge questions exist ({current_count}). '
                    f'Use --force to generate anyway.'
                )
            )
            return 0
        
        questions_to_generate = count if force else max(0, count - current_count)
        
        if questions_to_generate <= 0:
            return 0
        
        self.stdout.write(f'Generating {questions_to_generate} general knowledge questions...')
        
        if dry_run:
            return questions_to_generate
        
        try:
            generated = ai_service.generate_bulk_questions("General Knowledge", questions_to_generate)
            self.stdout.write(
                self.style.SUCCESS(f'Generated {generated} general knowledge questions')
            )
            return generated
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error generating general knowledge questions: {e}')
            )
            return 0
    
    def _generate_specialist_questions_for_subject(self, ai_service, subject_name, count, dry_run, force):
        """Generate specialist questions for a specific subject"""
        try:
            subject, created = Subject.objects.get_or_create(
                name=subject_name,
                defaults={'description': f'Specialist questions for {subject_name}'}
            )
            
            if created:
                self.stdout.write(f'Created new subject: {subject_name}')
            
            current_count = SpecialistQuestion.objects.filter(subject=subject).count()
            self.stdout.write(f'Current questions for {subject_name}: {current_count}')
            
            if not force and current_count >= count:
                self.stdout.write(
                    self.style.WARNING(
                        f'Sufficient questions exist for {subject_name} ({current_count}). '
                        f'Use --force to generate anyway.'
                    )
                )
                return 0
            
            questions_to_generate = count if force else max(0, count - current_count)
            
            if questions_to_generate <= 0:
                return 0
            
            self.stdout.write(f'Generating {questions_to_generate} questions for {subject_name}...')
            
            if dry_run:
                return questions_to_generate
            
            generated = ai_service.generate_bulk_questions(subject_name, questions_to_generate)
            self.stdout.write(
                self.style.SUCCESS(f'Generated {generated} questions for {subject_name}')
            )
            return generated
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error generating questions for {subject_name}: {e}')
            )
            return 0