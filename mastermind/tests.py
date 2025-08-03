"""
Mastermind App Tests

Basic tests to verify the mastermind app is working correctly.
"""

from django.test import TestCase
from django.urls import reverse
from game_sessions.models import GameSession, GameType, GameConfiguration
from players.models import Player
from .models import Subject, SpecialistQuestion, MastermindRound
from .services import MastermindService


class MastermindModelsTest(TestCase):
    """Test mastermind models work correctly"""
    
    def setUp(self):
        self.subject = Subject.objects.create(name="Test Subject")
        
    def test_subject_creation(self):
        """Test creating a subject"""
        self.assertEqual(self.subject.name, "Test Subject")
        self.assertTrue(self.subject.is_active)
        
    def test_specialist_question_creation(self):
        """Test creating specialist questions"""
        question = SpecialistQuestion.objects.create(
            subject=self.subject,
            question_text="Test question?",
            choices=["A", "B", "C", "D"],
            correct_answer="B"
        )
        
        self.assertEqual(question.subject, self.subject)
        self.assertEqual(question.correct_answer, "B")
        self.assertEqual(question.difficulty, "medium")
        
    def test_question_mark_as_used(self):
        """Test marking a question as used"""
        question = SpecialistQuestion.objects.create(
            subject=self.subject,
            question_text="Test question?",
            choices=["A", "B", "C", "D"],
            correct_answer="B"
        )
        
        initial_count = question.usage_count
        question.mark_as_used()
        
        self.assertEqual(question.usage_count, initial_count + 1)
        self.assertIsNotNone(question.last_used)


class MastermindServiceTest(TestCase):
    """Test mastermind service functionality"""
    
    def setUp(self):
        self.game_type = GameType.objects.create(name="Quiz Game")
        self.game_session = GameSession.objects.create()
        self.config = GameConfiguration.objects.create(
            game_session=self.game_session,
            game_type=self.game_type,
            num_rounds=3,
            round_time_seconds=30,
            round_type_sequence=['mastermind']
        )
        
        self.player = Player.objects.create(
            name="Test Player",
            game_session=self.game_session,
            specialist_subject="Science"
        )
        
        self.service = MastermindService(self.game_session)
        
    def test_get_or_create_round(self):
        """Test getting or creating a mastermind round"""
        round_obj = self.service.get_or_create_round(1)
        
        self.assertIsInstance(round_obj, MastermindRound)
        self.assertEqual(round_obj.game_session, self.game_session)
        self.assertEqual(round_obj.round_number, 1)
        self.assertEqual(round_obj.state, 'waiting_for_player_selection')
        
    def test_get_round_data(self):
        """Test getting round data"""
        round_data = self.service.get_round_data(1)
        
        self.assertEqual(round_data['round_type'], 'mastermind')
        self.assertEqual(round_data['round_number'], 1)
        self.assertEqual(round_data['state'], 'waiting_for_player_selection')
        self.assertIn('available_players', round_data)


class MastermindViewsTest(TestCase):
    """Test mastermind API views"""
    
    def setUp(self):
        self.game_type = GameType.objects.create(name="Quiz Game")
        self.game_session = GameSession.objects.create()
        self.config = GameConfiguration.objects.create(
            game_session=self.game_session,
            game_type=self.game_type,
            num_rounds=1,
            round_type_sequence=['mastermind']
        )
        
        self.player = Player.objects.create(
            name="Test Player",
            game_session=self.game_session,
            specialist_subject="Science"
        )
        
    def test_round_status_view(self):
        """Test the round status API endpoint"""
        url = reverse('mastermind:round_status', kwargs={'game_code': self.game_session.game_code})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertEqual(data['game_code'], self.game_session.game_code)
        self.assertIn('round_data', data)
        self.assertEqual(data['round_data']['round_type'], 'mastermind')


class MastermindIntegrationTest(TestCase):
    """Test mastermind integration with main game system"""
    
    def setUp(self):
        self.game_type = GameType.objects.create(name="Quiz Game")
        self.game_session = GameSession.objects.create()
        self.config = GameConfiguration.objects.create(
            game_session=self.game_session,
            game_type=self.game_type,
            round_type_sequence=['mastermind']
        )
        
    def test_mastermind_round_handler_import(self):
        """Test that mastermind round handler can be imported from new location"""
        from game_sessions.round_handlers import get_round_handler
        
        handler = get_round_handler(self.game_session, 1, 'mastermind')
        
        # Should import from mastermind app, not game_sessions
        self.assertEqual(handler.__class__.__module__, 'mastermind.handlers')
        self.assertEqual(handler.ROUND_TYPE, 'mastermind')