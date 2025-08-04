"""
Test Question Pre-Generation System

Tests the question pre-generation service to ensure questions are properly
generated and available for mastermind rounds without delays.
"""

import os
from django.test import TestCase
from django.conf import settings
from unittest.mock import patch, MagicMock

from game_sessions.models import GameSession, GameConfiguration
from players.models import Player
from mastermind.models import Subject, SpecialistQuestion, GeneralKnowledgeQuestion
from mastermind.question_pregeneration_service import QuestionPregenerationService
from mastermind.services import MastermindService


class QuestionPregenerationTestCase(TestCase):
    """Test the question pre-generation system"""
    
    def setUp(self):
        """Set up test data"""
        # Create game session first
        self.game_session = GameSession.objects.create(
            game_code='TEST01',
            current_round_number=1
        )
        
        # Create game type for configuration
        from game_sessions.models import GameType
        game_type = GameType.objects.create(
            name='Test Game',
            description='Test game type'
        )
        
        # Create game configuration (requires game_session)
        self.config = GameConfiguration.objects.create(
            game_session=self.game_session,
            game_type=game_type,
            round_time_seconds=90,
            round_type_sequence=['mastermind']
        )
        
        # Create test players with specialist subjects
        self.player1 = Player.objects.create(
            game_session=self.game_session,
            name='Test Player 1',
            specialist_subject='History',
            is_connected=True
        )
        
        self.player2 = Player.objects.create(
            game_session=self.game_session,
            name='Test Player 2',
            specialist_subject='Science',
            is_connected=True
        )
        
        # Create pre-generation service
        self.pregeneration_service = QuestionPregenerationService(self.game_session)
    
    def test_validation_without_questions(self):
        """Test validation when no questions exist"""
        validation_result = self.pregeneration_service.validate_question_availability()
        
        self.assertFalse(validation_result['success'])
        self.assertIn('errors', validation_result)
        self.assertTrue(len(validation_result['errors']) > 0)
    
    def test_pregeneration_status(self):
        """Test getting pre-generation status"""
        status = self.pregeneration_service.get_pregeneration_status()
        
        self.assertIn('specialist_subjects', status)
        self.assertIn('general_knowledge_questions', status)
        self.assertIn('player_subjects', status)
        self.assertEqual(status['questions_needed_per_player'], 20)
        self.assertEqual(status['players_count'], 2)
        self.assertIn('History', status['player_subjects'])
        self.assertIn('Science', status['player_subjects'])
    
    @patch('mastermind.models.SpecialistQuestion.objects.filter')
    @patch('mastermind.models.Subject.objects.get_or_create')
    @patch('mastermind.models.GeneralKnowledgeQuestion.objects.count')
    @patch('shared.services.specialist_ai_service.SpecialistAIService.generate_bulk_questions')
    @patch('shared.services.general_knowledge_ai_service.GeneralKnowledgeAIService.generate_bulk_questions')
    def test_pregeneration_mocked(self, mock_gk_gen, mock_spec_gen, mock_gk_count, mock_subject_get_create, mock_spec_filter):
        """Test pre-generation with mocked AI services"""
        # Mock database operations to avoid table locks
        from mastermind.models import Subject
        
        # Mock subject creation for both Science and History
        mock_subject_science = Subject(name='Science', description='Specialist questions for Science')
        mock_subject_history = Subject(name='History', description='Specialist questions for History')
        
        def subject_get_or_create_side_effect(name, defaults=None):
            if name == 'Science':
                return mock_subject_science, True
            elif name == 'History':
                return mock_subject_history, True
            else:
                return Subject(name=name), True
        
        mock_subject_get_create.side_effect = subject_get_or_create_side_effect
        
        # Mock no existing specialist questions (so AI generation is triggered)
        mock_spec_filter.return_value.count.return_value = 0
        
        # Mock no existing general knowledge questions (so AI generation is triggered)
        mock_gk_count.return_value = 0
        
        # Mock successful AI generation
        mock_spec_gen.return_value = 20  # Generated 20 specialist questions per subject
        mock_gk_gen.return_value = 60   # Generated 60 general knowledge questions
        
        # Run pre-generation
        result = self.pregeneration_service.pregenerate_all_questions()
        
        # Verify results
        self.assertTrue(result['success'])
        self.assertEqual(result['total_questions_generated'], 100)  # 20*2 subjects + 60 = 100
        self.assertEqual(result['players_count'], 2)
        
        # Verify AI services were called for both subjects
        self.assertEqual(mock_spec_gen.call_count, 2)  # Called for Science and History
        self.assertTrue(mock_gk_gen.called)
    
    def test_mastermind_service_integration(self):
        """Test integration with MastermindService"""
        mastermind_service = MastermindService(self.game_session)
        
        # Test getting pre-generation status
        status = mastermind_service.get_question_generation_status()
        self.assertIn('player_subjects', status)
        
        # Test validation (should fail without questions)
        validation = mastermind_service.validate_question_readiness()
        self.assertFalse(validation['success'])
    
    def test_ensure_specialist_subject_questions(self):
        """Test ensuring specialist questions for a specific subject"""
        with patch('shared.services.specialist_ai_service.SpecialistAIService.generate_bulk_questions') as mock_gen:
            mock_gen.return_value = 40
            
            # Test private method directly
            generated = self.pregeneration_service._ensure_specialist_subject_questions('History')
            
            self.assertEqual(generated, 40)
            mock_gen.assert_called_once_with('History', 40)  # 20 * 2 buffer
    
    def test_pregeneration_with_existing_questions(self):
        """Test pre-generation when some questions already exist"""
        # Create some existing questions
        history_subject = Subject.objects.create(name='History')
        for i in range(15):
            SpecialistQuestion.objects.create(
                subject=history_subject,
                question_text=f'Test history question {i}',
                choices=['A', 'B', 'C', 'D'],
                correct_answer='A',
                is_ai_generated=False
            )
        
        # Create some general knowledge questions
        for i in range(30):
            GeneralKnowledgeQuestion.objects.create(
                question_text=f'Test GK question {i}',
                choices=['A', 'B', 'C', 'D'],
                correct_answer='A',
                is_ai_generated=False
            )
        
        with patch('shared.services.specialist_ai_service.SpecialistAIService.generate_bulk_questions') as mock_spec_gen, \
             patch('shared.services.general_knowledge_ai_service.GeneralKnowledgeAIService.generate_bulk_questions') as mock_gk_gen:
            
            # Mock generating only the remaining needed questions
            mock_spec_gen.return_value = 25  # For History: need 40, have 15, generate 25
            mock_gk_gen.return_value = 30   # For GK: need 60, have 30, generate 30
            
            result = self.pregeneration_service.pregenerate_all_questions()
            
            self.assertTrue(result['success'])
            # Should generate fewer questions since some already exist
            self.assertGreater(result['total_questions_generated'], 0)
    
    def test_validation_with_sufficient_questions(self):
        """Test validation when sufficient questions exist"""
        # Create sufficient questions for all subjects
        history_subject = Subject.objects.create(name='History')
        science_subject = Subject.objects.create(name='Science')
        
        # Create 25 questions for each subject (more than the 20 needed)
        for subject in [history_subject, science_subject]:
            for i in range(25):
                SpecialistQuestion.objects.create(
                    subject=subject,
                    question_text=f'Test question {i} for {subject.name}',
                    choices=['A', 'B', 'C', 'D'],
                    correct_answer='A',
                    is_ai_generated=False
                )
        
        # Create 25 general knowledge questions (more than the 20 needed)
        for i in range(25):
            GeneralKnowledgeQuestion.objects.create(
                question_text=f'Test GK question {i}',
                choices=['A', 'B', 'C', 'D'],
                correct_answer='A',
                is_ai_generated=False
            )
        
        # Test validation
        validation_result = self.pregeneration_service.validate_question_availability()
        
        self.assertTrue(validation_result['success'])
        self.assertEqual(len(validation_result['errors']), 0)
        
        # Check specialist validation
        self.assertIn('History', validation_result['specialist_validation'])
        self.assertIn('Science', validation_result['specialist_validation'])
        self.assertTrue(validation_result['specialist_validation']['History']['sufficient'])
        self.assertTrue(validation_result['specialist_validation']['Science']['sufficient'])
        
        # Check general knowledge validation
        self.assertTrue(validation_result['general_knowledge_validation']['sufficient'])