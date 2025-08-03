"""
Mastermind Game Service

Business logic for mastermind rounds, extracted from the generic round handler system.
Provides clean separation of concerns and better maintainability.
"""

import logging
from typing import Dict, List, Any, Optional
from django.utils import timezone
from django.core.cache import cache
from django.db import transaction

from .models import MastermindRound, Subject, SpecialistQuestion, GeneralKnowledgeQuestion, PlayerQuestionSet, MastermindAnswer
from .question_pregeneration_service import QuestionPregenerationService
from players.models import Player
from game_sessions.models import GameSession

logger = logging.getLogger('mastermind')


class MastermindService:
    """Service class for mastermind game logic"""
    
    def __init__(self, game_session: GameSession):
        self.game_session = game_session
        self.questions_per_player = 20
        self.pregeneration_service = QuestionPregenerationService(game_session)
    
    def get_or_create_round(self, round_number: int) -> MastermindRound:
        """Get or create a mastermind round for the given round number"""
        mastermind_round, created = MastermindRound.objects.get_or_create(
            game_session=self.game_session,
            round_number=round_number,
            defaults={
                'questions_per_player': self.questions_per_player
            }
        )
        
        if created:
            logger.info(f"Created new mastermind round {round_number} for game {self.game_session.game_code}")
        
        return mastermind_round
    
    def get_round_data(self, round_number: int) -> Dict[str, Any]:
        """Get current round data for frontend display"""
        mastermind_round = self.get_or_create_round(round_number)
        
        # Base data for all states
        data = {
            'round_type': 'mastermind',
            'round_number': round_number,
            'state': mastermind_round.state,
            'is_active': self.game_session.is_round_active,
            'time_remaining': self._calculate_time_remaining(),
            'started_at': self._serialize_datetime(self.game_session.current_round_started_at),
        }
        
        # State-specific data
        if mastermind_round.state == 'waiting_for_player_selection':
            data.update(self._get_player_selection_data(mastermind_round))
        elif mastermind_round.state == 'asking_ready':
            data.update(self._get_ready_check_data(mastermind_round))
        elif mastermind_round.state == 'playing':
            data.update(self._get_active_question_data(mastermind_round))
        elif mastermind_round.state == 'player_complete':
            data.update(self._get_player_complete_data(mastermind_round))
        elif mastermind_round.state == 'all_complete':
            data.update(self._generate_general_knowledge_data())
        
        return data
    
    def select_player(self, round_number: int, player_id: int) -> Dict[str, Any]:
        """GM selects which player goes next"""
        try:
            with transaction.atomic():
                mastermind_round = self.get_or_create_round(round_number)
                player = Player.objects.get(
                    id=player_id,
                    game_session=self.game_session,
                    is_connected=True
                )
                
                # Use model method for validation and state change
                mastermind_round.select_player(player)
                
                # Pre-load questions for this player
                self._preload_player_questions(mastermind_round, player)
                
                return {
                    'success': True,
                    'selected_player': {
                        'id': player.id,
                        'name': player.name,
                        'specialist_subject': player.specialist_subject
                    },
                    'message': f'Selected {player.name} for their specialist round on {player.specialist_subject}'
                }
                
        except Player.DoesNotExist:
            return {'success': False, 'error': 'Player not found'}
        except ValueError as e:
            return {'success': False, 'error': str(e)}
        except Exception as e:
            logger.error(f"Error selecting player {player_id}: {e}")
            return {'success': False, 'error': 'Failed to select player'}
    
    def player_ready_response(self, round_number: int, is_ready: bool) -> Dict[str, Any]:
        """Process player's ready response"""
        try:
            with transaction.atomic():
                mastermind_round = self.get_or_create_round(round_number)
                
                if mastermind_round.player_ready(is_ready):
                    # Player is ready, return success
                    return {
                        'success': True,
                        'message': f'Starting rapid-fire specialist round! {self.questions_per_player} questions in 90 seconds!'
                    }
                else:
                    # Player not ready, return to selection
                    return {
                        'success': True,
                        'message': 'Player not ready, select another player or try again later'
                    }
                    
        except ValueError as e:
            return {'success': False, 'error': str(e)}
        except Exception as e:
            logger.error(f"Error processing ready response: {e}")
            return {'success': False, 'error': 'Failed to process ready response'}
    
    def continue_to_next_player(self, round_number: int) -> Dict[str, Any]:
        """Move from player complete back to player selection"""
        try:
            mastermind_round = self.get_or_create_round(round_number)
            mastermind_round.continue_to_next_player()
            
            return {
                'success': True,
                'message': 'Ready to select next player'
            }
            
        except Exception as e:
            logger.error(f"Error continuing to next player: {e}")
            return {'success': False, 'error': 'Failed to continue to next player'}
    
    def start_general_knowledge_round(self, round_number: int) -> Dict[str, Any]:
        """Start general knowledge round for all players simultaneously"""
        try:
            with transaction.atomic():
                mastermind_round = self.get_or_create_round(round_number)
                
                # Ensure we're in the correct phase and set active state
                mastermind_round.current_phase = 'general_knowledge'
                mastermind_round.state = 'general_knowledge_active'
                mastermind_round.save()
                
                # Get all connected players
                all_players = self.game_session.players.filter(is_connected=True).order_by('joined_at')
                
                if not all_players.exists():
                    return {
                        'success': False,
                        'error': 'No connected players available for general knowledge round'
                    }
                
                # Pre-load general knowledge questions for all players
                if not self._preload_general_knowledge_questions(mastermind_round, all_players):
                    return {
                        'success': False,
                        'error': 'Failed to load general knowledge questions'
                    }
                
                # Start the timer for the general knowledge round
                self.game_session.is_round_active = True
                self.game_session.current_round_started_at = timezone.now()
                self.game_session.save()
                
                logger.info(f"Started general knowledge round for {len(all_players)} players in game {self.game_session.game_code}")
                
                return {
                    'success': True,
                    'phase': 'general_knowledge',
                    'time_limit_seconds': 120,
                    'player_count': len(all_players),
                    'message': f'General Knowledge round started! All {len(all_players)} players have 2 minutes to answer 20 questions.'
                }
                
        except Exception as e:
            logger.error(f"Error starting general knowledge round: {e}")
            return {'success': False, 'error': 'Failed to start general knowledge round'}
    
    def complete_general_knowledge_round(self, round_number: int) -> Dict[str, Any]:
        """Complete the general knowledge round and check if all players have submitted"""
        try:
            mastermind_round = self.get_or_create_round(round_number)
            
            if mastermind_round.current_phase != 'general_knowledge':
                return {
                    'success': False,
                    'error': 'Not currently in general knowledge phase'
                }
            
            # Get all connected players
            all_players = self.game_session.players.filter(is_connected=True)
            
            # Check how many players have submitted general knowledge answers
            players_who_answered = MastermindAnswer.objects.filter(
                mastermind_round=mastermind_round,
                question_type='general_knowledge'
            ).values_list('player_id', flat=True).distinct()
            
            answered_count = len(set(players_who_answered))
            total_players = all_players.count()
            
            # Calculate completion statistics
            completion_stats = self._get_general_knowledge_stats(mastermind_round, all_players)
            
            # Check if time has expired (120 seconds for general knowledge)
            time_expired = False
            if self.game_session.is_round_active and self.game_session.current_round_started_at:
                elapsed = (timezone.now() - self.game_session.current_round_started_at).total_seconds()
                time_expired = elapsed > 120  # 120 seconds for general knowledge
            
            if answered_count >= total_players or time_expired:
                # All players answered or time expired - complete the round
                mastermind_round.state = 'all_complete'
                mastermind_round.save()
                
                # End the game session round
                self.game_session.is_round_active = False
                self.game_session.current_round_started_at = None
                self.game_session.save()
                
                logger.info(f"General knowledge round completed: {answered_count}/{total_players} players answered")
                
                return {
                    'success': True,
                    'completed': True,
                    'players_answered': answered_count,
                    'total_players': total_players,
                    'stats': completion_stats,
                    'message': f'General Knowledge round completed! {answered_count}/{total_players} players submitted answers.'
                }
            else:
                # Still waiting for more players
                return {
                    'success': True,
                    'completed': False,
                    'players_answered': answered_count,
                    'total_players': total_players,
                    'waiting_for': total_players - answered_count,
                    'message': f'Waiting for {total_players - answered_count} more players to submit answers...'
                }
                
        except Exception as e:
            logger.error(f"Error completing general knowledge round: {e}")
            return {'success': False, 'error': 'Failed to complete general knowledge round'}
    
    def submit_rapid_fire_answers(self, round_number: int, player_id: int, answers: List[Dict]) -> Dict[str, Any]:
        """Process submitted rapid-fire answers for both specialist and general knowledge phases"""
        try:
            with transaction.atomic():
                mastermind_round = self.get_or_create_round(round_number)
                player = Player.objects.get(id=player_id, game_session=self.game_session)
                
                # Get pre-loaded questions to validate answers
                question_set = PlayerQuestionSet.objects.get(
                    mastermind_round=mastermind_round,
                    player=player
                )
                
                correct_count = 0
                total_points = 0
                
                # Determine question type from the first question or current phase
                question_type = 'specialist'  # default
                if question_set.questions and len(question_set.questions) > 0:
                    first_question = question_set.questions[0]
                    question_type = first_question.get('question_type', 'specialist')
                elif mastermind_round.current_phase == 'general_knowledge':
                    question_type = 'general_knowledge'
                
                # Calculate starting question index (20+ for general knowledge to avoid conflicts)
                start_index = 20 if question_type == 'general_knowledge' else 0
                
                # Process each answer
                for i, answer_data in enumerate(answers):
                    if i < len(question_set.questions):
                        question = question_set.questions[i]
                        is_correct = answer_data.get('selected_choice') == question.get('correct_answer')
                        
                        if is_correct:
                            correct_count += 1
                            total_points += 10  # 10 points per correct answer
                        
                        # Record individual answer with question type and adjusted index
                        MastermindAnswer.objects.create(
                            mastermind_round=mastermind_round,
                            player=player,
                            question_index=start_index + i,  # Use offset index to avoid conflicts
                            question_id=question.get('question_id', 0),
                            question_type=question_type,
                            selected_choice=answer_data.get('selected_choice', ''),
                            is_correct=is_correct,
                            response_time_ms=answer_data.get('response_time_ms', 0)
                        )
                
                # Update player score with appropriate reason
                reason = f"mastermind_{question_type}"
                player.award_points(
                    total_points,
                    reason=reason,
                    round_number=round_number
                )
                
                # Handle completion based on question type
                if question_type == 'specialist':
                    # Mark player as complete for specialist round
                    mastermind_round.complete_current_player()
                    # Check if we should transition to next player or general knowledge phase
                    mastermind_round.continue_to_next_player()
                    message = f'Completed specialist round: {correct_count}/{len(answers)} correct'
                else:
                    # General knowledge - don't change state, all players answer simultaneously
                    message = f'Completed general knowledge round: {correct_count}/{len(answers)} correct'
                
                logger.info(f"Player {player.name} completed {question_type} round: {correct_count}/{len(answers)} correct, {total_points} points")
                
                return {
                    'success': True,
                    'correct_answers': correct_count,
                    'total_questions': len(answers),
                    'points_earned': total_points,
                    'question_type': question_type,
                    'message': message
                }
                
        except (Player.DoesNotExist, PlayerQuestionSet.DoesNotExist) as e:
            logger.error(f"Error submitting rapid-fire answers: {e}")
            return {'success': False, 'error': 'Player or questions not found'}
        except Exception as e:
            logger.error(f"Error processing rapid-fire answers: {e}")
            return {'success': False, 'error': 'Failed to process answers'}
    
    # Private helper methods
    
    def _calculate_time_remaining(self) -> int:
        """Calculate time remaining for active rounds"""
        if not self.game_session.is_round_active or not self.game_session.current_round_started_at:
            return 0
        
        elapsed = (timezone.now() - self.game_session.current_round_started_at).total_seconds()
        return max(0, self.game_session.configuration.round_time_seconds - int(elapsed))
    
    def _get_player_selection_data(self, mastermind_round: MastermindRound) -> Dict[str, Any]:
        """GM selects which player goes next"""
        available_players = mastermind_round.get_available_players()

        # Get all connected players for GM screen display
        all_players = self.game_session.players.filter(is_connected=True).order_by('joined_at')

        if not available_players.exists():
            # Check if this is because no players have specialist subjects
            # vs all players have actually completed their rounds
            players_with_subjects = all_players.filter(
                specialist_subject__isnull=False
            ).exclude(specialist_subject='')

            if not players_with_subjects.exists():
                # No players have specialist subjects - this is a configuration issue
                return {
                    'state': 'waiting_for_player_selection',
                    'available_players': [],
                    'completed_players': list(mastermind_round.completed_players.values_list('id', flat=True)),
                    'all_players': [
                        {
                            'id': p.id,
                            'name': p.name,
                            'specialist_subject': p.specialist_subject or '',
                            'current_score': p.current_score or 0
                        } for p in all_players
                    ],
                    'no_specialist_subjects': True,
                    'message': 'No players have specialist subjects set. Mastermind rounds require specialist subjects.',
                    'error': 'Cannot continue with Mastermind round - no specialist subjects available'
                }
            else:
                # All players with specialist subjects have completed their rounds
                mastermind_round.state = 'all_complete'
                mastermind_round.save()
                return self._generate_general_knowledge_data()

        return {
            'state': 'waiting_for_player_selection',
            'available_players': [
                {
                    'id': p.id,
                    'name': p.name,
                    'specialist_subject': p.specialist_subject
                } for p in available_players
            ],
            'completed_players': list(mastermind_round.completed_players.values_list('id', flat=True)),
            'all_players': [
                {
                    'id': p.id,
                    'name': p.name,
                    'specialist_subject': p.specialist_subject or '',
                    'current_score': p.current_score or 0
                } for p in all_players
            ],
            'message': 'Game Master: Select the next player for their specialist round'
        }
    
    def _get_ready_check_data(self, mastermind_round: MastermindRound) -> Dict[str, Any]:
        """Ask current player if they're ready"""
        if not mastermind_round.current_player:
            mastermind_round.state = 'waiting_for_player_selection'
            mastermind_round.save()
            return self._get_player_selection_data(mastermind_round)
        
        return {
            'state': 'asking_ready',
            'current_player': {
                'id': mastermind_round.current_player.id,
                'name': mastermind_round.current_player.name,
                'specialist_subject': mastermind_round.current_player.specialist_subject
            },
            'message': f'{mastermind_round.current_player.name}, are you ready for your specialist round on {mastermind_round.current_player.specialist_subject}?'
        }
    
    def _get_active_question_data(self, mastermind_round: MastermindRound) -> Dict[str, Any]:
        """Get current question for active player - SECURE: No answers sent to client"""
        if not mastermind_round.current_player:
            mastermind_round.state = 'waiting_for_player_selection'
            mastermind_round.save()
            return self._get_player_selection_data(mastermind_round)
        
        try:
            # Get pre-loaded questions for this player
            question_set = PlayerQuestionSet.objects.get(
                mastermind_round=mastermind_round,
                player=mastermind_round.current_player
            )
            
            questions = question_set.questions
            current_index = mastermind_round.current_question_index
            
            if current_index >= len(questions):
                # All questions answered, player is complete
                mastermind_round.complete_current_player()
                return self._get_player_complete_data(mastermind_round)
            
            # Get current question (SECURE: Don't send correct_answer to client)
            current_question = questions[current_index]
            
            # Get all connected players for GM screen display
            all_players = self.game_session.players.filter(is_connected=True).order_by('joined_at')
            
            return {
                'state': 'playing',
                'current_player': {
                    'id': mastermind_round.current_player.id,
                    'name': mastermind_round.current_player.name,
                    'specialist_subject': mastermind_round.current_player.specialist_subject
                },
                'question_text': current_question['question_text'],
                'choices': current_question['choices'],
                'category': current_question['category'],
                'is_ai_generated': current_question.get('is_ai_generated', False),
                'question_id': current_question['question_id'],
                'current_question_index': current_index + 1,
                'questions_per_player': len(questions),
                'rapid_fire_mode': True,
                # SECURITY FIX: Send questions WITHOUT answers
                'all_questions': [
                    {
                        'question_id': q['question_id'],
                        'question_text': q['question_text'],
                        'choices': q['choices'],
                        'category': q['category'],
                        'is_ai_generated': q.get('is_ai_generated', False),
                        # DON'T send correct_answer
                    } for q in questions
                ],
                'all_players': [
                    {
                        'id': p.id,
                        'name': p.name,
                        'specialist_subject': p.specialist_subject or '',
                        'current_score': p.current_score or 0
                    } for p in all_players
                ],
            }
            
        except PlayerQuestionSet.DoesNotExist:
            logger.error(f"No question set found for player {mastermind_round.current_player.name}")
            # Fallback: try to pre-load questions now
            self._preload_player_questions(mastermind_round, mastermind_round.current_player)
            return {
                'state': 'asking_ready',
                'current_player': {
                    'id': mastermind_round.current_player.id,
                    'name': mastermind_round.current_player.name,
                    'specialist_subject': mastermind_round.current_player.specialist_subject
                },
                'message': f'Preparing questions for {mastermind_round.current_player.name}...'
            }
    
    def _get_player_complete_data(self, mastermind_round: MastermindRound) -> Dict[str, Any]:
        """Current player finished their round"""
        current_player = mastermind_round.current_player
        
        return {
            'state': 'player_complete',
            'current_player': {
                'id': current_player.id,
                'name': current_player.name,
                'specialist_subject': current_player.specialist_subject
            } if current_player else None,
            'completed_players': list(mastermind_round.completed_players.values_list('id', flat=True)),
            'message': f'{current_player.name} has completed their specialist round!' if current_player else 'Player completed their round!'
        }
    
    def _generate_general_knowledge_data(self) -> Dict[str, Any]:
        """Generate general knowledge data for final simultaneous round"""
        try:
            # Get all connected players for general knowledge round
            all_players = self.game_session.players.filter(is_connected=True).order_by('joined_at')
            
            # Check if questions are already pre-loaded for general knowledge
            round_obj = MastermindRound.objects.get(
                game_session=self.game_session,
                round_number=self.game_session.current_round_number
            )
            
            # Pre-load general knowledge questions for all players if not done
            self._preload_general_knowledge_questions(round_obj, all_players)
            
            # Get the first player's question set to send to all players
            # (All players get the same questions in general knowledge phase)
            first_player = all_players.first()
            if first_player:
                try:
                    question_set = PlayerQuestionSet.objects.get(
                        mastermind_round=round_obj,
                        player=first_player
                    )
                    questions = question_set.questions
                    
                    # SECURITY: Send questions WITHOUT correct answers
                    safe_questions = [
                        {
                            'question_id': q['question_id'],
                            'question_text': q['question_text'],
                            'choices': q['choices'],
                            'category': q['category'],
                            'is_ai_generated': q.get('is_ai_generated', False),
                            'question_number': i + 1,
                            'total_questions': len(questions)
                        } for i, q in enumerate(questions)
                    ]
                    
                    return {
                        'state': 'general_knowledge',
                        'phase': 'general_knowledge',
                        'all_questions': safe_questions,
                        'questions_per_player': len(questions),
                        'time_limit_seconds': 120,  # 2 minutes for general knowledge
                        'simultaneous_play': True,
                        'all_players': [
                            {
                                'id': p.id,
                                'name': p.name,
                                'current_score': p.current_score or 0
                            } for p in all_players
                        ],
                        'message': 'General Knowledge Round: All players answer 20 questions simultaneously!'
                    }
                    
                except PlayerQuestionSet.DoesNotExist:
                    logger.error("No general knowledge questions found for players")
                    return {
                        'state': 'general_knowledge',
                        'phase': 'general_knowledge',
                        'error': 'General knowledge questions not available',
                        'message': 'Preparing general knowledge questions...'
                    }
            else:
                return {
                    'state': 'all_complete',
                    'phase': 'general_knowledge',
                    'message': 'No players available for general knowledge round'
                }
                
        except Exception as e:
            logger.error(f"Error generating general knowledge data: {e}")
            return {
                'state': 'all_complete',
                'phase': 'general_knowledge',
                'error': str(e),
                'message': 'Error preparing general knowledge round'
            }
    
    def _preload_player_questions(self, mastermind_round: MastermindRound, player: Player) -> bool:
        """Pre-load questions for a player's rapid-fire session (specialist questions only)"""
        try:
            # Check if questions already loaded
            if PlayerQuestionSet.objects.filter(mastermind_round=mastermind_round, player=player).exists():
                logger.info(f"Questions already pre-loaded for {player.name}")
                return True
            
            specialist_subject = player.specialist_subject
            if not specialist_subject:
                logger.error(f"Player {player.name} has no specialist subject")
                return False
            
            # Get or create subject
            subject, _ = Subject.objects.get_or_create(name=specialist_subject)
            
            # Get questions for this subject
            questions = list(SpecialistQuestion.objects.filter(
                subject=subject
            ).order_by('usage_count', 'last_used')[:self.questions_per_player])
            
            if len(questions) < self.questions_per_player:
                logger.warning(f"Only {len(questions)} questions available for {specialist_subject}, need {self.questions_per_player}")
            
            # Convert to serializable format
            question_data = []
            for i, question in enumerate(questions):
                question_data.append({
                    'question_id': question.id,
                    'question_text': question.question_text,
                    'choices': question.choices,
                    'correct_answer': question.correct_answer,  # Server-side only
                    'category': specialist_subject,
                    'is_ai_generated': question.is_ai_generated,
                    'question_number': i + 1,
                    'total_questions': len(questions),
                    'question_type': 'specialist'
                })
            
            # Store question set
            PlayerQuestionSet.objects.create(
                mastermind_round=mastermind_round,
                player=player,
                questions=question_data
            )
            
            logger.info(f"Pre-loaded {len(question_data)} specialist questions for {player.name} ({specialist_subject})")
            return True
            
        except Exception as e:
            logger.error(f"Error pre-loading questions for {player.name}: {e}")
            return False
    
    def _preload_general_knowledge_questions(self, mastermind_round: MastermindRound, players) -> bool:
        """Pre-load general knowledge questions for all players (same questions for everyone)"""
        try:
            # Check if general knowledge questions already loaded for any player
            existing_gk_set = PlayerQuestionSet.objects.filter(
                mastermind_round=mastermind_round,
                player__in=players
            ).first()
            
            if existing_gk_set and 'question_type' in str(existing_gk_set.questions) and 'general_knowledge' in str(existing_gk_set.questions):
                logger.info("General knowledge questions already pre-loaded")
                return True
            
            # Get general knowledge questions
            gk_questions = list(GeneralKnowledgeQuestion.objects.order_by(
                'usage_count', 'last_used'
            )[:self.questions_per_player])
            
            if len(gk_questions) < self.questions_per_player:
                logger.warning(f"Only {len(gk_questions)} general knowledge questions available, need {self.questions_per_player}")
            
            # Convert to serializable format (same questions for all players)
            question_data = []
            for i, question in enumerate(gk_questions):
                question_data.append({
                    'question_id': question.id,
                    'question_text': question.question_text,
                    'choices': question.choices,
                    'correct_answer': question.correct_answer,  # Server-side only
                    'category': question.category,
                    'is_ai_generated': question.is_ai_generated,
                    'question_number': i + 1,
                    'total_questions': len(gk_questions),
                    'question_type': 'general_knowledge'
                })
            
            # Store question set for all players (same questions)
            for player in players:
                # Check if player already has a question set (from specialist round)
                existing_set = PlayerQuestionSet.objects.filter(
                    mastermind_round=mastermind_round,
                    player=player
                ).first()
                
                if existing_set:
                    # Update existing set with general knowledge questions
                    existing_set.questions = question_data
                    existing_set.save()
                else:
                    # Create new question set with general knowledge questions
                    PlayerQuestionSet.objects.create(
                        mastermind_round=mastermind_round,
                        player=player,
                        questions=question_data
                    )
            
            logger.info(f"Pre-loaded {len(question_data)} general knowledge questions for {len(players)} players")
            return True
            
        except Exception as e:
            logger.error(f"Error pre-loading general knowledge questions: {e}")
            return False
    
    def _get_general_knowledge_questions(self, mastermind_round: MastermindRound):
        """Get general knowledge questions for the round"""
        try:
            # Get the first player's question set (all players have the same questions)
            players = self.game_session.players.filter(is_connected=True)
            if not players.exists():
                return []
                
            first_player = players.first()
            question_set = PlayerQuestionSet.objects.get(
                mastermind_round=mastermind_round,
                player=first_player
            )
            
            # Convert to GeneralKnowledgeQuestion objects for compatibility
            gk_questions = []
            for q_data in question_set.questions:
                if q_data.get('question_type') == 'general_knowledge':
                    # Create a mock GeneralKnowledgeQuestion object with the data
                    class MockGKQuestion:
                        def __init__(self, data):
                            self.id = data['question_id']
                            self.question_text = data['question_text']
                            self.choices = data['choices']
                            self.correct_answer = data['correct_answer']
                            self.category = data.get('category', 'General Knowledge')
                            self.is_ai_generated = data.get('is_ai_generated', False)
                    
                    gk_questions.append(MockGKQuestion(q_data))
            
            return gk_questions[:20]  # Return up to 20 questions
            
        except (PlayerQuestionSet.DoesNotExist, IndexError):
            # Fallback: get questions directly from database
            return list(GeneralKnowledgeQuestion.objects.order_by(
                'usage_count', 'last_used'
            )[:20])
        except Exception as e:
            logger.error(f"Error getting general knowledge questions: {e}")
            return []
    
    def _get_specialist_questions(self, mastermind_round: MastermindRound, player):
        """Get specialist questions for a specific player"""
        try:
            question_set = PlayerQuestionSet.objects.get(
                mastermind_round=mastermind_round,
                player=player
            )
            
            # Convert to SpecialistQuestion objects for compatibility
            specialist_questions = []
            for q_data in question_set.questions:
                if q_data.get('question_type') == 'specialist':
                    # Create a mock SpecialistQuestion object with the data
                    class MockSpecialistQuestion:
                        def __init__(self, data):
                            self.id = data['question_id']
                            self.question_text = data['question_text']
                            self.choices = data['choices']
                            self.correct_answer = data['correct_answer']
                            self.subject = type('Subject', (), {'name': data.get('category', 'Unknown')})()
                            self.is_ai_generated = data.get('is_ai_generated', False)
                    
                    specialist_questions.append(MockSpecialistQuestion(q_data))
            
            return specialist_questions[:20]  # Return up to 20 questions
            
        except PlayerQuestionSet.DoesNotExist:
            # Fallback: get questions directly from database
            subject, _ = Subject.objects.get_or_create(name=player.specialist_subject)
            return list(SpecialistQuestion.objects.filter(
                subject=subject
            ).order_by('usage_count', 'last_used')[:20])
        except Exception as e:
            logger.error(f"Error getting specialist questions: {e}")
            return []
    
    def _get_general_knowledge_stats(self, mastermind_round: MastermindRound, players) -> Dict[str, Any]:
        """Calculate general knowledge round completion statistics"""
        try:
            stats = {
                'player_results': [],
                'average_score': 0,
                'highest_score': 0,
                'questions_answered': 0
            }
            
            total_scores = []
            
            for player in players:
                # Get player's general knowledge answers
                player_answers = MastermindAnswer.objects.filter(
                    mastermind_round=mastermind_round,
                    player=player,
                    question_type='general_knowledge'
                )
                
                correct_answers = player_answers.filter(is_correct=True).count()
                total_answers = player_answers.count()
                score_earned = correct_answers * 10  # 10 points per correct answer
                
                if total_answers > 0:
                    total_scores.append(score_earned)
                    stats['questions_answered'] += total_answers
                
                stats['player_results'].append({
                    'player_id': player.id,
                    'name': player.name,
                    'correct_answers': correct_answers,
                    'total_answers': total_answers,
                    'score_earned': score_earned,
                    'percentage': round((correct_answers / total_answers * 100) if total_answers > 0 else 0, 1)
                })
            
            if total_scores:
                stats['average_score'] = round(sum(total_scores) / len(total_scores), 1)
                stats['highest_score'] = max(total_scores)
            
            return stats
            
        except Exception as e:
            logger.error(f"Error calculating general knowledge stats: {e}")
            return {'error': 'Failed to calculate statistics'}
    
    # Question Pre-Generation Methods
    
    def pregenerate_questions_for_round(self, round_number: int = None) -> Dict[str, Any]:
        """
        Pre-generate all questions needed for this mastermind round.
        This should be called at game start to eliminate loading delays.
        
        Args:
            round_number: Round number to pre-generate for (default: current)
            
        Returns:
            Dict with pre-generation results
        """
        try:
            logger.info(f"Starting question pre-generation for game {self.game_session.game_code}")
            result = self.pregeneration_service.pregenerate_all_questions(round_number)
            
            if result['success']:
                logger.info(f"Successfully pre-generated {result['total_questions_generated']} questions")
            else:
                logger.error(f"Question pre-generation failed: {result.get('error', 'Unknown error')}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error in question pre-generation: {e}")
            return {
                'success': False,
                'error': str(e),
                'total_questions_generated': 0
            }
    
    def validate_question_readiness(self, round_number: int = None) -> Dict[str, Any]:
        """
        Validate that all required questions are available for the mastermind round.
        
        Args:
            round_number: Round number to validate
            
        Returns:
            Dict with validation results
        """
        try:
            return self.pregeneration_service.validate_question_availability(round_number)
        except Exception as e:
            logger.error(f"Error validating question readiness: {e}")
            return {
                'success': False,
                'errors': [str(e)]
            }
    
    def get_question_generation_status(self) -> Dict[str, Any]:
        """Get current status of question availability for this game"""
        try:
            return self.pregeneration_service.get_pregeneration_status()
        except Exception as e:
            logger.error(f"Error getting question generation status: {e}")
            return {'error': str(e)}
    
    def _serialize_datetime(self, dt):
        """Helper method to serialize datetime objects for JSON"""
        if dt is None:
            return None
        return dt.isoformat() if hasattr(dt, 'isoformat') else str(dt)