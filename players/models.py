from django.db import models
from game_sessions.models import GameSession


class Player(models.Model):
    """A player in a game session"""

    name = models.CharField(max_length=50)
    game_session = models.ForeignKey(
        GameSession,
        on_delete=models.CASCADE,
        related_name='players'
    )
    joined_at = models.DateTimeField(auto_now_add=True)
    is_connected = models.BooleanField(default=True)
    current_score = models.IntegerField(default=0)

    # For local testing - we'll use a simple session identifier
    session_key = models.CharField(max_length=40, null=True, blank=True)

    class Meta:
        ordering = ['joined_at']
        # No unique constraints for development - allows multiple players with same name

    def __str__(self):
        return f"{self.name} in {self.game_session.game_code}"

    def disconnect(self):
        """Mark player as disconnected"""
        self.is_connected = False
        self.save()

    def reconnect(self):
        """Mark player as reconnected"""
        self.is_connected = True
        self.save()

    @property
    def total_score(self):
        """Calculate total score from all player answers (backward compatibility)"""
        return self.current_score

    def award_points(self, amount, reason="points_awarded", round_number=None, related_answer=None):
        """Award points to the player and create audit trail"""
        # Update current score
        self.current_score += amount
        self.save()

        # Create history entry
        ScoreHistory.objects.create(
            player=self,
            game_session=self.game_session,
            round_number=round_number,
            points_change=amount,
            reason=reason,
            related_answer=related_answer
        )

        # Update PlayerAnswer if provided (for backward compatibility)
        if related_answer:
            related_answer.points_awarded = amount
            related_answer.save()

        return self.current_score

    def deduct_points(self, amount, reason="points_deducted", round_number=None):
        """Deduct points from the player (amount should be positive)"""
        return self.award_points(-amount, reason, round_number)

    def get_current_score(self):
        """Get the player's current total score"""
        return self.current_score

    def reset_score(self):
        """Reset the player's score to 0 (for game restart)"""
        self.current_score = 0
        self.save()

    def get_round_score(self, round_number):
        """Get the player's total score for a specific round"""
        return self.score_history.filter(
            round_number=round_number
        ).aggregate(total=models.Sum('points_change'))['total'] or 0

    def get_score_breakdown(self):
        """Get detailed score breakdown by round"""
        breakdown = {}
        for history in self.score_history.all():
            round_num = history.round_number or 'game'
            if round_num not in breakdown:
                breakdown[round_num] = []
            breakdown[round_num].append({
                'points': history.points_change,
                'reason': history.reason,
                'timestamp': history.timestamp
            })
        return breakdown


class PlayerAnswer(models.Model):
    """A player's answer for a specific round"""

    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='answers')
    round_number = models.IntegerField(default=1)  # Simple counter-based round tracking
    answer_text = models.CharField(max_length=100)
    submitted_at = models.DateTimeField(auto_now_add=True)

    # Scoring
    points_awarded = models.IntegerField(default=0)
    is_valid = models.BooleanField(default=True)
    is_unique = models.BooleanField(default=False)

    class Meta:
        unique_together = ['player', 'round_number']
        ordering = ['submitted_at']

    def __str__(self):
        return f"{self.player.name}: {self.answer_text} (Round {self.round_number})"


class ScoreHistory(models.Model):
    """Track all score changes for audit and analytics"""

    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='score_history')
    game_session = models.ForeignKey(GameSession, on_delete=models.CASCADE, related_name='score_history')
    round_number = models.IntegerField(null=True, blank=True)  # Null for game-wide events
    points_change = models.IntegerField()  # Can be positive or negative
    reason = models.CharField(max_length=100, default='points_awarded')
    timestamp = models.DateTimeField(auto_now_add=True)
    related_answer = models.ForeignKey(PlayerAnswer, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['-timestamp']
        verbose_name_plural = 'Score histories'

    def __str__(self):
        sign = '+' if self.points_change >= 0 else ''
        return f"{self.player.name}: {sign}{self.points_change} ({self.reason})"
