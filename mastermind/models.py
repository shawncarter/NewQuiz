"""
Mastermind Game Models

Database models for persistent mastermind game state management.
Replaces cache-only state with proper database persistence.
"""

from django.db import models
from django.utils import timezone
import logging

logger = logging.getLogger('mastermind')


class Subject(models.Model):
    """Specialist subjects for mastermind rounds"""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return self.name


class SpecialistQuestion(models.Model):
    """Questions for specialist subjects in mastermind rounds"""
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='questions')
    question_text = models.TextField()
    choices = models.JSONField()
    correct_answer = models.CharField(max_length=255)
    difficulty = models.CharField(
        max_length=20, 
        choices=[('easy', 'Easy'), ('medium', 'Medium'), ('hard', 'Hard')],
        default='medium'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_used = models.DateTimeField(null=True, blank=True)
    usage_count = models.IntegerField(default=0)
    is_ai_generated = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['usage_count', 'last_used']
        indexes = [
            models.Index(fields=['subject', 'usage_count', 'last_used']),
            models.Index(fields=['subject', 'difficulty']),
        ]
    
    def __str__(self):
        return f"{self.subject.name}: {self.question_text[:50]}..."
    
    def mark_as_used(self):
        """Mark this question as used"""
        self.usage_count += 1
        self.last_used = timezone.now()
        self.save(update_fields=['usage_count', 'last_used'])


class GeneralKnowledgeQuestion(models.Model):
    """Questions for the general knowledge phase of mastermind rounds"""
    question_text = models.TextField()
    choices = models.JSONField()
    correct_answer = models.CharField(max_length=255)
    difficulty = models.CharField(
        max_length=20, 
        choices=[('easy', 'Easy'), ('medium', 'Medium'), ('hard', 'Hard')],
        default='medium'
    )
    category = models.CharField(max_length=100, default='General Knowledge')
    created_at = models.DateTimeField(auto_now_add=True)
    last_used = models.DateTimeField(null=True, blank=True)
    usage_count = models.IntegerField(default=0)
    is_ai_generated = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['usage_count', 'last_used']
        indexes = [
            models.Index(fields=['usage_count', 'last_used']),
            models.Index(fields=['difficulty']),
        ]
    
    def __str__(self):
        return f"GK: {self.question_text[:50]}..."
    
    def mark_as_used(self):
        """Mark this question as used"""
        self.usage_count += 1
        self.last_used = timezone.now()
        self.save(update_fields=['usage_count', 'last_used'])


class MastermindRound(models.Model):
    """Persistent state for mastermind rounds"""
    
    STATE_CHOICES = [
        ('waiting_for_player_selection', 'Waiting for Player Selection'),
        ('asking_ready', 'Asking Player Ready'),
        ('playing', 'Playing Rapid Fire'),
        ('player_complete', 'Player Complete'),
        ('specialist_complete', 'Specialist Round Complete'),
        ('general_knowledge', 'General Knowledge Round'),
        ('all_complete', 'All Players Complete'),
    ]
    
    PHASE_CHOICES = [
        ('specialist', 'Specialist Round'),
        ('general_knowledge', 'General Knowledge Round'),
    ]
    
    game_session = models.ForeignKey(
        'game_sessions.GameSession', 
        on_delete=models.CASCADE, 
        related_name='mastermind_rounds'
    )
    round_number = models.IntegerField()
    state = models.CharField(max_length=50, choices=STATE_CHOICES, default='waiting_for_player_selection')
    current_player = models.ForeignKey(
        'players.Player', 
        null=True, 
        blank=True, 
        on_delete=models.SET_NULL, 
        related_name='current_mastermind_rounds'
    )
    completed_players = models.ManyToManyField(
        'players.Player', 
        blank=True, 
        related_name='completed_mastermind_rounds'
    )
    current_question_index = models.IntegerField(default=0)
    questions_per_player = models.IntegerField(default=20)
    current_phase = models.CharField(max_length=20, choices=PHASE_CHOICES, default='specialist')
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    started_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        unique_together = ['game_session', 'round_number']
        ordering = ['game_session', 'round_number']
    
    def __str__(self):
        return f"Mastermind Round {self.round_number} - Game {self.game_session.game_code} ({self.state})"
    
    def get_available_players(self):
        """Get players who haven't completed their specialist round yet"""
        from django.db.models import Q

        return self.game_session.players.filter(
            is_connected=True,
            specialist_subject__isnull=False
        ).exclude(
            Q(specialist_subject='') | Q(id__in=self.completed_players.all())
        ).order_by('joined_at')
    
    def select_player(self, player):
        """Select a player for their specialist round"""
        if player in self.completed_players.all():
            raise ValueError("Player has already completed their round")
            
        if not player.specialist_subject or player.specialist_subject.strip() == '':
            raise ValueError("Player has no specialist subject")
            
        self.current_player = player
        self.state = 'asking_ready'
        self.current_question_index = 0
        self.save()
        
        logger.info(f"Selected player {player.name} for mastermind round {self.round_number}")
    
    def player_ready(self, is_ready):
        """Handle player ready response"""
        if self.state != 'asking_ready':
            raise ValueError(f"Cannot process ready response in state {self.state}")
            
        if is_ready:
            self.state = 'playing'
            self.started_at = timezone.now()
            self.save()
            logger.info(f"Started rapid-fire for player {self.current_player.name}")
            return True
        else:
            self.state = 'waiting_for_player_selection'
            self.current_player = None
            self.save()
            logger.info(f"Player {self.current_player.name} not ready, returning to selection")
            return False
    
    def complete_current_player(self):
        """Mark current player as complete and update state"""
        if not self.current_player:
            raise ValueError("No current player to complete")
            
        self.completed_players.add(self.current_player)
        self.state = 'player_complete'
        self.save()
        
        logger.info(f"Completed player {self.current_player.name} for mastermind round {self.round_number}")
    
    def continue_to_next_player(self):
        """Reset state to select next player or transition to general knowledge"""
        self.current_player = None
        self.current_question_index = 0
        
        # Check if all players completed their specialist rounds
        if self.current_phase == 'specialist':
            available_players = self.get_available_players()
            if not available_players.exists():
                # All specialist rounds complete, transition to general knowledge
                self.current_phase = 'general_knowledge'
                self.state = 'general_knowledge'
                self.save()
                logger.info(f"All specialist rounds complete, starting general knowledge for round {self.round_number}")
                return
            else:
                # More specialist rounds to do
                self.state = 'waiting_for_player_selection'
        elif self.current_phase == 'general_knowledge':
            # General knowledge complete
            self.state = 'all_complete'
            logger.info(f"All players completed mastermind round {self.round_number}")
        
        self.save()
    
    def advance_question(self):
        """Advance to next question in rapid-fire"""
        self.current_question_index += 1
        
        if self.current_question_index >= self.questions_per_player:
            self.complete_current_player()
        else:
            self.save(update_fields=['current_question_index'])


class PlayerQuestionSet(models.Model):
    """Pre-loaded questions for a player's rapid-fire session"""
    mastermind_round = models.ForeignKey(MastermindRound, on_delete=models.CASCADE)
    player = models.ForeignKey('players.Player', on_delete=models.CASCADE)
    questions = models.JSONField()  # List of question data
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['mastermind_round', 'player']
    
    def __str__(self):
        return f"Questions for {self.player.name} - Round {self.mastermind_round.round_number}"


class MastermindAnswer(models.Model):
    """Individual answers in mastermind rapid-fire sessions"""
    mastermind_round = models.ForeignKey(MastermindRound, on_delete=models.CASCADE)
    player = models.ForeignKey('players.Player', on_delete=models.CASCADE)
    question_index = models.IntegerField()
    question_id = models.IntegerField()
    question_type = models.CharField(
        max_length=20, 
        choices=[('specialist', 'Specialist'), ('general_knowledge', 'General Knowledge')],
        default='specialist'
    )
    selected_choice = models.CharField(max_length=255)
    is_correct = models.BooleanField()
    response_time_ms = models.IntegerField()  # Time taken to answer in milliseconds
    answered_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['mastermind_round', 'player', 'question_index']
        ordering = ['mastermind_round', 'player', 'question_index']
    
    def __str__(self):
        return f"{self.player.name} Q{self.question_index}: {'✓' if self.is_correct else '✗'}"