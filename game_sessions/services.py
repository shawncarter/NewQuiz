"""
Business Logic Services for Quiz Game

This module contains service classes that encapsulate the core business logic
of the quiz game, separating it from the presentation layer (views).

Services handle:
- Game state management
- Round progression 
- Player management
- Scoring logic
- Data persistence
"""

import logging
from typing import Dict, List, Any
from django.utils import timezone
from django.core.cache import cache
from django.db import transaction

from .models import GameSession
from players.models import Player, PlayerAnswer
from .round_handlers import get_round_handler
from .websocket_utils import broadcast_to_game, broadcast_round_started, broadcast_round_ended, broadcast_player_results, start_timer_broadcast
from .cache_service import get_game_cache, PlayerCacheService

logger = logging.getLogger('game_sessions')


class GameService:
    """Service class for game-related business logic"""
    
    def __init__(self, game_session: GameSession):
        self.game_session = game_session
        self.config = getattr(game_session, 'configuration', None)
    
    def start_game(self) -> Dict[str, Any]:
        """Start the game session"""
        if self.game_session.status != 'waiting':
            return {'success': False, 'error': 'Game is not in waiting state'}
        
        if self.game_session.player_count == 0:
            return {'success': False, 'error': 'No players have joined yet'}
        
        # Update game state
        self.game_session.status = 'active'
        self.game_session.started_at = timezone.now()
        self.game_session.save()
        
        # Generate rounds for the game (if needed)
        self.game_session.generate_rounds()
        
        # Broadcast game activation to all connected clients
        broadcast_to_game(self.game_session.game_code, 'game_started', {
            'game_status': 'active',
            'message': 'Game has started! Get ready for the first round.',
            'player_count': self.game_session.player_count
        })
        
        return {'success': True, 'message': 'Game started! Ready for first round.'}
    
    def start_round(self) -> Dict[str, Any]:
        """Start the next round using counter system"""
        if self.game_session.status != 'active':
            return {'success': False, 'error': 'Game is not active'}
        
        # End current round if active
        if self.game_session.is_round_active:
            self.game_session.is_round_active = False
            self.game_session.save()
        
        # Check if game is complete
        if self.game_session.current_round_number >= self.config.num_rounds:
            return self._finish_game()
        
        # Start new round
        return self._start_round_internal()
    
    def end_round(self) -> Dict[str, Any]:
        """End the current round and calculate scores with caching optimizations"""
        if not self.game_session.is_round_active:
            return {'success': False, 'error': 'No active round'}
        
        # End the round
        self.game_session.is_round_active = False
        self.game_session.save()
        
        # Get current round info (try cache first)
        game_cache = get_game_cache(self.game_session.game_code)
        cached_round_state = game_cache.get_cached_round_state(self.game_session.current_round_number)
        
        if cached_round_state and cached_round_state.get('round_info'):
            round_info = cached_round_state['round_info']
        else:
            # Fallback to database query
            round_info = self.game_session.get_current_round_info()
            if not round_info:
                return {'success': False, 'error': 'Could not get round information'}
        
        # Mark round as ended in cache
        game_cache.mark_round_ended(self.game_session.current_round_number)
        
        # Process cached answers into database with bulk operations
        self._process_cached_answers()
        
        # Get all answers for this round from database
        answers = self._get_round_answers()
        
        # Perform automatic scoring
        self._perform_scoring(answers)
        
        # Send feedback to players if needed
        self._send_player_feedback(round_info, answers)
        
        # Prepare response data
        answer_data = self._format_answer_data(answers)
        
        # Invalidate game state cache since round ended
        game_cache.invalidate_game_state()
        
        # Broadcast round ended to all connected clients
        broadcast_round_ended(self.game_session, round_info, answer_data)
        
        response_data = {
            'success': True,
            'answers': answer_data,
            'round_number': self.game_session.current_round_number,
            'round_type': round_info['round_type'],
            'is_final_round': self.game_session.current_round_number >= self.config.num_rounds
        }
        
        # Add correct answer for multiple choice questions
        if round_info['round_type'] == 'multiple_choice':
            response_data['correct_answer'] = round_info.get('correct_answer')
        
        return response_data
    
    def restart_game(self) -> Dict[str, Any]:
        """Restart the game session for development/testing"""
        if self.game_session.status not in ['active', 'finished']:
            return {'success': False, 'error': 'Game can only be restarted when active or finished'}
        
        # Use existing restart logic
        self.game_session.restart_game()
        
        # Clean up duplicate players and reset scores
        self._cleanup_players_on_restart()
        
        # Broadcast game restart
        self._broadcast_restart()
        
        return {'success': True, 'message': 'Game restarted successfully.'}
    
    # Private helper methods
    
    def _start_round_internal(self) -> Dict[str, Any]:
        """Internal function to start any round using round handler system with caching"""
        # Increment round number
        self.game_session.current_round_number += 1
        self.game_session.is_round_active = True
        self.game_session.current_round_started_at = timezone.now()
        self.game_session.save()
        
        # Get the round handler for this round
        round_handler = get_round_handler(self.game_session, self.game_session.current_round_number)
        
        # Get the round info from the handler
        round_info = round_handler.get_round_info()
        if not round_info:
            return {'success': False, 'error': 'Could not generate round information'}
        
        # Cache round state for faster access
        game_cache = get_game_cache(self.game_session.game_code)
        game_cache.cache_round_state(self.game_session.current_round_number, round_info)
        
        # Invalidate game state cache since round changed
        game_cache.invalidate_game_state()
        
        # Broadcast round started to all connected clients
        broadcast_round_started(self.game_session, round_info)
        
        # Start timer broadcasting (but not for MasterMind rounds - they start timer when player is ready)
        if round_info.get('round_type') != 'mastermind':
            from .websocket_utils import start_timer_broadcast
            start_timer_broadcast(self.game_session, round_info)
        
        import time
        
        # Build response with round-specific data
        response_data = {
            'success': True,
            'round_number': round_info['round_number'],
            'time_seconds': self.config.round_time_seconds,
            'started_at': time.time(),  # Current timestamp for synchronization
            'round_type': round_info['round_type'],
        }
        
        # Add round type specific data
        if round_info['round_type'] == 'flower_fruit_veg':
            response_data.update({
                'prompt': round_info.get('prompt'),
                'letter': round_info.get('prompt_letter'),
                'category': round_info.get('category', {}).name if hasattr(round_info.get('category'), 'name') else str(round_info.get('category', '')),
            })
        elif round_info['round_type'] == 'multiple_choice':
            response_data.update({
                'question_text': round_info.get('question_text'),
                'choices': round_info.get('choices'),
                'category': round_info.get('category'),
                'correct_answer': round_info.get('correct_answer'),  # Include for GM screen
            })
        
        return response_data
    
    def _finish_game(self) -> Dict[str, Any]:
        """Finish the game and return final scores"""
        final_scores = self.game_session.get_final_scores()
        self.game_session.status = 'finished'
        self.game_session.finished_at = timezone.now()
        self.game_session.save()
        
        # Broadcast game completion to all connected clients
        broadcast_to_game(self.game_session.game_code, 'game_complete', {
            'game_status': 'finished',
            'final_scores': final_scores,
            'message': 'Game completed! Here are the final scores.'
        })
        
        return {
            'success': True,
            'status': 'game_complete',
            'final_scores': final_scores,
            'message': 'Game completed! Here are the final scores.'
        }
    
    def _process_cached_answers(self):
        """Process cached answers into database PlayerAnswer objects with bulk operations"""
        game_cache = get_game_cache(self.game_session.game_code)
        cached_answers = game_cache.get_cached_answers(self.game_session.current_round_number)
        
        if not cached_answers:
            logger.debug(f"No cached answers found for game {self.game_session.game_code} round {self.game_session.current_round_number}")
            return
        
        # Get all connected players in one query
        player_ids = [int(pid) for pid in cached_answers.keys() if pid.isdigit()]
        connected_players = {
            p.id: p for p in Player.objects.filter(
                id__in=player_ids, 
                game_session=self.game_session, 
                is_connected=True
            ).select_related('game_session')
        }
        
        # Get existing answers to avoid duplicates
        existing_answers = set(
            PlayerAnswer.objects.filter(
                player_id__in=player_ids,
                round_number=self.game_session.current_round_number
            ).values_list('player_id', flat=True)
        )
        
        # Prepare bulk answer creation
        answers_to_create = []
        round_handler = get_round_handler(self.game_session, self.game_session.current_round_number)
        
        for player_id_str, answer_text in cached_answers.items():
            try:
                player_id = int(player_id_str)
                player = connected_players.get(player_id)
                
                if player and player_id not in existing_answers and answer_text.strip():
                    # Use round handler to prepare PlayerAnswer data
                    answer_obj = round_handler.create_player_answer(player, answer_text.strip())
                    if answer_obj:  # Some handlers return the object, others save directly
                        answers_to_create.append(answer_obj)
                    logger.info(f"Processed answer for player {player.name}: {answer_text[:20]}...")
                    
            except (ValueError, KeyError) as e:
                logger.warning(f"Could not process answer for player_id {player_id_str}: {e}")
        
        # Bulk create if we have answers to create (some round handlers save directly)
        if answers_to_create:
            try:
                PlayerAnswer.objects.bulk_create(answers_to_create, ignore_conflicts=True)
                logger.info(f"Bulk created {len(answers_to_create)} PlayerAnswer objects")
            except Exception as e:
                logger.error(f"Failed to bulk create answers: {e}")
                # Fallback to individual creation
                for answer in answers_to_create:
                    try:
                        answer.save()
                    except Exception:
                        pass
        
        # Clear the cache for this round only after successful processing
        game_cache.clear_round_answers(self.game_session.current_round_number)
        logger.info(f"Processed {len(cached_answers)} cached answers into database")
    
    def _get_round_answers(self):
        """Get all answers for this round from database"""
        return PlayerAnswer.objects.filter(
            player__game_session=self.game_session,
            player__is_connected=True,
            round_number=self.game_session.current_round_number
        ).select_related('player').order_by('?')  # Random order
    
    def _perform_scoring(self, answers):
        """Perform automatic scoring using round handler system"""
        if not answers:
            return
        
        round_handler = get_round_handler(self.game_session, self.game_session.current_round_number)
        round_handler.perform_automatic_scoring(answers)
    
    def _send_player_feedback(self, round_info, answers):
        """Send individual results to each player based on round handler behavior"""
        round_handler = get_round_handler(self.game_session, self.game_session.current_round_number)
        
        if round_handler.should_send_immediate_feedback():
            broadcast_player_results(self.game_session, round_info, answers)
    
    def _format_answer_data(self, answers) -> List[Dict[str, Any]]:
        """Format answers for response"""
        answer_data = []
        for answer in answers:
            answer_data.append({
                'player_name': answer.player.name,
                'answer_text': answer.answer_text,
                'points_awarded': answer.points_awarded,
                'is_valid': answer.is_valid,
                'is_unique': getattr(answer, 'is_unique', False),
            })
        return answer_data
    
    def _cleanup_players_on_restart(self):
        """Clean up duplicate players and reset scores on restart"""
        # Clean up any duplicate players (keep the first occurrence of each name)
        seen_names = set()
        players_to_keep = []
        players_to_remove = []
        
        for player in self.game_session.players.all().order_by('joined_at'):
            if player.name in seen_names:
                players_to_remove.append(player)
            else:
                seen_names.add(player.name)
                players_to_keep.append(player)
        
        # Remove duplicates
        for duplicate_player in players_to_remove:
            logger.info(f"Removing duplicate player {duplicate_player.name} (id={duplicate_player.id}) during restart")
            duplicate_player.delete()
        
        # Reset scores for remaining players and ensure they're connected
        for player in players_to_keep:
            player.current_score = 0
            player.correct_answer_streak = 0
            player.is_connected = True
            player.save()
    
    def _broadcast_restart(self):
        """Broadcast game restart to all connected clients"""
        import time
        import threading
        
        # First broadcast - immediate restart notification
        broadcast_to_game(self.game_session.game_code, 'game_update', {
            'game_status': 'waiting',
            'player_count': self.game_session.players.count(),
            'message': 'Game restarted! Ready for next game.',
            'current_round': None,
            'restart_timestamp': int(time.time())
        })
        
        # Second broadcast after short delay to ensure delivery
        def delayed_broadcast():
            time.sleep(0.5)
            broadcast_to_game(self.game_session.game_code, 'game_restart_confirmation', {
                'game_status': 'waiting',
                'player_count': self.game_session.players.count(),
                'message': 'Game restarted! Please return to lobby if you haven\'t already.',
                'force_redirect': True,
                'restart_timestamp': int(time.time())
            })
        
        thread = threading.Thread(target=delayed_broadcast)
        thread.daemon = True
        thread.start()

    def mastermind_select_player(self, player_id: int) -> Dict[str, Any]:
        """GM selects a player for mastermind round"""
        if self.game_session.current_round_number == 0:
            return {'success': False, 'error': 'No active round'}
        
        from .round_handlers import get_round_handler
        round_handler = get_round_handler(self.game_session, self.game_session.current_round_number)
        
        if round_handler.ROUND_TYPE != 'mastermind':
            return {'success': False, 'error': 'Not a mastermind round'}
        
        if hasattr(round_handler, 'select_player'):
            result = round_handler.select_player(player_id)
            if result['success']:
                # Broadcast updated round data
                round_info = round_handler.get_round_info()
                broadcast_to_game(self.game_session.game_code, 'round_update', round_info)
            return result
        else:
            return {'success': False, 'error': 'Round handler does not support player selection'}
    
    def mastermind_ready_response(self, is_ready: bool) -> Dict[str, Any]:
        """Process GM's ready response for mastermind round"""
        if self.game_session.current_round_number == 0:
            return {'success': False, 'error': 'No active round'}
        
        from .round_handlers import get_round_handler
        round_handler = get_round_handler(self.game_session, self.game_session.current_round_number)
        
        if round_handler.ROUND_TYPE != 'mastermind':
            return {'success': False, 'error': 'Not a mastermind round'}
        
        if hasattr(round_handler, 'player_ready_response'):
            result = round_handler.player_ready_response(is_ready)
            if result['success']:
                # Broadcast updated round data
                round_info = round_handler.get_round_info()
                
                # If starting to play, send round_started instead of round_update for player interfaces
                if round_info.get('state') == 'playing':
                    from .websocket_utils import broadcast_round_started
                    broadcast_round_started(self.game_session, round_info)
                    start_timer_broadcast(self.game_session, round_info, mastermind_duration=90)
                else:
                    # For other state changes, send round_update (GM screen only)
                    broadcast_to_game(self.game_session.game_code, 'round_update', round_info)
                    
            return result
        else:
            return {'success': False, 'error': 'Round handler does not support ready response'}
    
    def mastermind_continue_to_next_player(self) -> Dict[str, Any]:
        """GM continues from player complete to next player selection"""
        if self.game_session.current_round_number == 0:
            return {'success': False, 'error': 'No active round'}
        
        from .round_handlers import get_round_handler
        round_handler = get_round_handler(self.game_session, self.game_session.current_round_number)
        
        if round_handler.ROUND_TYPE != 'mastermind':
            return {'success': False, 'error': 'Not a mastermind round'}
        
        if hasattr(round_handler, 'continue_to_next_player'):
            result = round_handler.continue_to_next_player()
            if result['success']:
                # Broadcast updated round data
                round_info = round_handler.get_round_info()
                broadcast_to_game(self.game_session.game_code, 'round_update', round_info)
            return result
        else:
            return {'success': False, 'error': 'Round handler does not support continue to next player'}


class PlayerService:
    """Service class for player-related business logic"""
    
    @staticmethod
    def join_game(game_code: str, player_name: str, specialist_subject: str = None) -> Dict[str, Any]:
        """Handle player joining a game session"""
        from .models import GameSession
        
        # Validate input
        if not game_code or not player_name:
            return {'success': False, 'error': 'Please provide both game code and your name.'}
        
        # Find game session
        try:
            game_session = GameSession.objects.get(game_code=game_code.upper())
        except GameSession.DoesNotExist:
            return {'success': False, 'error': 'Game not found. Please check the game code.'}
        
        # Check if game can be joined
        if not game_session.can_join:
            return {'success': False, 'error': 'Cannot join this game. It may be full or already started.'}
        
        # Check for existing player (reconnection)
        existing_player = Player.objects.filter(
            name=player_name,
            game_session=game_session
        ).first()
        
        if existing_player:
            # Reconnect existing player and update specialist subject if provided
            existing_player.is_connected = True
            if specialist_subject and specialist_subject.strip():
                existing_player.specialist_subject = specialist_subject.strip()
            existing_player.save()
            player = existing_player
            logger.info(f"Player {player_name} reconnected to game {game_code}")
        else:
            # Create new player
            player = Player.objects.create(
                name=player_name,
                game_session=game_session,
                specialist_subject=specialist_subject.strip() if specialist_subject else None,
                session_key=None  # Not using sessions for now
            )
            logger.info(f"Player {player_name} created for game {game_code} with specialist subject: {specialist_subject}")
        
        # Pre-generate specialist questions if player has a specialist subject
        if player.specialist_subject and player.specialist_subject.strip():
            PlayerService._ensure_specialist_questions_async(player.specialist_subject.strip())
        
        # Broadcast player join to all connected clients
        PlayerService._broadcast_player_join(game_session, player)
        
        return {
            'success': True, 
            'message': f'Joined game {game_code} as {player_name}!',
            'player': player,
            'game_session': game_session
        }
    
    @staticmethod
    def _ensure_specialist_questions_async(specialist_subject: str):
        """Asynchronously ensure we have enough specialist questions for MasterMind rounds"""
        from .ai_questions import generate_specialist_questions
        from .models import MultipleChoiceQuestion
        from django.core.cache import cache
        import threading
        
        # Check if already generating for this subject
        generation_key = f'generating_specialist_{specialist_subject}'
        if cache.get(generation_key):
            logger.info(f"Already generating questions for {specialist_subject}")
            return
        
        # Check if we have enough questions
        question_count = MultipleChoiceQuestion.objects.filter(
            category=specialist_subject,
            is_specialist=True
        ).count()
        
        if question_count < 25:  # Need 25 questions for rapid-fire
            logger.info(f"Starting background generation of specialist questions for {specialist_subject}")
            
            # Mark as generating
            cache.set(generation_key, True, timeout=300)  # 5 minutes
            
            def generate_questions():
                try:
                    generate_specialist_questions(specialist_subject, target_count=25)
                    logger.info(f"Completed background generation for {specialist_subject}")
                except Exception as e:
                    logger.error(f"Failed to generate questions for {specialist_subject}: {e}")
                finally:
                    cache.delete(generation_key)
            
            # Start background thread
            thread = threading.Thread(target=generate_questions)
            thread.daemon = True
            thread.start()
        else:
            logger.info(f"Already have {question_count} questions for {specialist_subject}")
    
    @staticmethod
    def _broadcast_player_join(game_session: GameSession, player: Player):
        """Broadcast player join to all connected clients with caching"""
        # Get connected players data efficiently
        connected_players = game_session.players.filter(is_connected=True).order_by('joined_at')
        player_count = connected_players.count()
        logger.info(f"Player {player.name} joined game {game_session.game_code}. Total players: {player_count}")
        
        # Build players data for broadcast and cache
        players_data = []
        for p in connected_players:
            players_data.append({
                'id': p.id,
                'name': p.name,
                'joined_at': p.joined_at.strftime('%H:%M:%S'),
                'total_score': p.current_score,
            })
        
        # Cache the game state and connected players
        game_cache = get_game_cache(game_session.game_code)
        game_cache.cache_game_state(game_session, players_data)
        PlayerCacheService.cache_connected_players(game_session.game_code, players_data)
        
        broadcast_data = {
            'game_status': game_session.status,
            'player_count': player_count,
            'players': players_data,
            'message': f'{player.name} joined the game!'
        }
        logger.info(f"Broadcasting player join: {broadcast_data}")
        broadcast_to_game(game_session.game_code, 'game_update', broadcast_data)
    
