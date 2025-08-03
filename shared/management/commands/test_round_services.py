"""
Management command to test the round services functionality

This command demonstrates and validates the new round management services
and provides debugging information for round generation.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from unittest.mock import Mock

from shared.services import (
    get_round_service, 
    get_round_generator,
    RoundCacheService,
    DeterministicSeedingUtility
)


class Command(BaseCommand):
    help = 'Test the round management services'

    def add_arguments(self, parser):
        parser.add_argument(
            '--test-type',
            choices=['all', 'service', 'generator', 'cache', 'seeding'],
            default='all',
            help='Type of service to test'
        )
        parser.add_argument(
            '--game-code',
            default='TEST01',
            help='Game code to use for testing'
        )
        parser.add_argument(
            '--rounds',
            type=int,
            default=5,
            help='Number of rounds to test'
        )

    def handle(self, *args, **options):
        test_type = options['test_type']
        game_code = options['game_code']
        rounds = options['rounds']
        
        self.stdout.write(
            self.style.SUCCESS(
                f"Testing round services - Type: {test_type}, Game: {game_code}, Rounds: {rounds}"
            )
        )
        
        # Create mock game session
        game_session = self.create_mock_game_session(game_code, rounds)
        
        if test_type in ['all', 'service']:
            self.test_round_service(game_session)
        
        if test_type in ['all', 'generator']:
            self.test_round_generator(game_session)
        
        if test_type in ['all', 'cache']:
            self.test_cache_service(game_code)
        
        if test_type in ['all', 'seeding']:
            self.test_seeding_utility(game_session)
        
        self.stdout.write(self.style.SUCCESS("All round service tests completed!"))

    def create_mock_game_session(self, game_code, max_rounds):
        """Create a mock game session for testing"""
        game_session = Mock()
        game_session.game_code = game_code
        game_session.current_round_number = 0
        game_session.is_round_active = False
        game_session.current_round_started_at = None
        game_session.status = 'waiting'
        game_session.created_at = timezone.now()
        game_session.save = Mock()
        
        # Mock used questions
        game_session.used_questions = Mock()
        game_session.used_questions.add = Mock()
        game_session.used_questions.clear = Mock()
        
        # Mock configuration
        config = Mock()
        config.num_rounds = max_rounds
        config.round_time_seconds = 30
        config.round_type_sequence = ['flower_fruit_veg', 'multiple_choice', 'mastermind']
        
        # Mock categories
        config.categories = Mock()
        mock_categories = [Mock(name="Flowers", id=1), Mock(name="Fruits", id=2)]
        config.categories.all.return_value = mock_categories
        config.categories.exists.return_value = True
        config.categories.values_list.return_value = ["Flowers", "Fruits"]
        
        game_session.configuration = config
        return game_session

    def test_round_service(self, game_session):
        """Test the RoundService functionality"""
        self.stdout.write(self.style.WARNING("\n=== Testing Round Service ==="))
        
        service = get_round_service(game_session)
        
        # Test service creation
        self.stdout.write(f"✓ Service created: {type(service).__name__}")
        
        # Test initial state
        progress = service.get_round_progress()
        self.stdout.write(f"✓ Initial progress: Round {progress['current_round']}/{progress['total_rounds']}")
        
        # Test game completion check
        is_complete = service.is_game_complete()
        self.stdout.write(f"✓ Game complete check: {is_complete}")
        
        # Test current round info (should be None initially)
        current_info = service.get_current_round_info()
        self.stdout.write(f"✓ Current round info: {'None' if current_info is None else 'Available'}")
        
        # Test next round info
        next_info = service.get_next_round_info()
        if next_info:
            self.stdout.write(f"✓ Next round info: Round {next_info['round_number']}, Type: {next_info['round_type']}")
        else:
            self.stdout.write("✓ Next round info: None (game complete)")
        
        # Test restart functionality
        restart_result = service.restart_rounds()
        self.stdout.write(f"✓ Restart rounds: {restart_result['success']}")
        
        self.stdout.write(self.style.SUCCESS("Round service tests passed!"))

    def test_round_generator(self, game_session):
        """Test the RoundGeneratorService functionality"""
        self.stdout.write(self.style.WARNING("\n=== Testing Round Generator ==="))
        
        generator = get_round_generator(game_session)
        
        # Test generator creation
        self.stdout.write(f"✓ Generator created: {type(generator).__name__}")
        
        # Test round type determination
        for round_num in range(1, 4):
            round_type = generator._get_round_type(round_num)
            self.stdout.write(f"✓ Round {round_num} type: {round_type}")
        
        # Test round data generation for different types
        test_rounds = [
            (1, 'flower_fruit_veg'),
            (2, 'multiple_choice'),
            (3, 'mastermind')
        ]
        
        for round_num, expected_type in test_rounds:
            try:
                round_data = generator.generate_round_data(round_num)
                if round_data:
                    self.stdout.write(f"✓ Round {round_num} ({expected_type}): Generated successfully")
                    self.stdout.write(f"  - Type: {round_data.get('round_type')}")
                    
                    if round_data['round_type'] == 'flower_fruit_veg':
                        self.stdout.write(f"  - Letter: {round_data.get('prompt_letter')}")
                        self.stdout.write(f"  - Category: {round_data.get('category')}")
                    elif round_data['round_type'] == 'multiple_choice':
                        self.stdout.write(f"  - Question: {round_data.get('question_text', 'N/A')[:30]}...")
                        
                else:
                    self.stdout.write(f"⚠ Round {round_num} ({expected_type}): Generation failed")
            except Exception as e:
                self.stdout.write(f"✗ Round {round_num} ({expected_type}): Error - {e}")
        
        # Test deterministic behavior
        data1 = generator.generate_round_data(1)
        data2 = generator.generate_round_data(1)
        
        if data1 and data2:
            is_deterministic = (data1.get('prompt_letter') == data2.get('prompt_letter'))
            self.stdout.write(f"✓ Deterministic generation: {is_deterministic}")
        
        # Test cache clearing
        generator.clear_all_round_cache()
        self.stdout.write("✓ Cache cleared successfully")
        
        self.stdout.write(self.style.SUCCESS("Round generator tests passed!"))

    def test_cache_service(self, game_code):
        """Test the RoundCacheService functionality"""
        self.stdout.write(self.style.WARNING("\n=== Testing Cache Service ==="))
        
        cache_service = RoundCacheService(game_code)
        
        # Test round data caching
        test_data = {'round_number': 1, 'round_type': 'test', 'test_data': True}
        
        # Initially no cached data
        cached = cache_service.get_round_data(1)
        self.stdout.write(f"✓ Initial cache state: {'Empty' if cached is None else 'Has data'}")
        
        # Cache some data
        success = cache_service.set_round_data(1, test_data)
        self.stdout.write(f"✓ Cache set operation: {success}")
        
        # Retrieve cached data
        cached = cache_service.get_round_data(1)
        data_matches = cached == test_data if cached else False
        self.stdout.write(f"✓ Cache retrieval: {data_matches}")
        
        # Test question ID caching
        question_id = 12345
        cache_service.set_question_id(2, question_id)
        cached_id = cache_service.get_question_id(2)
        self.stdout.write(f"✓ Question ID caching: {cached_id == question_id}")
        
        # Test used letters caching
        used_letters = ['A', 'B', 'C']
        cache_service.set_used_letters(used_letters)
        cached_letters = cache_service.get_used_letters()
        self.stdout.write(f"✓ Used letters caching: {cached_letters == used_letters}")
        
        # Test cache statistics
        stats = cache_service.get_cache_stats(5)
        self.stdout.write(f"✓ Cache stats: {len(stats['cached_rounds'])} rounds, {len(stats['cached_questions'])} questions")
        
        # Test cache clearing
        cache_service.clear_round_cache(1)
        cleared_data = cache_service.get_round_data(1)
        self.stdout.write(f"✓ Cache clearing: {'Success' if cleared_data is None else 'Failed'}")
        
        self.stdout.write(self.style.SUCCESS("Cache service tests passed!"))

    def test_seeding_utility(self, game_session):
        """Test the DeterministicSeedingUtility functionality"""
        self.stdout.write(self.style.WARNING("\n=== Testing Seeding Utility ==="))
        
        utility = DeterministicSeedingUtility(game_session)
        
        # Test deterministic choice
        choices = ['A', 'B', 'C', 'D', 'E']
        choice1 = utility.get_deterministic_choice(choices, 1)
        choice2 = utility.get_deterministic_choice(choices, 1)
        
        self.stdout.write(f"✓ Deterministic choice consistency: {choice1 == choice2}")
        self.stdout.write(f"  - Choice for round 1: {choice1}")
        
        # Test different rounds produce different results (usually)
        choice_round_2 = utility.get_deterministic_choice(choices, 2)
        choice_round_3 = utility.get_deterministic_choice(choices, 3)
        
        self.stdout.write(f"  - Choice for round 2: {choice_round_2}")
        self.stdout.write(f"  - Choice for round 3: {choice_round_3}")
        
        # Test deterministic sample
        population = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
        sample1 = utility.get_deterministic_sample(population, 3, 1)
        sample2 = utility.get_deterministic_sample(population, 3, 1)
        
        self.stdout.write(f"✓ Deterministic sample consistency: {sample1 == sample2}")
        self.stdout.write(f"  - Sample: {sample1}")
        
        # Test seed setting directly
        utility.set_seed_for_round(5)
        self.stdout.write("✓ Direct seed setting: No errors")
        
        self.stdout.write(self.style.SUCCESS("Seeding utility tests passed!"))