"""
Question Pre-Generation Service for Mastermind Games

Handles pre-loading and generation of both specialist and general knowledge questions
to eliminate loading delays during gameplay. Questions are pre-generated at game start
and stored for immediate retrieval during rounds.
"""

import logging
import asyncio
from typing import Dict, List, Any, Optional
from django.db import transaction
from django.utils import timezone
from django.conf import settings
from concurrent.futures import ThreadPoolExecutor, as_completed

from .models import MastermindRound, GeneralKnowledgeQuestion, SpecialistQuestion, Subject
from players.models import Player
from shared.services.specialist_ai_service import SpecialistAIService
from shared.services.general_knowledge_ai_service import GeneralKnowledgeAIService

logger = logging.getLogger('mastermind')


class QuestionPregenerationService:
    """Service for pre-generating questions at game start"""
    
    def __init__(self, game_session):
        self.game_session = game_session
        self.questions_per_player = 20
        self.specialist_ai_service = SpecialistAIService()
        self.general_knowledge_ai_service = GeneralKnowledgeAIService()
    
    def pregenerate_all_questions(self, round_number: int = None) -> Dict[str, Any]:
        """
        Pre-generate all questions needed for the mastermind round.
        
        This includes:
        1. Specialist questions for each player's subject
        2. General knowledge questions for the final phase
        
        Args:
            round_number: The round number to pre-generate for (default: current)
            
        Returns:
            Dict with success status and details
        """
        if round_number is None:
            round_number = self.game_session.current_round_number
        
        logger.info(f"Starting question pre-generation for game {self.game_session.game_code}, round {round_number}")
        
        try:
            # Get all connected players
            players = self.game_session.players.filter(is_connected=True)
            
            if not players.exists():
                return {
                    'success': False,
                    'error': 'No connected players found',
                    'details': {}
                }
            
            # Pre-generate specialist questions for each player
            specialist_results = self._pregenerate_specialist_questions(players)
            
            # Pre-generate general knowledge questions
            general_knowledge_results = self._pregenerate_general_knowledge_questions()
            
            # Combine results
            total_generated = (
                specialist_results.get('questions_generated', 0) + 
                general_knowledge_results.get('questions_generated', 0)
            )
            
            logger.info(f"Pre-generation complete: {total_generated} total questions generated")
            
            return {
                'success': True,
                'total_questions_generated': total_generated,
                'specialist_results': specialist_results,
                'general_knowledge_results': general_knowledge_results,
                'players_count': len(players),
                'message': f'Successfully pre-generated questions for {len(players)} players'
            }
                
        except Exception as e:
            logger.error(f"Error in question pre-generation: {e}")
            return {
                'success': False,
                'error': str(e),
                'details': {}
            }
    
    def _pregenerate_specialist_questions(self, players) -> Dict[str, Any]:
        """Pre-generate specialist questions for all players"""
        results = {
            'success': True,
            'questions_generated': 0,
            'subjects_processed': [],
            'errors': []
        }
        
        # Get unique specialist subjects
        specialist_subjects = set()
        for player in players:
            if player.specialist_subject and player.specialist_subject.strip():
                specialist_subjects.add(player.specialist_subject.strip())
        
        if not specialist_subjects:
            logger.warning("No specialist subjects found for players")
            results['errors'].append("No specialist subjects found")
            return results
        
        logger.info(f"Pre-generating specialist questions for subjects: {list(specialist_subjects)}")
        
        # Use parallel processing only in production, not in tests
        use_parallel = not getattr(settings, 'TESTING', False) and len(specialist_subjects) > 1
        
        if use_parallel:
            # Use ThreadPoolExecutor for parallel generation
            with ThreadPoolExecutor(max_workers=3) as executor:
                future_to_subject = {
                    executor.submit(self._ensure_specialist_subject_questions, subject): subject
                    for subject in specialist_subjects
                }
                
                for future in as_completed(future_to_subject):
                    subject = future_to_subject[future]
                    try:
                        generated_count = future.result()
                        results['questions_generated'] += generated_count
                        results['subjects_processed'].append({
                            'subject': subject,
                            'questions_generated': generated_count
                        })
                        logger.info(f"Generated {generated_count} questions for {subject}")
                    except Exception as e:
                        error_msg = f"Failed to generate questions for {subject}: {e}"
                        logger.error(error_msg)
                        results['errors'].append(error_msg)
        else:
            # Sequential processing for tests or single subjects
            for subject in specialist_subjects:
                try:
                    generated_count = self._ensure_specialist_subject_questions(subject)
                    results['questions_generated'] += generated_count
                    results['subjects_processed'].append({
                        'subject': subject,
                        'questions_generated': generated_count
                    })
                    logger.info(f"Generated {generated_count} questions for {subject}")
                except Exception as e:
                    error_msg = f"Failed to generate questions for {subject}: {e}"
                    logger.error(error_msg)
                    results['errors'].append(error_msg)
        
        return results
    
    def _ensure_specialist_subject_questions(self, subject_name: str) -> int:
        """Ensure sufficient specialist questions exist for a subject"""
        try:
            # Check current question count
            subject, created = Subject.objects.get_or_create(
                name=subject_name,
                defaults={'description': f'Specialist questions for {subject_name}'}
            )
            
            current_count = SpecialistQuestion.objects.filter(subject=subject).count()
            minimum_needed = self.questions_per_player * 2  # Buffer for multiple games
            
            if current_count < minimum_needed:
                questions_to_generate = minimum_needed - current_count
                logger.info(f"Generating {questions_to_generate} questions for {subject_name}")
                
                generated = self.specialist_ai_service.generate_bulk_questions(
                    subject_name, 
                    questions_to_generate
                )
                return generated
            else:
                logger.info(f"Sufficient questions exist for {subject_name}: {current_count}")
                return 0
                
        except Exception as e:
            logger.error(f"Error ensuring specialist questions for {subject_name}: {e}")
            return 0
    
    def _pregenerate_general_knowledge_questions(self) -> Dict[str, Any]:
        """Pre-generate general knowledge questions for the final phase"""
        results = {
            'success': True,
            'questions_generated': 0,
            'errors': []
        }
        
        try:
            # Check current general knowledge question count
            current_count = GeneralKnowledgeQuestion.objects.count()
            minimum_needed = self.questions_per_player * 3  # Buffer for multiple games
            
            if current_count < minimum_needed:
                questions_to_generate = minimum_needed - current_count
                logger.info(f"Generating {questions_to_generate} general knowledge questions")
                
                generated = self.general_knowledge_ai_service.generate_bulk_questions(
                    "General Knowledge", 
                    questions_to_generate
                )
                results['questions_generated'] = generated
                logger.info(f"Generated {generated} general knowledge questions")
            else:
                logger.info(f"Sufficient general knowledge questions exist: {current_count}")
                results['questions_generated'] = 0
            
        except Exception as e:
            error_msg = f"Error generating general knowledge questions: {e}"
            logger.error(error_msg)
            results['success'] = False
            results['errors'].append(error_msg)
        
        return results
    
    def validate_question_availability(self, round_number: int = None) -> Dict[str, Any]:
        """
        Validate that sufficient questions are available for all phases.
        
        Args:
            round_number: Round number to validate for
            
        Returns:
            Dict with validation results
        """
        if round_number is None:
            round_number = self.game_session.current_round_number
        
        validation_results = {
            'success': True,
            'specialist_validation': {},
            'general_knowledge_validation': {},
            'errors': []
        }
        
        try:
            # Get all connected players
            players = self.game_session.players.filter(is_connected=True)
            
            # Validate specialist questions for each player
            for player in players:
                if player.specialist_subject and player.specialist_subject.strip():
                    subject_name = player.specialist_subject.strip()
                    try:
                        subject = Subject.objects.get(name=subject_name)
                        question_count = SpecialistQuestion.objects.filter(subject=subject).count()
                        
                        validation_results['specialist_validation'][subject_name] = {
                            'available': question_count,
                            'needed': self.questions_per_player,
                            'sufficient': question_count >= self.questions_per_player
                        }
                        
                        if question_count < self.questions_per_player:
                            validation_results['success'] = False
                            validation_results['errors'].append(
                                f"Insufficient specialist questions for {subject_name}: {question_count}/{self.questions_per_player}"
                            )
                    except Subject.DoesNotExist:
                        validation_results['success'] = False
                        validation_results['errors'].append(f"Subject '{subject_name}' not found")
            
            # Validate general knowledge questions
            gk_count = GeneralKnowledgeQuestion.objects.count()
            validation_results['general_knowledge_validation'] = {
                'available': gk_count,
                'needed': self.questions_per_player,
                'sufficient': gk_count >= self.questions_per_player
            }
            
            if gk_count < self.questions_per_player:
                validation_results['success'] = False
                validation_results['errors'].append(
                    f"Insufficient general knowledge questions: {gk_count}/{self.questions_per_player}"
                )
            
        except Exception as e:
            validation_results['success'] = False
            validation_results['errors'].append(f"Validation error: {e}")
        
        return validation_results
    
    def get_pregeneration_status(self) -> Dict[str, Any]:
        """Get current status of question pre-generation"""
        try:
            # Count specialist questions by subject
            specialist_subjects = {}
            for subject in Subject.objects.all():
                count = SpecialistQuestion.objects.filter(subject=subject).count()
                specialist_subjects[subject.name] = count
            
            # Count general knowledge questions
            gk_count = GeneralKnowledgeQuestion.objects.count()
            
            # Get player subjects
            players = self.game_session.players.filter(is_connected=True)
            player_subjects = [
                p.specialist_subject for p in players 
                if p.specialist_subject and p.specialist_subject.strip()
            ]
            
            return {
                'specialist_subjects': specialist_subjects,
                'general_knowledge_questions': gk_count,
                'player_subjects': player_subjects,
                'questions_needed_per_player': self.questions_per_player,
                'players_count': len(players)
            }
            
        except Exception as e:
            logger.error(f"Error getting pre-generation status: {e}")
            return {'error': str(e)}