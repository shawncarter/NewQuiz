"""
Mastermind Round Handler

Simple integration layer between the existing round handler system
and the new mastermind service architecture.
"""

import logging
from typing import Dict, Any
from game_sessions.round_handlers import BaseRoundHandler
from .services import MastermindService

logger = logging.getLogger('mastermind')


class MastermindRoundHandler(BaseRoundHandler):
    """
    Simplified mastermind round handler that delegates to MastermindService.
    
    This maintains compatibility with the existing round handler system
    while using the new dedicated mastermind service for business logic.
    """
    
    ROUND_TYPE = 'mastermind'
    DISPLAY_NAME = 'Mastermind'
    
    def __init__(self, game_session, round_number: int):
        super().__init__(game_session, round_number)
        self.service = MastermindService(game_session)
        # Trigger question pre-generation when mastermind round is first created
        self._ensure_questions_pregenerated()
    
    def generate_round_data(self) -> Dict[str, Any]:
        """Generate mastermind round data using the dedicated service"""
        return self.service.get_round_data(self.round_number)
    
    def create_player_answer(self, player, answer_text: str):
        """
        Mastermind uses its own answer system, so this is a no-op.
        Answers are handled via the rapid-fire submission system.
        """
        # For compatibility with existing system, create a summary answer
        from players.models import PlayerAnswer
        
        return PlayerAnswer.objects.create(
            player=player,
            round_number=self.round_number,
            answer_text=f"Mastermind rapid-fire session",
            is_valid=True,
            points_awarded=0  # Will be updated by service
        )
    
    def perform_automatic_scoring(self, answers):
        """
        Mastermind handles scoring internally via the service.
        This is a no-op for compatibility.
        """
        logger.info(f"Mastermind scoring handled by service for {len(answers)} answers")
    
    def should_send_immediate_feedback(self) -> bool:
        """Mastermind provides immediate feedback via its own system"""
        return False  # Handled internally
    
    def supports_manual_validation(self) -> bool:
        """Mastermind rounds don't support manual validation"""
        return False
    
    def get_player_feedback_message(self, player_answer, is_correct: bool, points: int) -> str:
        """Generate feedback message for mastermind rounds"""
        return "Mastermind round completed - check your specialist subject performance!"
    
    # Mastermind-specific methods for WebSocket integration
    
    def select_player(self, player_id: int) -> Dict[str, Any]:
        """GM selects which player goes next"""
        return self.service.select_player(self.round_number, player_id)
    
    def player_ready_response(self, is_ready: bool) -> Dict[str, Any]:
        """Process player's ready response"""
        return self.service.player_ready_response(self.round_number, is_ready)
    
    def continue_to_next_player(self) -> Dict[str, Any]:
        """Move from player complete back to player selection"""
        return self.service.continue_to_next_player(self.round_number)
    
    def submit_rapid_fire_answers(self, player_id: int, answers: list) -> Dict[str, Any]:
        """Process submitted rapid-fire answers"""
        return self.service.submit_rapid_fire_answers(self.round_number, player_id, answers)
    
    def _ensure_questions_pregenerated(self):
        """
        Ensure questions are pre-generated for this mastermind round.
        This is called during initialization to minimize loading delays.
        """
        try:
            # Check if questions are already available
            validation_result = self.service.validate_question_readiness(self.round_number)
            
            if validation_result['success']:
                logger.info(f"Questions already available for mastermind round {self.round_number}")
                return
            
            # Pre-generate questions if needed
            logger.info(f"Pre-generating questions for mastermind round {self.round_number}")
            result = self.service.pregenerate_questions_for_round(self.round_number)
            
            if result['success']:
                logger.info(f"Successfully pre-generated {result['total_questions_generated']} questions")
            else:
                logger.warning(f"Question pre-generation had issues: {result.get('error', 'Unknown error')}")
                
        except Exception as e:
            logger.error(f"Error during question pre-generation: {e}")
            # Don't fail the round creation, just log the error