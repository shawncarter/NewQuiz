"""
End-to-End MasterMind Game Testing

Comprehensive tests for the full MasterMind game flow including:
- Specialist round flow (player selection → ready → 90s rapid-fire)
- Phase transitions (specialist → general knowledge) 
- General knowledge simultaneous play (all players, 120s timer)
- Question pre-generation and no-duplication logic
- Scoring for both phases (10 points per correct answer)
- WebSocket broadcasts for phase transitions
"""

import json
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from django.test import TestCase
from django.contrib.auth.models import AnonymousUser
from channels.testing import WebsocketCommunicator
from channels.db import database_sync_to_async

from game_sessions.models import GameSession, GameType, GameConfiguration
from players.models import Player
from mastermind.models import Subject, SpecialistQuestion, GeneralKnowledgeQuestion, MastermindRound, PlayerQuestionSet, MastermindAnswer
from mastermind.consumers import MastermindConsumer
from mastermind.services import MastermindService


class MastermindE2ETestCase(TestCase):
    """End-to-end tests for MasterMind game flow"""
    
    def setUp(self):
        """Set up test data for MasterMind game"""
        # Create game type and session
        self.game_type = GameType.objects.create(
            name="MasterMind Game",
            description="Specialist knowledge quiz"
        )
        
        self.game_session = GameSession.objects.create(
            game_code='MM2024',
            status='waiting'
        )
        
        # Create game configuration for mastermind
        self.config = GameConfiguration.objects.create(
            game_session=self.game_session,
            game_type=self.game_type,
            num_rounds=1,
            round_time_seconds=90,  # 90s for specialist, 120s for GK
            round_type_sequence=['mastermind']
        )
        
        # Create test subjects
        self.history_subject = Subject.objects.create(name='History', is_active=True)
        self.science_subject = Subject.objects.create(name='Science', is_active=True)
        
        # Create test players with specialist subjects
        self.player1 = Player.objects.create(
            game_session=self.game_session,
            name='Alice History',
            specialist_subject='History',
            is_connected=True,
            session_key='alice_session'
        )
        
        self.player2 = Player.objects.create(
            game_session=self.game_session,
            name='Bob Science', 
            specialist_subject='Science',
            is_connected=True,
            session_key='bob_session'
        )
        
        # Create sufficient test questions for both subjects
        self._create_test_questions()
        
        # Initialize MasterMind service
        self.mastermind_service = MastermindService(self.game_session)
    
    def _create_test_questions(self):
        """Create test questions for specialist and general knowledge phases"""
        # Create 25 History questions (more than 20 needed for buffer)
        for i in range(25):
            SpecialistQuestion.objects.create(
                subject=self.history_subject,
                question_text=f'History question {i+1}: What happened in {1900+i}?',
                choices=[f'Option A {i}', f'Option B {i}', f'Option C {i}', f'Option D {i}'],
                correct_answer=f'Option A {i}',
                difficulty='medium',
                is_ai_generated=False
            )
        
        # Create 25 Science questions
        for i in range(25):
            SpecialistQuestion.objects.create(
                subject=self.science_subject,
                question_text=f'Science question {i+1}: What is the formula for {["water", "salt", "sugar", "oxygen"][i%4]}?',
                choices=[f'Formula A {i}', f'Formula B {i}', f'Formula C {i}', f'Formula D {i}'],
                correct_answer=f'Formula A {i}',
                difficulty='medium',
                is_ai_generated=False
            )
        
        # Create 25 General Knowledge questions
        for i in range(25):
            GeneralKnowledgeQuestion.objects.create(
                question_text=f'General knowledge question {i+1}: What is the capital of {["France", "Germany", "Italy", "Spain"][i%4]}?',
                choices=[f'City A {i}', f'City B {i}', f'City C {i}', f'City D {i}'],
                correct_answer=f'City A {i}',
                difficulty='medium',
                is_ai_generated=False
            )

    def test_question_pre_generation_validation(self):
        """Test that questions are pre-generated and available before game starts"""
        # Test validation with sufficient questions
        validation_result = self.mastermind_service.validate_question_readiness()
        
        self.assertTrue(validation_result['success'], 
                       f"Question validation failed: {validation_result.get('errors', [])}")
        
        # Check specialist questions are available for both players
        history_count = SpecialistQuestion.objects.filter(subject__name='History').count()
        science_count = SpecialistQuestion.objects.filter(subject__name='Science').count()
        gk_count = GeneralKnowledgeQuestion.objects.count()
        
        self.assertGreaterEqual(history_count, 20, "Insufficient History questions")
        self.assertGreaterEqual(science_count, 20, "Insufficient Science questions") 
        self.assertGreaterEqual(gk_count, 20, "Insufficient General Knowledge questions")
        
        print(f"✅ Question validation passed: History={history_count}, Science={science_count}, GK={gk_count}")

    def test_no_question_duplication(self):
        """Test that questions are not duplicated within and across games"""
        # Get questions for first player's specialist round
        round_obj = self.mastermind_service.get_or_create_round(1)
        questions_alice = self.mastermind_service._get_specialist_questions(round_obj, self.player1)
        
        # Get questions for second player's specialist round  
        questions_bob = self.mastermind_service._get_specialist_questions(round_obj, self.player2)
        
        # Get general knowledge questions (same for all players)
        gk_questions = self.mastermind_service._get_general_knowledge_questions(round_obj)
        
        # Verify we got expected counts
        self.assertEqual(len(questions_alice), 20, "Alice should get 20 specialist questions")
        self.assertEqual(len(questions_bob), 20, "Bob should get 20 specialist questions")
        self.assertEqual(len(gk_questions), 20, "Should get 20 general knowledge questions")
        
        # Verify no duplicates within each set
        alice_ids = [q.id for q in questions_alice]
        bob_ids = [q.id for q in questions_bob]
        gk_ids = [q.id for q in gk_questions]
        
        self.assertEqual(len(alice_ids), len(set(alice_ids)), "Alice's questions contain duplicates")
        self.assertEqual(len(bob_ids), len(set(bob_ids)), "Bob's questions contain duplicates")
        self.assertEqual(len(gk_ids), len(set(gk_ids)), "General knowledge questions contain duplicates")
        
        # Verify Alice and Bob get different subjects (no cross-contamination)
        alice_subjects = {q.subject.name for q in questions_alice}
        bob_subjects = {q.subject.name for q in questions_bob}
        
        self.assertEqual(alice_subjects, {'History'}, "Alice should only get History questions")
        self.assertEqual(bob_subjects, {'Science'}, "Bob should only get Science questions")
        
        print(f"✅ No duplication test passed: Alice={len(alice_ids)} History, Bob={len(bob_ids)} Science, GK={len(gk_ids)}")

    def test_specialist_round_scoring(self):
        """Test scoring for specialist rounds (10 points per correct answer)"""
        # First set up the round properly
        round_obj = self.mastermind_service.get_or_create_round(1)
        
        # Select player and set up questions
        self.mastermind_service.select_player(1, self.player1.id)
        self.mastermind_service.player_ready_response(1, True)
        
        # Get the actual pre-loaded questions to use correct question IDs
        question_set = PlayerQuestionSet.objects.get(
            mastermind_round=round_obj,
            player=self.player1
        )
        
        # Create answers using the actual question data structure expected by the service
        alice_answers = []
        questions = question_set.questions[:4]  # Use first 4 questions for test
        
        for i, question in enumerate(questions):
            # Mix correct and incorrect answers
            is_correct = i != 2  # Make 3rd answer incorrect
            alice_answers.append({
                'selected_choice': question['correct_answer'] if is_correct else 'Wrong Answer',
                'response_time_ms': 1000 + (i * 100)
            })
        
        # Submit answers and check scoring
        initial_score = self.player1.current_score
        result = self.mastermind_service.submit_rapid_fire_answers(
            1, self.player1.id, alice_answers
        )
        
        self.assertTrue(result['success'], f"Answer submission failed: {result.get('error', 'Unknown error')}")
        
        # Refresh player to get updated score
        self.player1.refresh_from_db()
        expected_score = initial_score + (3 * 10)  # 3 correct answers × 10 points
        
        self.assertEqual(self.player1.current_score, expected_score,
                        f"Expected score {expected_score}, got {self.player1.current_score}")
        
        print(f"✅ Specialist scoring test passed: {initial_score} → {self.player1.current_score} (+{3*10} points)")

    def test_phase_transition_specialist_to_general_knowledge(self):
        """Test transition from specialist phase to general knowledge phase"""
        round_obj = self.mastermind_service.get_or_create_round(1)
        
        # Initially should be in waiting_for_player_selection state
        self.assertEqual(round_obj.state, 'waiting_for_player_selection')
        self.assertEqual(round_obj.current_phase, 'specialist')
        
        # Complete specialist rounds for both players using proper flow
        self._complete_specialist_round_for_player(self.player1)
        self._complete_specialist_round_for_player(self.player2)
        
        # After both players complete specialist rounds, should transition to general knowledge
        round_obj.refresh_from_db()
        
        # Check that we've transitioned to general knowledge phase
        self.assertEqual(round_obj.current_phase, 'general_knowledge',
                        f"Expected general_knowledge phase, got {round_obj.current_phase}")
        self.assertIn(round_obj.state, ['all_complete', 'general_knowledge_ready', 'general_knowledge'],
                     f"Expected general knowledge state, got {round_obj.state}")
        
        print(f"✅ Phase transition test passed: specialist → general_knowledge (state: {round_obj.state})")

    def test_general_knowledge_simultaneous_play(self):
        """Test general knowledge phase with simultaneous play for all players"""
        # First complete specialist phase for both players
        self._complete_specialist_phase()
        
        round_obj = MastermindRound.objects.get(game_session=self.game_session, round_number=1)
        self.assertEqual(round_obj.current_phase, 'general_knowledge')
        
        # Start general knowledge round for all players
        result = self.mastermind_service.start_general_knowledge_round(1)
        self.assertTrue(result['success'], f"Failed to start GK round: {result.get('error')}")
        
        round_obj.refresh_from_db()
        self.assertEqual(round_obj.state, 'general_knowledge_active')
        
        # Both players submit answers simultaneously (same questions, different answers)
        gk_questions = self.mastermind_service._get_general_knowledge_questions(round_obj)
        self.assertEqual(len(gk_questions), 20, "Should have 20 GK questions")
        
        # Alice answers (15 correct out of 20)
        alice_gk_answers = []
        for i, question in enumerate(gk_questions):
            is_correct = i < 15  # First 15 correct, last 5 incorrect
            alice_gk_answers.append({
                'selected_choice': question.correct_answer if is_correct else 'Wrong Answer',
                'response_time_ms': 1500 + (i * 50)
            })
        
        # Bob answers (12 correct out of 20) 
        bob_gk_answers = []
        for i, question in enumerate(gk_questions):
            is_correct = i < 12  # First 12 correct, last 8 incorrect
            bob_gk_answers.append({
                'selected_choice': question.correct_answer if is_correct else 'Wrong Answer',
                'response_time_ms': 1800 + (i * 60)
            })
        
        # Submit answers for both players
        # Alice should have 200 points from specialist phase, Bob should have 200 points
        self.player1.refresh_from_db()
        self.player2.refresh_from_db()
        alice_initial_score = self.player1.current_score  # Should be 200 after specialist
        bob_initial_score = self.player2.current_score    # Should be 200 after specialist
        
        result_alice = self.mastermind_service.submit_rapid_fire_answers(1, self.player1.id, alice_gk_answers)
        result_bob = self.mastermind_service.submit_rapid_fire_answers(1, self.player2.id, bob_gk_answers)
        
        self.assertTrue(result_alice['success'], "Alice's GK answers failed to submit")
        self.assertTrue(result_bob['success'], "Bob's GK answers failed to submit")
        
        # Check final scores
        self.player1.refresh_from_db()
        self.player2.refresh_from_db()
        
        alice_expected = alice_initial_score + (15 * 10)  # 15 correct × 10 points
        bob_expected = bob_initial_score + (12 * 10)      # 12 correct × 10 points
        
        self.assertEqual(self.player1.current_score, alice_expected,
                        f"Alice expected {alice_expected}, got {self.player1.current_score}. Initial was {alice_initial_score}")
        self.assertEqual(self.player2.current_score, bob_expected,
                        f"Bob expected {bob_expected}, got {self.player2.current_score}. Initial was {bob_initial_score}")
        
        print(f"✅ General knowledge simultaneous play test passed: Alice {alice_initial_score}+{15*10}={alice_expected}, Bob {bob_initial_score}+{12*10}={bob_expected}")

    def test_full_mastermind_game_flow(self):
        """Test complete MasterMind game flow from start to finish"""
        initial_scores = {
            self.player1.id: self.player1.current_score,
            self.player2.id: self.player2.current_score
        }
        
        # Phase 1: Specialist Rounds
        print("🎯 Starting Phase 1: Specialist Rounds")
        
        # Alice's specialist round (History)
        round_obj = self.mastermind_service.get_or_create_round(1)
        self.mastermind_service.select_player(1, self.player1.id)
        self.mastermind_service.player_ready_response(1, True)
        
        # Get Alice's pre-loaded questions and create answers (18/20 correct)
        alice_question_set = PlayerQuestionSet.objects.get(
            mastermind_round=round_obj, player=self.player1
        )
        alice_specialist_answers = []
        for i, question in enumerate(alice_question_set.questions):
            is_correct = i < 18  # First 18 correct, last 2 incorrect
            alice_specialist_answers.append({
                'selected_choice': question['correct_answer'] if is_correct else 'Wrong Answer',
                'response_time_ms': 1200 + (i * 100)
            })
        self.mastermind_service.submit_rapid_fire_answers(1, self.player1.id, alice_specialist_answers)
        
        # Continue to Bob
        self.mastermind_service.continue_to_next_player(1)
        self.mastermind_service.select_player(1, self.player2.id)
        self.mastermind_service.player_ready_response(1, True)
        
        # Get Bob's pre-loaded questions and create answers (16/20 correct)
        bob_question_set = PlayerQuestionSet.objects.get(
            mastermind_round=round_obj, player=self.player2
        )
        bob_specialist_answers = []
        for i, question in enumerate(bob_question_set.questions):
            is_correct = i < 16  # First 16 correct, last 4 incorrect
            bob_specialist_answers.append({
                'selected_choice': question['correct_answer'] if is_correct else 'Wrong Answer',
                'response_time_ms': 1300 + (i * 90)
            })
        self.mastermind_service.submit_rapid_fire_answers(1, self.player2.id, bob_specialist_answers)
        
        # Phase 2: General Knowledge Round
        print("🎯 Starting Phase 2: General Knowledge Round")
        
        round_obj.refresh_from_db()
        self.assertEqual(round_obj.current_phase, 'general_knowledge')
        
        self.mastermind_service.start_general_knowledge_round(1)
        
        # Both players answer general knowledge simultaneously
        gk_questions = self.mastermind_service._get_general_knowledge_questions(round_obj)
        
        # Alice gets 14/20 correct in GK
        alice_gk_answers = []
        for i, question in enumerate(gk_questions):
            is_correct = i < 14
            alice_gk_answers.append({
                'selected_choice': question.correct_answer if is_correct else 'Wrong Answer',
                'response_time_ms': 1400 + (i * 75)
            })
        
        # Bob gets 13/20 correct in GK
        bob_gk_answers = []
        for i, question in enumerate(gk_questions):
            is_correct = i < 13
            bob_gk_answers.append({
                'selected_choice': question.correct_answer if is_correct else 'Wrong Answer',
                'response_time_ms': 1600 + (i * 80)
            })
        
        self.mastermind_service.submit_rapid_fire_answers(1, self.player1.id, alice_gk_answers)
        self.mastermind_service.submit_rapid_fire_answers(1, self.player2.id, bob_gk_answers)
        
        # Complete the general knowledge round
        completion_result = self.mastermind_service.complete_general_knowledge_round(1)
        self.assertTrue(completion_result['success'])
        self.assertTrue(completion_result['completed'])
        
        # Verify final scores
        self.player1.refresh_from_db()
        self.player2.refresh_from_db()
        
        alice_total_correct = 18 + 14  # Specialist + GK
        bob_total_correct = 16 + 13    # Specialist + GK
        
        alice_expected = initial_scores[self.player1.id] + (alice_total_correct * 10)
        bob_expected = initial_scores[self.player2.id] + (bob_total_correct * 10)
        
        self.assertEqual(self.player1.current_score, alice_expected,
                        f"Alice final score: expected {alice_expected}, got {self.player1.current_score}")
        self.assertEqual(self.player2.current_score, bob_expected,
                        f"Bob final score: expected {bob_expected}, got {self.player2.current_score}")
        
        # Verify round completion
        round_obj.refresh_from_db()
        self.assertEqual(round_obj.state, 'all_complete')
        
        print(f"✅ Full game flow test passed!")
        print(f"   Alice: {alice_total_correct}/40 correct = {alice_expected} points")
        print(f"   Bob: {bob_total_correct}/40 correct = {bob_expected} points")

    def _complete_specialist_phase(self):
        """Helper method to complete specialist phase for both players"""
        self._complete_specialist_round_for_player(self.player1)
        self._complete_specialist_round_for_player(self.player2)
    
    def _complete_specialist_round_for_player(self, player):
        """Helper to complete a specialist round for a specific player"""
        round_obj = self.mastermind_service.get_or_create_round(1)
        
        # Select player and confirm ready
        self.mastermind_service.select_player(1, player.id)
        self.mastermind_service.player_ready_response(1, True)
        
        # Get pre-loaded questions
        question_set = PlayerQuestionSet.objects.get(
            mastermind_round=round_obj,
            player=player
        )
        
        # Create correct answers for all questions
        answers = []
        for question in question_set.questions:
            answers.append({
                'selected_choice': question['correct_answer'],
                'response_time_ms': 1000
            })
        
        # Submit answers
        self.mastermind_service.submit_rapid_fire_answers(1, player.id, answers)
        
        # Continue to next player if not the last one
        if round_obj.state == 'player_complete':
            self.mastermind_service.continue_to_next_player(1)


class MastermindWebSocketE2ETest(TestCase):
    """End-to-end WebSocket tests for MasterMind game flow"""
    
    def setUp(self):
        """Set up test data for WebSocket testing"""
        # Create game session and players (reuse setup from above)
        self.game_type = GameType.objects.create(name="MasterMind Game")
        self.game_session = GameSession.objects.create(game_code='WS2024', status='active')
        self.config = GameConfiguration.objects.create(
            game_session=self.game_session,
            game_type=self.game_type,
            num_rounds=1,
            round_type_sequence=['mastermind']
        )
        
        self.player1 = Player.objects.create(
            game_session=self.game_session,
            name='WebSocket Player 1',
            specialist_subject='History',
            is_connected=True
        )
        
        # Create test questions
        history_subject = Subject.objects.create(name='History')
        for i in range(25):
            SpecialistQuestion.objects.create(
                subject=history_subject,
                question_text=f'WS History question {i+1}',
                choices=['A', 'B', 'C', 'D'],
                correct_answer='A'
            )

    async def test_websocket_connection_and_initial_state(self):
        """Test WebSocket connection and initial game state broadcast"""
        communicator = WebsocketCommunicator(MastermindConsumer.as_asgi(), f"/ws/mastermind/WS2024/")
        communicator.scope['user'] = AnonymousUser()
        
        connected, subprotocol = await communicator.connect()
        self.assertTrue(connected, "WebSocket connection failed")
        
        # Should receive initial mastermind state
        response = await communicator.receive_json_from()
        
        self.assertEqual(response.get('type'), 'mastermind_state')
        self.assertIn('round_data', response)
        self.assertIn('players', response)
        self.assertEqual(response['game_code'], 'WS2024')
        
        await communicator.disconnect()
        print("✅ WebSocket connection and initial state test passed")

    async def test_websocket_player_selection_broadcast(self):
        """Test WebSocket broadcast when GM selects a player"""
        communicator = WebsocketCommunicator(MastermindConsumer.as_asgi(), f"/ws/mastermind/WS2024/")
        communicator.scope['user'] = AnonymousUser()
        
        connected, subprotocol = await communicator.connect()
        self.assertTrue(connected)
        
        # Skip initial state message
        await communicator.receive_json_from()
        
        # Send player selection message
        await communicator.send_json_to({
            'type': 'select_player',
            'player_id': self.player1.id,
            'round_number': 1
        })
        
        # Should receive player selection broadcast
        response = await communicator.receive_json_from()
        
        self.assertEqual(response.get('type'), 'player_selected')
        self.assertIn('result', response)
        self.assertEqual(response.get('round_number'), 1)
        
        await communicator.disconnect()
        print("✅ WebSocket player selection broadcast test passed")

    async def test_websocket_phase_transition_broadcast(self):
        """Test WebSocket broadcast for phase transitions"""
        # This would require a more complex setup to simulate completing specialist phase
        # and transitioning to general knowledge - implementation would be similar to above
        # but testing the specific broadcast messages for phase transitions
        print("✅ WebSocket phase transition broadcast test (placeholder - would test specialist→GK transition)")

    def test_websocket_sync_wrapper(self):
        """Wrapper to run async WebSocket tests"""
        asyncio.run(self.test_websocket_connection_and_initial_state())
        asyncio.run(self.test_websocket_player_selection_broadcast())
        asyncio.run(self.test_websocket_phase_transition_broadcast())


if __name__ == '__main__':
    # Run tests with more verbose output
    import unittest
    unittest.main(verbosity=2)