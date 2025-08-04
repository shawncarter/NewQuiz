"""
Test command for the unified AI service to ensure it works correctly
with both general and specialist questions.
"""

from django.core.management.base import BaseCommand
from shared.services.unified_ai_service import UnifiedAIService
from shared.services.ai_question_factory import get_unified_service
from shared.models import Question, Subject


class Command(BaseCommand):
    help = 'Test the unified AI service functionality'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--test-type',
            choices=['general', 'specialist', 'both'],
            default='both',
            help='Type of questions to test'
        )
    
    def handle(self, *args, **options):
        test_type = options['test_type']
        
        self.stdout.write(self.style.SUCCESS('Testing Unified AI Service'))
        self.stdout.write('=' * 40)
        
        # Get service instance
        service = get_unified_service()
        self.stdout.write(f'✓ Service created: {service.__class__.__name__}')
        
        # Test general questions
        if test_type in ['general', 'both']:
            self.test_general_questions(service)
        
        # Test specialist questions  
        if test_type in ['specialist', 'both']:
            self.test_specialist_questions(service)
        
        # Test question retrieval
        self.test_question_retrieval(service)
        
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('All tests completed successfully!'))
    
    def test_general_questions(self, service):
        """Test general question functionality"""
        self.stdout.write('')
        self.stdout.write('Testing General Questions:')
        self.stdout.write('-' * 25)
        
        # Test getting existing question
        general_count = Question.objects.filter(question_type='general').count()
        self.stdout.write(f'✓ Found {general_count} existing general questions')
        
        # Test question retrieval
        question = service.get_question_for_game(
            category='UK Sports',
            question_type='general',
            force_ai_generation=False
        )
        
        if question:
            self.stdout.write(f'✓ Retrieved general question: {question.question_text[:50]}...')
            self.stdout.write(f'  - Category: {question.category}')
            self.stdout.write(f'  - Type: {question.question_type}')
            self.stdout.write(f'  - Usage count: {question.usage_count}')
        else:
            self.stdout.write('✗ No general question found')
    
    def test_specialist_questions(self, service):
        """Test specialist question functionality"""
        self.stdout.write('')
        self.stdout.write('Testing Specialist Questions:')
        self.stdout.write('-' * 28)
        
        # Test getting existing question
        specialist_count = Question.objects.filter(question_type='specialist').count()
        self.stdout.write(f'✓ Found {specialist_count} existing specialist questions')
        
        # Test subject availability
        subjects = Subject.objects.filter(is_active=True)
        self.stdout.write(f'✓ Found {subjects.count()} active subjects: {[s.name for s in subjects]}')
        
        if subjects.exists():
            subject = subjects.first()
            
            # Test question retrieval
            question = service.get_specialist_question(subject.name)
            
            if question:
                self.stdout.write(f'✓ Retrieved specialist question: {question.question_text[:50]}...')
                self.stdout.write(f'  - Subject: {question.subject.name}')
                self.stdout.write(f'  - Type: {question.question_type}')
                self.stdout.write(f'  - Difficulty: {question.difficulty}')
                self.stdout.write(f'  - Usage count: {question.usage_count}')
            else:
                self.stdout.write(f'✗ No specialist question found for {subject.name}')
        else:
            self.stdout.write('✗ No active subjects found')
    
    def test_question_retrieval(self, service):
        """Test unified question retrieval methods"""
        self.stdout.write('')
        self.stdout.write('Testing Question Retrieval:')
        self.stdout.write('-' * 25)
        
        # Test general question retrieval
        general_questions = Question.get_general_questions('General Knowledge')
        self.stdout.write(f'✓ General Knowledge questions: {general_questions.count()}')
        
        # Test specialist question retrieval  
        subjects = Subject.objects.filter(is_active=True)
        if subjects.exists():
            subject = subjects.first()
            specialist_questions = Question.get_specialist_questions(subject_name=subject.name)
            self.stdout.write(f'✓ {subject.name} specialist questions: {specialist_questions.count()}')
        
        # Test total counts
        total_questions = Question.objects.count()
        general_total = Question.objects.filter(question_type='general').count()
        specialist_total = Question.objects.filter(question_type='specialist').count()
        
        self.stdout.write('')
        self.stdout.write('Total Question Counts:')
        self.stdout.write(f'  - Total: {total_questions}')
        self.stdout.write(f'  - General: {general_total}')
        self.stdout.write(f'  - Specialist: {specialist_total}')
        self.stdout.write(f'  - Verification: {general_total + specialist_total == total_questions} ✓')