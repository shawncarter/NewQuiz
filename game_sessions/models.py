from django.db import models
import random
import string
from django.utils import timezone


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

    # Simple counter-based round system
    current_round_number = models.IntegerField(default=0)
    is_round_active = models.BooleanField(default=False)
    current_round_started_at = models.DateTimeField(null=True, blank=True)
    max_players = models.IntegerField(default=10)

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

        # Reset round counter
        self.current_round_number = 0
        self.is_round_active = False
        self.current_round_started_at = None
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
        """Get the current round info dynamically - NO DATABASE ROUNDS"""
        return self.get_current_round_info()

    def get_next_round(self):
        """Get the next round info dynamically - NO DATABASE ROUNDS"""
        if self.current_round_number >= self.configuration.num_rounds:
            return None  # Game is complete

        # Return info for the next round
        next_round_num = self.current_round_number + 1

        # Get available categories and letters
        categories = list(self.configuration.categories.all())
        letters = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M',
                  'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z']

        if not categories:
            return None

        # Use random selection with game code as seed for consistency
        import random
        random.seed(f"{self.game_code}_{next_round_num}")

        # Random category (can repeat)
        category = random.choice(categories)

        # Random letter but avoid repeats by tracking used letters
        used_letters = self._get_used_letters_for_round(next_round_num)
        available_letters = [l for l in letters if l not in used_letters]

        # If all letters used, reset and use all letters again
        if not available_letters:
            available_letters = letters

        letter = random.choice(available_letters)

        return {
            'round_number': next_round_num,
            'category': category,
            'prompt_letter': letter,
            'is_active': False,
            'time_remaining': 0,
            'started_at': None,
        }

    def is_game_complete(self):
        """Check if all rounds have been completed using counter system"""
        return self.current_round_number >= self.configuration.num_rounds

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
        """Get current round information dynamically"""
        if self.current_round_number == 0:
            return None

        # Use selected categories from game configuration, with fallback to dynamic list
        try:
            config = self.configuration
            selected_categories = list(config.categories.values_list('name', flat=True))
            
            if selected_categories:
                available_categories = selected_categories
            else:
                # Fallback to dynamic categories if none selected
                available_categories = [
                    'Animals', 'Countries', 'Cities', 'Foods', 'Movies', 'Books', 'TV Shows',
                    'Sports', 'Cars', 'Colors', 'Fruits', 'Vegetables', 'Flowers', 'Clothing',
                    'Musical Instruments', 'Board Games', 'Video Games', 'Celebrities', 
                    'Fictional Characters', 'Superheroes', 'School Subjects', 'Job Titles',
                    'Things in a Kitchen', 'Things in a Bedroom', 'Things at the Beach',
                    'Things that Fly', 'Things that are Round', 'Things that are Red',
                    'Boys Names', 'Girls Names', 'Last Names', 'Brand Names', 'Restaurants',
                    'Hobbies', 'Toys', 'Cartoon Characters', 'Disney Movies', 'Pizza Toppings',
                    'Ice Cream Flavors', 'Things in Space', 'Ocean Creatures', 'Farm Animals',
                    'Wild Animals', 'Types of Birds', 'Types of Fish', 'Insects', 'Trees',
                    'Things Made of Metal', 'Things Made of Wood', 'Electronics', 'Tools',
                    'Things in a Hospital', 'Things in a School', 'Types of Weather'
                ]
        except GameConfiguration.DoesNotExist:
            # Fallback if no configuration exists
            available_categories = ['Animals', 'Countries', 'Movies', 'Foods', 'Sports']

        letters = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M',
                  'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z']

        # Use varied seeding to prevent predictable patterns across games
        import random
        import hashlib
        import time
        
        # Create truly random seed that varies between games but stays consistent within rounds
        # Use game_code (which is random), round number, and a hash of the game creation time
        creation_hash = hashlib.md5(str(self.created_at.timestamp()).encode()).hexdigest()[:8]
        seed_string = f"{self.game_code}_{self.current_round_number}_{creation_hash}_{int(time.time()) % 10000}"
        seed_hash = hashlib.md5(seed_string.encode()).hexdigest()
        
        # Use full hash as integer seed for better distribution
        random.seed(int(seed_hash[:16], 16))

        # Random category selection from available categories
        category_name = random.choice(available_categories)
        
        # Create a simple category object for compatibility
        class DynamicCategory:
            def __init__(self, name):
                self.name = name
                self.id = hash(name) % 1000  # Simple ID for consistency
        
        category = DynamicCategory(category_name)

        # Random letter but avoid repeats by tracking used letters
        used_letters = self._get_used_letters()
        available_letters = [l for l in letters if l not in used_letters]

        # If all letters used, reset and use all letters again
        if not available_letters:
            available_letters = letters

        letter = random.choice(available_letters)

        # Calculate time remaining if round is active
        time_remaining = 0
        if self.is_round_active and self.current_round_started_at:
            from django.utils import timezone
            elapsed = (timezone.now() - self.current_round_started_at).total_seconds()
            time_remaining = max(0, self.configuration.round_time_seconds - int(elapsed))

        return {
            'round_number': self.current_round_number,
            'category': category,
            'prompt_letter': letter,
            'is_active': self.is_round_active,
            'time_remaining': time_remaining,
            'started_at': self.current_round_started_at,
        }

    def _get_used_letters(self):
        """Get letters that have been used in previous rounds"""
        return self._get_used_letters_for_round(self.current_round_number)

    def _get_used_letters_for_round(self, target_round):
        """Get letters that have been used in rounds before target_round"""
        # Store used letters in a simple way - could be enhanced with database storage
        # For now, use a deterministic approach based on round numbers
        used_letters = []

        import random
        import hashlib
        import time
        
        for round_num in range(1, target_round):
            # Use the same improved seeding approach as the main round generation
            creation_hash = hashlib.md5(str(self.created_at.timestamp()).encode()).hexdigest()[:8]
            seed_string = f"{self.game_code}_{round_num}_{creation_hash}_{int(time.time()) % 10000}"
            seed_hash = hashlib.md5(seed_string.encode()).hexdigest()
            random.seed(int(seed_hash[:16], 16))
            
            letters = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M',
                      'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z']
            available = [l for l in letters if l not in used_letters]
            if available:
                used_letters.append(random.choice(available))

        return used_letters


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

    # Scoring configuration
    unique_answer_points = models.IntegerField(default=10)
    valid_answer_points = models.IntegerField(default=5)
    invalid_answer_points = models.IntegerField(default=0)

    def __str__(self):
        return f"Config for {self.game_session.game_code}"



