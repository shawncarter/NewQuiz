from django.db import models
import random
import string
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


class MultipleChoiceQuestion(models.Model):
    """A multiple choice question for a quiz game"""
    question_text = models.TextField(unique=True)
    choices = models.JSONField()
    correct_answer = models.CharField(max_length=255)
    category = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used = models.DateTimeField(null=True, blank=True)
    usage_count = models.IntegerField(default=0)
    is_ai_generated = models.BooleanField(default=False)
    is_specialist = models.BooleanField(default=False, help_text="True if this question is for a specialist subject (Mastermind rounds)")

    def __str__(self):
        return self.question_text


class GameSession(models.Model):
    """A game session that players can join"""

    STATUS_CHOICES = [
        ('waiting', 'Waiting for Players'),
        ('active', 'Game Active'),
        ('finished', 'Game Finished'),
    ]

    game_code = models.CharField(max_length=6, unique=True, db_index=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='waiting')
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    # Counter-based round system: 0=no rounds started, 1+=active round number
    current_round_number = models.IntegerField(default=0)
    is_round_active = models.BooleanField(default=False)
    current_round_started_at = models.DateTimeField(null=True, blank=True)
    max_players = models.IntegerField(default=10)
    used_questions = models.ManyToManyField(MultipleChoiceQuestion, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Game {self.game_code} ({self.status})"

    def save(self, *args, **kwargs):
        if not self.game_code:
            self.game_code = self.generate_game_code()
        super().save(*args, **kwargs)

    @staticmethod
    def generate_game_code():
        """Generate a unique 6-character game code"""
        while True:
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            if not GameSession.objects.filter(game_code=code).exists():
                return code

    @property
    def player_count(self):
        """Get current number of players"""
        return self.players.count()

    @property
    def can_join(self):
        """Check if new players can join this session"""
        return (self.status == 'waiting' and
                self.player_count < self.max_players)

    def start_game(self):
        """Start the game session"""
        self.status = 'active'
        self.started_at = timezone.now()
        self.save()

        # Generate rounds for the game
        self.generate_rounds()

    def finish_game(self):
        """Finish the game session"""
        self.status = 'finished'
        self.finished_at = timezone.now()
        self.save()

    def restart_game(self):
        """Restart the game session for development/testing"""
        # Reset game session status
        self.status = 'waiting'
        self.started_at = None
        self.finished_at = None

        # Use round service to restart rounds
        from shared.services import get_round_service
        round_service = get_round_service(self)
        round_service.restart_rounds()
        
        self.save()

        # Clear player answers
        from players.models import PlayerAnswer
        PlayerAnswer.objects.filter(player__game_session=self).delete()

        # Reset player connections and scores (keep players but mark as connected)
        self.players.update(is_connected=True)

        # Reset all player scores to 0
        for player in self.players.all():
            player.reset_score()

        # Keep the configuration but allow it to be changed

    def generate_rounds(self):
        """Generate rounds for the game based on configuration"""
        # Rounds are now generated dynamically using the counter system
        # No need to create database objects or validate categories here
        pass

    def get_current_round(self):
        """Get the current round info using round handler system"""
        return self.get_current_round_info()

    def get_next_round(self):
        """Get the next round info using the new round service"""
        from shared.services import get_round_service
        round_service = get_round_service(self)
        return round_service.get_next_round_info()


    def is_game_complete(self):
        """Check if all rounds have been completed using round service"""
        from shared.services import get_round_service
        round_service = get_round_service(self)
        return round_service.is_game_complete()

    def get_final_scores(self):
        """Get final scores for all players using new scoring system"""
        players = self.players.filter(is_connected=True)
        scores = []

        for player in players:
            scores.append({
                'player_name': player.name,
                'total_score': player.current_score
            })

        # Sort by score descending
        scores.sort(key=lambda x: x['total_score'], reverse=True)
        return scores

    def get_current_round_info(self):
        """Get current round information using the new round service"""
        from shared.services import get_round_service
        round_service = get_round_service(self)
        return round_service.get_current_round_info()

    # Legacy helper methods moved to RoundGeneratorService


class GameType(models.Model):
    """Different types of games that can be played"""

    name = models.CharField(max_length=50, unique=True)
    description = models.TextField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class GameCategory(models.Model):
    """Categories for games (e.g., Flowers, Fruits, Movies, etc.)"""

    name = models.CharField(max_length=50)
    game_type = models.ForeignKey(GameType, on_delete=models.CASCADE, related_name='categories')
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "Game Categories"
        unique_together = ['name', 'game_type']

    def __str__(self):
        return f"{self.name} ({self.game_type.name})"


class GameConfiguration(models.Model):
    """Configuration for a specific game session"""

    game_session = models.OneToOneField(GameSession, on_delete=models.CASCADE, related_name='configuration')
    game_type = models.ForeignKey(GameType, on_delete=models.CASCADE)
    categories = models.ManyToManyField(GameCategory, blank=True)
    num_rounds = models.IntegerField(default=10)
    round_time_seconds = models.IntegerField(default=30)
    round_type_sequence = models.JSONField(default=list)

    # Scoring configuration
    unique_answer_points = models.IntegerField(default=10)
    valid_answer_points = models.IntegerField(default=5)
    invalid_answer_points = models.IntegerField(default=0)

    def __str__(self):
        return f"Config for {self.game_session.game_code}"



