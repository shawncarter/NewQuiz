"""
Round Management Service

Service layer for managing game rounds, separating business logic from models
and providing a clean interface for round progression and state management.
"""

import logging
from typing import Dict, Any, Optional
from django.utils import timezone
from django.core.cache import cache

logger = logging.getLogger(__name__)


class RoundService:
    """
    Service for managing round state and progression.
    
    Handles the lifecycle of rounds including starting, ending, and state management
    while delegating actual round data generation to RoundGeneratorService.
    """
    
    def __init__(self, game_session):
        self.game_session = game_session
        self.config = game_session.configuration
        self._generator = None
    
    @property
    def generator(self):
        """Lazy initialization of round generator"""
        if self._generator is None:
            from .round_generator_service import RoundGeneratorService
            self._generator = RoundGeneratorService(self.game_session)
        return self._generator
    
    def get_current_round_info(self) -> Optional[Dict[str, Any]]:
        """
        Get current round information.
        
        Returns:
            Dict containing current round data or None if no current round
        """
        if self.game_session.current_round_number == 0:
            return None
        
        # Use round handler system for current round info
        from game_sessions.round_handlers import get_round_handler
        round_handler = get_round_handler(self.game_session, self.game_session.current_round_number)
        return round_handler.get_round_info()
    
    def get_next_round_info(self) -> Optional[Dict[str, Any]]:
        """
        Get next round information without advancing the round counter.
        
        Returns:
            Dict containing next round data or None if game is complete
        """
        if self.is_game_complete():
            return None
        
        next_round_number = self.game_session.current_round_number + 1
        return self.generator.generate_round_data(next_round_number)
    
    def start_next_round(self) -> Dict[str, Any]:
        """
        Start the next round and update game state.
        
        Returns:
            Dict with success status and round info or error message
        """
        if self.game_session.status != 'active':
            return {'success': False, 'error': 'Game is not active'}
        
        # End current round if active
        if self.game_session.is_round_active:
            self.end_current_round()
        
        # Check if game is complete
        if self.is_game_complete():
            return self._finish_game()
        
        # Start new round
        return self._start_new_round()
    
    def end_current_round(self) -> Dict[str, Any]:
        """
        End the current round and update state.
        
        Returns:
            Dict with success status and results
        """
        if not self.game_session.is_round_active:
            return {'success': False, 'error': 'No active round to end'}
        
        # Update game state
        self.game_session.is_round_active = False
        self.game_session.save()
        
        # Clear any cached round state
        self.generator.clear_round_cache(self.game_session.current_round_number)
        
        return {'success': True, 'message': 'Round ended successfully'}
    
    def is_game_complete(self) -> bool:
        """Check if all rounds have been completed"""
        return self.game_session.current_round_number >= self.config.num_rounds
    
    def get_round_progress(self) -> Dict[str, Any]:
        """
        Get current game progress information.
        
        Returns:
            Dict with current round, total rounds, and completion status
        """
        return {
            'current_round': self.game_session.current_round_number,
            'total_rounds': self.config.num_rounds,
            'is_complete': self.is_game_complete(),
            'is_round_active': self.game_session.is_round_active,
            'rounds_remaining': max(0, self.config.num_rounds - self.game_session.current_round_number)
        }
    
    def restart_rounds(self) -> Dict[str, Any]:
        """
        Restart round progression for game restart.
        
        Returns:
            Dict with success status
        """
        # Reset round state
        self.game_session.current_round_number = 0
        self.game_session.is_round_active = False
        self.game_session.current_round_started_at = None
        
        # Clear all cached round data
        self.generator.clear_all_round_cache()
        
        # Clear used questions
        self.game_session.used_questions.clear()
        
        self.game_session.save()
        
        return {'success': True, 'message': 'Rounds restarted successfully'}
    
    def _start_new_round(self) -> Dict[str, Any]:
        """Internal method to start a new round"""
        try:
            # Increment round counter
            self.game_session.current_round_number += 1
            
            # Generate round data
            round_info = self.generator.generate_round_data(self.game_session.current_round_number)
            if not round_info:
                return {
                    'success': False, 
                    'error': f'Failed to generate round {self.game_session.current_round_number}'
                }
            
            # Update game state
            self.game_session.is_round_active = True
            self.game_session.current_round_started_at = timezone.now()
            self.game_session.save()
            
            # Update round info with current state
            round_info.update({
                'is_active': True,
                'time_remaining': self.config.round_time_seconds,
                'started_at': self.game_session.current_round_started_at
            })
            
            # Handle broadcasting and caching if requested
            self._handle_round_started_events(round_info)
            
            return {
                'success': True,
                'round_info': round_info,
                'message': f'Round {self.game_session.current_round_number} started'
            }
            
        except Exception as e:
            logger.error(f"Error starting round {self.game_session.current_round_number}: {e}")
            return {'success': False, 'error': 'Failed to start round'}
    
    def _finish_game(self) -> Dict[str, Any]:
        """Internal method to finish the game"""
        self.game_session.status = 'finished'
        self.game_session.finished_at = timezone.now()
        self.game_session.save()
        
        return {
            'success': True,
            'game_complete': True,
            'message': 'Game completed successfully'
        }
    
    def _handle_round_started_events(self, round_info: Dict[str, Any]):
        """Handle broadcasting and caching for round start events"""
        try:
            # Cache round state for faster access
            from game_sessions.cache_service import get_game_cache
            game_cache = get_game_cache(self.game_session.game_code)
            game_cache.cache_round_state(self.game_session.current_round_number, round_info)
            
            # Invalidate game state cache since round changed
            game_cache.invalidate_game_state()
            
            # Broadcast round started to all connected clients
            from game_sessions.websocket_utils import broadcast_round_started, start_timer_broadcast
            broadcast_round_started(self.game_session, round_info)
            
            # Start timer broadcasting (mastermind rounds handle their own timing)
            if round_info.get('round_type') != 'mastermind':
                start_timer_broadcast(self.game_session, round_info)
                
        except Exception as e:
            logger.warning(f"Failed to handle round started events: {e}")
            # Don't fail the round start for broadcasting issues