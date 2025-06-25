from django.core.management.base import BaseCommand
from game_sessions.models import GameType, GameCategory


class Command(BaseCommand):
    help = 'Set up initial game types and categories'

    def handle(self, *args, **options):
        # Create the Flower, Fruit and Veg game type
        game_type, created = GameType.objects.get_or_create(
            name="Letter Categories",
            defaults={
                'description': "Players think of items in specific categories that start with a given letter"
            }
        )
        
        if created:
            self.stdout.write(f"Created game type: {game_type.name}")
        else:
            self.stdout.write(f"Game type already exists: {game_type.name}")
        
        # Create categories
        categories = [
            "Flowers",
            "Fruits", 
            "Vegetables",
            "Movies",
            "Boys Names",
            "Girls Names",
            "Animals",
            "Countries",
            "Cities",
            "Foods",
            "Brands",
            "TV Shows",
            "Books",
            "Colors",
            "Sports"
        ]
        
        created_count = 0
        for category_name in categories:
            category, created = GameCategory.objects.get_or_create(
                name=category_name,
                game_type=game_type
            )
            if created:
                created_count += 1
                self.stdout.write(f"Created category: {category_name}")
        
        if created_count > 0:
            self.stdout.write(
                self.style.SUCCESS(f"Successfully created {created_count} new categories")
            )
        else:
            self.stdout.write("All categories already exist")
