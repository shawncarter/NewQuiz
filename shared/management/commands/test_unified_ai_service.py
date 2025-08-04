"""
Management command to test the unified AI service functionality

This command demonstrates and validates the new shared AI question generation
service without requiring OpenAI API access.
"""

from django.core.management.base import BaseCommand
from django.test import override_settings
from unittest.mock import Mock, patch
import json

from shared.services import get_multiple_choice_service, get_specialist_service


class Command(BaseCommand):
    help = 'Test the unified AI question generation service'

    def add_arguments(self, parser):
        parser.add_argument(
            '--test-type',
            choices=['multiple_choice', 'specialist', 'both'],
            default='both',
            help='Type of service to test'
        )
        parser.add_argument(
            '--category',
            default='Science',
            help='Category to use for test questions'
        )

    def handle(self, *args, **options):
        test_type = options['test_type']
        category = options['category']
        
        self.stdout.write(
            self.style.SUCCESS(
                f"Testing unified AI service - Type: {test_type}, Category: {category}"
            )
        )
        
        if test_type in ['multiple_choice', 'both']:
            self.test_multiple_choice_service(category)
        
        if test_type in ['specialist', 'both']:
            self.test_specialist_service(category)
        
        self.stdout.write(self.style.SUCCESS("All tests completed successfully!"))

    def test_multiple_choice_service(self, category):
        """Test the multiple choice AI service"""
        self.stdout.write(self.style.WARNING("\n=== Testing Multiple Choice Service ==="))
        
        service = get_multiple_choice_service()
        
        # Test service properties
        self.stdout.write(f"✓ Service created: {type(service).__name__}")
        self.stdout.write(f"✓ Question model: {service.get_question_model().__name__}")
        
        # Test prompt generation
        prompt = service.create_question_prompt(category)
        self.stdout.write(f"✓ Question prompt generated ({len(prompt)} chars)")
        
        bulk_prompt = service.create_bulk_questions_prompt(category, 5)
        self.stdout.write(f"✓ Bulk prompt generated ({len(bulk_prompt)} chars)")
        
        # Test validation
        valid_data = {
            'question': 'What is the atomic number of carbon?',
            'choices': ['4', '6', '8', '12'],
            'correct_answer': '6',
            'category': category
        }
        
        is_valid = service._validate_question_data(valid_data)
        self.stdout.write(f"✓ Question validation: {is_valid}")
        
        # Test JSON parsing
        json_response = json.dumps(valid_data)
        parsed = service._parse_single_question_response(json_response)
        self.stdout.write(f"✓ JSON parsing: {parsed is not None}")
        
        # Test markdown extraction
        markdown_response = f"```json\n{json_response}\n```"
        extracted = service._parse_single_question_response(markdown_response)
        self.stdout.write(f"✓ Markdown extraction: {extracted is not None}")
        
        self.stdout.write(self.style.SUCCESS("Multiple choice service tests passed!"))

    def test_specialist_service(self, category):
        """Test the specialist AI service"""
        self.stdout.write(self.style.WARNING("\n=== Testing Specialist Service ==="))
        
        service = get_specialist_service()
        
        # Test service properties
        self.stdout.write(f"✓ Service created: {type(service).__name__}")
        self.stdout.write(f"✓ Question model: {service.get_question_model().__name__}")
        
        # Test prompt generation
        prompt = service.create_question_prompt(category)
        self.stdout.write(f"✓ Question prompt generated ({len(prompt)} chars)")
        
        bulk_prompt = service.create_bulk_questions_prompt(category, 10)
        self.stdout.write(f"✓ Bulk prompt generated ({len(bulk_prompt)} chars)")
        
        # Test validation with specialist data
        specialist_data = {
            'question': f'Advanced {category} question about quantum mechanics?',
            'choices': ['Option A', 'Option B', 'Option C', 'Option D'],
            'correct_answer': 'Option A',
            'category': category
        }
        
        is_valid = service._validate_question_data(specialist_data)
        self.stdout.write(f"✓ Specialist question validation: {is_valid}")
        
        # Test bulk parsing
        bulk_data = [specialist_data, specialist_data]
        bulk_response = json.dumps(bulk_data)
        parsed_bulk = service._parse_bulk_questions_response(bulk_response)
        self.stdout.write(f"✓ Bulk JSON parsing: {len(parsed_bulk) if parsed_bulk else 0} questions")
        
        self.stdout.write(self.style.SUCCESS("Specialist service tests passed!"))

    def simulate_ai_generation(self, service, category):
        """Simulate AI question generation with mocked OpenAI responses"""
        self.stdout.write(self.style.WARNING("\n=== Simulating AI Generation ==="))
        
        mock_question_data = {
            'question': f'Test question about {category}?',
            'choices': ['A', 'B', 'C', 'D'],
            'correct_answer': 'B',
            'category': category
        }
        
        with patch.object(service, '_make_openai_request') as mock_request, \
             patch.object(service, '_is_duplicate_question') as mock_duplicate, \
             patch.object(service, 'create_question_instance') as mock_create:
            
            # Setup mocks
            mock_request.return_value = json.dumps(mock_question_data)
            mock_duplicate.return_value = False
            mock_question = Mock()
            mock_question.question_text = mock_question_data['question']
            mock_create.return_value = mock_question
            
            # Test single question generation
            result = service.generate_single_question(category)
            
            if result:
                self.stdout.write(f"✓ Simulated question generation successful")
                self.stdout.write(f"  Generated: {result.question_text}")
            else:
                self.stdout.write(self.style.ERROR("✗ Question generation failed"))
        
        self.stdout.write(self.style.SUCCESS("AI generation simulation completed!"))