"""
Tests for Shared AI Question Services

Comprehensive test suite for the unified AI question generation service
including error handling, fallback logic, and polymorphic behavior.
"""

import json
from unittest.mock import Mock, patch, MagicMock
from django.test import TestCase
from django.conf import settings

from .services import (
    AIQuestionServiceFactory,
    get_multiple_choice_service,
    get_specialist_service,
    MultipleChoiceAIService,
    SpecialistAIService
)


class AIQuestionServiceFactoryTest(TestCase):
    """Test the factory class for creating AI services"""
    
    def test_create_multiple_choice_service(self):
        """Test creating multiple choice service"""
        service = AIQuestionServiceFactory.create_multiple_choice_service()
        self.assertIsInstance(service, MultipleChoiceAIService)
    
    def test_create_specialist_service(self):
        """Test creating specialist service"""
        service = AIQuestionServiceFactory.create_specialist_service()
        self.assertIsInstance(service, SpecialistAIService)
    
    def test_get_service_for_question_type_multiple_choice(self):
        """Test getting service by type - multiple choice"""
        service = AIQuestionServiceFactory.get_service_for_question_type('multiple_choice')
        self.assertIsInstance(service, MultipleChoiceAIService)
    
    def test_get_service_for_question_type_specialist(self):
        """Test getting service by type - specialist"""
        service = AIQuestionServiceFactory.get_service_for_question_type('specialist')
        self.assertIsInstance(service, SpecialistAIService)
    
    def test_get_service_for_unknown_type_raises_error(self):
        """Test that unknown question type raises ValueError"""
        with self.assertRaises(ValueError) as context:
            AIQuestionServiceFactory.get_service_for_question_type('unknown')
        self.assertIn('Unsupported question type', str(context.exception))
    
    def test_convenience_functions(self):
        """Test convenience functions work correctly"""
        mc_service = get_multiple_choice_service()
        specialist_service = get_specialist_service()
        
        self.assertIsInstance(mc_service, MultipleChoiceAIService)
        self.assertIsInstance(specialist_service, SpecialistAIService)


class MultipleChoiceAIServiceTest(TestCase):
    """Test the multiple choice AI service"""
    
    def setUp(self):
        self.service = MultipleChoiceAIService()
        self.mock_question_data = {
            'question': 'What is the capital of France?',
            'choices': ['London', 'Berlin', 'Paris', 'Madrid'],
            'correct_answer': 'Paris',
            'category': 'Geography'
        }
    
    def test_get_question_model(self):
        """Test that correct model is returned"""
        from game_sessions.models import MultipleChoiceQuestion
        model = self.service.get_question_model()
        self.assertEqual(model, MultipleChoiceQuestion)
    
    def test_create_question_prompt_general(self):
        """Test prompt creation for general categories"""
        prompt = self.service.create_question_prompt("Science")
        self.assertIn("Science", prompt)
        self.assertIn("JSON format", prompt)
        self.assertIn("4 answer choices", prompt)
    
    def test_create_question_prompt_uk_sports(self):
        """Test specialized prompt for UK Sports"""
        prompt = self.service.create_question_prompt("UK Sports")
        self.assertIn("UK/British sports", prompt)
        self.assertIn("Premier League", prompt)
        self.assertIn("Wimbledon", prompt)
    
    def test_create_bulk_questions_prompt(self):
        """Test bulk question prompt creation"""
        prompt = self.service.create_bulk_questions_prompt("Science", 5)
        self.assertIn("5 different multiple choice questions", prompt)
        self.assertIn("JSON array", prompt)
    
    def test_create_bulk_questions_prompt_specialist(self):
        """Test bulk specialist question prompt"""
        prompt = self.service.create_bulk_questions_prompt("Physics", 10, is_specialist=True)
        self.assertIn("10 different multiple choice questions", prompt)
        self.assertIn("specialist subject", prompt)
        self.assertIn("medium to hard difficulty", prompt)
    
    @patch('shared.services.multiple_choice_ai_service.MultipleChoiceQuestion')
    def test_create_question_instance(self, mock_model):
        """Test question instance creation"""
        mock_question = Mock()
        mock_model.objects.create.return_value = mock_question
        
        result = self.service.create_question_instance(self.mock_question_data)
        
        mock_model.objects.create.assert_called_once_with(
            question_text='What is the capital of France?',
            choices=['London', 'Berlin', 'Paris', 'Madrid'],
            correct_answer='Paris',
            category='Geography',
            is_ai_generated=True,
            is_specialist=False
        )
        self.assertEqual(result, mock_question)
    
    @patch('shared.services.multiple_choice_ai_service.MultipleChoiceQuestion')
    def test_create_specialist_question_instance(self, mock_model):
        """Test specialist question instance creation"""
        mock_question = Mock()
        mock_model.objects.create.return_value = mock_question
        
        result = self.service.create_question_instance(
            self.mock_question_data, 
            is_specialist=True
        )
        
        mock_model.objects.create.assert_called_once_with(
            question_text='What is the capital of France?',
            choices=['London', 'Berlin', 'Paris', 'Madrid'],
            correct_answer='Paris',
            category='Geography',
            is_ai_generated=True,
            is_specialist=True
        )
    
    @patch('shared.services.multiple_choice_ai_service.MultipleChoiceQuestion')
    def test_get_existing_questions_for_duplicate_check(self, mock_model):
        """Test getting existing questions for duplicate checking"""
        mock_queryset = Mock()
        mock_model.objects.all.return_value = mock_queryset
        
        result = self.service.get_existing_questions_for_duplicate_check("Science")
        
        mock_model.objects.all.assert_called_once()
        self.assertEqual(result, mock_queryset)


class SpecialistAIServiceTest(TestCase):
    """Test the specialist AI service"""
    
    def setUp(self):
        self.service = SpecialistAIService()
        self.mock_question_data = {
            'question': 'What is quantum entanglement?',
            'choices': ['Option A', 'Option B', 'Option C', 'Option D'],
            'correct_answer': 'Option A',
            'category': 'Physics'
        }
    
    def test_get_question_model(self):
        """Test that correct model is returned"""
        from mastermind.models import SpecialistQuestion
        model = self.service.get_question_model()
        self.assertEqual(model, SpecialistQuestion)
    
    def test_create_question_prompt(self):
        """Test specialist question prompt creation"""
        prompt = self.service.create_question_prompt("Physics")
        self.assertIn("Physics", prompt)
        self.assertIn("specialist subject", prompt)
        self.assertIn("medium to hard difficulty", prompt)
    
    def test_create_bulk_questions_prompt(self):
        """Test bulk specialist question prompt"""
        prompt = self.service.create_bulk_questions_prompt("Chemistry", 15)
        self.assertIn("15 different multiple choice questions", prompt)
        self.assertIn("Chemistry", prompt)
        self.assertIn("JSON array", prompt)
    
    @patch('shared.services.specialist_ai_service.Subject')
    @patch('shared.services.specialist_ai_service.SpecialistQuestion')
    def test_create_question_instance(self, mock_question_model, mock_subject_model):
        """Test specialist question instance creation"""
        mock_subject = Mock()
        mock_subject_model.objects.get_or_create.return_value = (mock_subject, True)
        
        mock_question = Mock()
        mock_question_model.objects.create.return_value = mock_question
        
        result = self.service.create_question_instance(self.mock_question_data)
        
        mock_subject_model.objects.get_or_create.assert_called_once_with(
            name='Physics',
            defaults={'description': 'Specialist questions for Physics'}
        )
        
        mock_question_model.objects.create.assert_called_once_with(
            subject=mock_subject,
            question_text='What is quantum entanglement?',
            choices=['Option A', 'Option B', 'Option C', 'Option D'],
            correct_answer='Option A',
            difficulty='medium',
            is_ai_generated=True
        )
        self.assertEqual(result, mock_question)
    
    @patch('shared.services.specialist_ai_service.Subject')
    @patch('shared.services.specialist_ai_service.SpecialistQuestion')
    def test_get_existing_questions_for_duplicate_check(self, mock_question_model, mock_subject_model):
        """Test getting existing specialist questions for duplicate checking"""
        mock_subject = Mock()
        mock_subject_model.objects.get.return_value = mock_subject
        
        mock_queryset = Mock()
        mock_question_model.objects.filter.return_value = mock_queryset
        
        result = self.service.get_existing_questions_for_duplicate_check("Physics")
        
        mock_subject_model.objects.get.assert_called_once_with(name="Physics")
        mock_question_model.objects.filter.assert_called_once_with(subject=mock_subject)
        self.assertEqual(result, mock_queryset)
    
    @patch('shared.services.specialist_ai_service.Subject')
    @patch('shared.services.specialist_ai_service.SpecialistQuestion')
    def test_get_existing_questions_subject_not_exists(self, mock_question_model, mock_subject_model):
        """Test handling when subject doesn't exist"""
        mock_subject_model.objects.get.side_effect = mock_subject_model.DoesNotExist()
        mock_question_model.objects.none.return_value = Mock()
        
        result = self.service.get_existing_questions_for_duplicate_check("NonExistent")
        
        mock_question_model.objects.none.assert_called_once()


class AIQuestionServiceBaseTest(TestCase):
    """Test the base AIQuestionService functionality"""
    
    def setUp(self):
        self.service = MultipleChoiceAIService()
        self.valid_question_data = {
            'question': 'Test question?',
            'choices': ['A', 'B', 'C', 'D'],
            'correct_answer': 'B',
            'category': 'Test'
        }
    
    def test_initialization_with_custom_models(self):
        """Test service initialization with custom model list"""
        custom_models = ['gpt-4', 'gpt-3.5-turbo']
        service = MultipleChoiceAIService(models_to_try=custom_models)
        self.assertEqual(service.models_to_try, custom_models)
    
    def test_initialization_with_default_models(self):
        """Test service initialization with default models"""
        service = MultipleChoiceAIService()
        self.assertEqual(service.models_to_try, MultipleChoiceAIService.DEFAULT_MODELS)
    
    @patch('shared.services.ai_question_service.settings')
    def test_client_property_no_api_key(self, mock_settings):
        """Test client property raises error when no API key"""
        mock_settings.OPENAI_API_KEY = None
        service = MultipleChoiceAIService()
        
        with self.assertRaises(ValueError) as context:
            _ = service.client
        self.assertIn('No OpenAI API key configured', str(context.exception))
    
    @patch('shared.services.ai_question_service.settings')
    @patch('shared.services.ai_question_service.openai')
    def test_client_property_with_api_key(self, mock_openai, mock_settings):
        """Test client property creates client when API key exists"""
        mock_settings.OPENAI_API_KEY = 'test-key'
        mock_client = Mock()
        mock_openai.OpenAI.return_value = mock_client
        
        service = MultipleChoiceAIService()
        client = service.client
        
        mock_openai.OpenAI.assert_called_once_with(api_key='test-key')
        self.assertEqual(client, mock_client)
    
    def test_validate_question_data_valid(self):
        """Test validation with valid question data"""
        result = self.service._validate_question_data(self.valid_question_data)
        self.assertTrue(result)
    
    def test_validate_question_data_missing_fields(self):
        """Test validation fails with missing fields"""
        invalid_data = {'question': 'Test?'}
        result = self.service._validate_question_data(invalid_data)
        self.assertFalse(result)
    
    def test_validate_question_data_wrong_choice_count(self):
        """Test validation fails with wrong number of choices"""
        invalid_data = self.valid_question_data.copy()
        invalid_data['choices'] = ['A', 'B']  # Only 2 choices
        result = self.service._validate_question_data(invalid_data)
        self.assertFalse(result)
    
    def test_validate_question_data_correct_answer_not_in_choices(self):
        """Test validation fails when correct answer not in choices"""
        invalid_data = self.valid_question_data.copy()
        invalid_data['correct_answer'] = 'E'  # Not in choices
        result = self.service._validate_question_data(invalid_data)
        self.assertFalse(result)
    
    def test_parse_single_question_response_valid_json(self):
        """Test parsing valid JSON response"""
        response = json.dumps(self.valid_question_data)
        result = self.service._parse_single_question_response(response)
        self.assertEqual(result, self.valid_question_data)
    
    def test_parse_single_question_response_with_markdown(self):
        """Test parsing JSON wrapped in markdown"""
        response = f"```json\n{json.dumps(self.valid_question_data)}\n```"
        result = self.service._parse_single_question_response(response)
        self.assertEqual(result, self.valid_question_data)
    
    def test_parse_bulk_questions_response_valid(self):
        """Test parsing valid bulk response"""
        bulk_data = [self.valid_question_data, self.valid_question_data]
        response = json.dumps(bulk_data)
        result = self.service._parse_bulk_questions_response(response)
        self.assertEqual(result, bulk_data)
    
    def test_parse_bulk_questions_response_not_array(self):
        """Test parsing non-array bulk response returns None"""
        response = json.dumps(self.valid_question_data)  # Single object, not array
        result = self.service._parse_bulk_questions_response(response)
        self.assertIsNone(result)
    
    def test_extract_json_from_text_object(self):
        """Test extracting JSON object from text"""
        text = "Here is the answer: {'question': 'test'} and that's it"
        result = self.service._extract_json_from_text(text, expect_array=False)
        self.assertEqual(result, {'question': 'test'})
    
    def test_extract_json_from_text_array(self):
        """Test extracting JSON array from text"""
        text = "Here is the array: [{'question': 'test'}] and that's it"
        result = self.service._extract_json_from_text(text, expect_array=True)
        self.assertEqual(result, [{'question': 'test'}])
    
    def test_extract_json_from_text_no_match(self):
        """Test extracting JSON when no JSON found"""
        text = "No JSON here at all"
        result = self.service._extract_json_from_text(text, expect_array=False)
        self.assertIsNone(result)
    
    @patch.object(MultipleChoiceAIService, 'get_existing_questions_for_duplicate_check')
    def test_is_duplicate_question_no_duplicates(self, mock_get_existing):
        """Test duplicate detection when no duplicates exist"""
        mock_question = Mock()
        mock_question.question_text = "Different question"
        mock_question.choices = ['X', 'Y', 'Z', 'W']
        mock_question.correct_answer = "X"
        
        mock_get_existing.return_value = [mock_question]
        
        result = self.service._is_duplicate_question(self.valid_question_data, "Test")
        self.assertFalse(result)
    
    @patch.object(MultipleChoiceAIService, 'get_existing_questions_for_duplicate_check')
    def test_is_duplicate_question_similar_text(self, mock_get_existing):
        """Test duplicate detection with similar question text"""
        mock_question = Mock()
        mock_question.question_text = "Test question?"  # Same as test data
        mock_question.choices = ['X', 'Y', 'Z', 'W']
        mock_question.correct_answer = "X"
        
        mock_get_existing.return_value = [mock_question]
        
        result = self.service._is_duplicate_question(self.valid_question_data, "Test")
        self.assertTrue(result)
    
    @patch.object(MultipleChoiceAIService, 'get_existing_questions_for_duplicate_check')
    def test_is_duplicate_question_similar_choices(self, mock_get_existing):
        """Test duplicate detection with similar answer choices"""
        mock_question = Mock()
        mock_question.question_text = "Different question"
        mock_question.choices = ['A', 'B', 'C', 'D']  # Same as test data
        mock_question.correct_answer = "B"  # Same as test data
        
        mock_get_existing.return_value = [mock_question]
        
        result = self.service._is_duplicate_question(self.valid_question_data, "Test")
        self.assertTrue(result)


class AIQuestionServiceErrorHandlingTest(TestCase):
    """Test error handling and fallback logic"""
    
    def setUp(self):
        self.service = MultipleChoiceAIService()
    
    @patch('shared.services.ai_question_service.settings')
    def test_generate_single_question_no_api_key(self, mock_settings):
        """Test generation fails gracefully without API key"""
        mock_settings.OPENAI_API_KEY = None
        result = self.service.generate_single_question("Test")
        self.assertIsNone(result)
    
    @patch('shared.services.ai_question_service.settings')
    def test_generate_bulk_questions_no_api_key(self, mock_settings):
        """Test bulk generation fails gracefully without API key"""
        mock_settings.OPENAI_API_KEY = None
        result = self.service.generate_bulk_questions("Test", 5)
        self.assertEqual(result, 0)
    
    def test_generate_bulk_questions_empty_category(self):
        """Test bulk generation with empty category"""
        result = self.service.generate_bulk_questions("", 5)
        self.assertEqual(result, 0)
        
        result = self.service.generate_bulk_questions(None, 5)
        self.assertEqual(result, 0)
    
    @patch.object(MultipleChoiceAIService, 'client')
    def test_make_openai_request_all_models_fail(self, mock_client):
        """Test OpenAI request when all models fail"""
        mock_client.chat.completions.create.side_effect = Exception("API Error")
        
        with self.assertRaises(Exception):
            self.service._make_openai_request("test prompt", 100, 0.8)
    
    @patch.object(MultipleChoiceAIService, 'client')
    def test_make_openai_request_fallback_success(self, mock_client):
        """Test OpenAI request with fallback to working model"""
        # First model fails, second succeeds
        mock_response = Mock()
        mock_response.choices[0].message.content = "Success"
        
        mock_client.chat.completions.create.side_effect = [
            Exception("First model failed"),
            mock_response
        ]
        
        result = self.service._make_openai_request("test prompt", 100, 0.8)
        self.assertEqual(result, "Success")
    
    @patch.object(MultipleChoiceAIService, 'client')
    def test_make_openai_request_o3_mini_model(self, mock_client):
        """Test OpenAI request with o3-mini model (no temperature parameter)"""
        service = MultipleChoiceAIService(models_to_try=['o3-mini'])
        mock_response = Mock()
        mock_response.choices[0].message.content = "Success"
        mock_client.chat.completions.create.return_value = mock_response
        
        result = service._make_openai_request("test prompt", 100, 0.8)
        
        # Verify o3-mini was called with max_completion_tokens instead of max_tokens
        call_args = mock_client.chat.completions.create.call_args
        self.assertIn('max_completion_tokens', call_args.kwargs)
        self.assertNotIn('max_tokens', call_args.kwargs)
        self.assertNotIn('temperature', call_args.kwargs)
        self.assertEqual(result, "Success")
    
    @patch.object(MultipleChoiceAIService, '_make_openai_request')
    @patch.object(MultipleChoiceAIService, '_validate_question_data')
    def test_generate_single_question_invalid_response(self, mock_validate, mock_request):
        """Test single question generation with invalid AI response"""
        mock_request.return_value = "Invalid JSON response"
        mock_validate.return_value = False
        
        result = self.service.generate_single_question("Test")
        self.assertIsNone(result)
    
    @patch.object(MultipleChoiceAIService, '_make_openai_request')
    @patch.object(MultipleChoiceAIService, '_is_duplicate_question')
    @patch.object(MultipleChoiceAIService, '_validate_question_data')
    def test_generate_single_question_duplicate_detected(self, mock_validate, mock_duplicate, mock_request):
        """Test single question generation when duplicate is detected"""
        mock_request.return_value = json.dumps({
            'question': 'Test?',
            'choices': ['A', 'B', 'C', 'D'],
            'correct_answer': 'B',
            'category': 'Test'
        })
        mock_validate.return_value = True
        mock_duplicate.return_value = True
        
        result = self.service.generate_single_question("Test")
        self.assertIsNone(result)


class AIQuestionServiceIntegrationTest(TestCase):
    """Integration tests for the AI question service with mocked dependencies"""
    
    @patch('shared.services.ai_question_service.settings')
    @patch.object(MultipleChoiceAIService, 'client')
    @patch.object(MultipleChoiceAIService, 'create_question_instance')
    @patch.object(MultipleChoiceAIService, '_is_duplicate_question')
    def test_successful_question_generation_flow(self, mock_duplicate, mock_create, mock_client, mock_settings):
        """Test complete successful question generation flow"""
        # Setup mocks
        mock_settings.OPENAI_API_KEY = 'test-key'
        mock_duplicate.return_value = False
        
        mock_response = Mock()
        mock_response.choices[0].message.content = json.dumps({
            'question': 'What is 2+2?',
            'choices': ['3', '4', '5', '6'],
            'correct_answer': '4',
            'category': 'Math'
        })
        mock_client.chat.completions.create.return_value = mock_response
        
        mock_question_instance = Mock()
        mock_create.return_value = mock_question_instance
        
        # Execute
        service = MultipleChoiceAIService()
        result = service.generate_single_question("Math")
        
        # Verify
        self.assertEqual(result, mock_question_instance)
        mock_client.chat.completions.create.assert_called_once()
        mock_create.assert_called_once()
        mock_duplicate.assert_called_once()
    
    @patch('shared.services.ai_question_service.settings')
    @patch.object(MultipleChoiceAIService, 'client')
    @patch.object(MultipleChoiceAIService, 'create_question_instance')
    @patch.object(MultipleChoiceAIService, '_is_duplicate_question')
    def test_successful_bulk_generation_flow(self, mock_duplicate, mock_create, mock_client, mock_settings):
        """Test complete successful bulk generation flow"""
        # Setup mocks
        mock_settings.OPENAI_API_KEY = 'test-key'
        mock_duplicate.return_value = False
        
        bulk_response = [
            {
                'question': 'What is 2+2?',
                'choices': ['3', '4', '5', '6'],
                'correct_answer': '4',
                'category': 'Math'
            },
            {
                'question': 'What is 3+3?',
                'choices': ['5', '6', '7', '8'],
                'correct_answer': '6',
                'category': 'Math'
            }
        ]
        
        mock_response = Mock()
        mock_response.choices[0].message.content = json.dumps(bulk_response)
        mock_client.chat.completions.create.return_value = mock_response
        
        mock_question_instance = Mock()
        mock_create.return_value = mock_question_instance
        
        # Execute
        service = MultipleChoiceAIService()
        result = service.generate_bulk_questions("Math", 2)
        
        # Verify
        self.assertEqual(result, 2)  # 2 questions created
        mock_client.chat.completions.create.assert_called_once()
        self.assertEqual(mock_create.call_count, 2)  # 2 questions created
        self.assertEqual(mock_duplicate.call_count, 2)  # 2 duplicate checks