from django.core.management.base import BaseCommand
from game_sessions.models import GameType, GameCategory


class Command(BaseCommand):
    help = 'Set up initial game types and categories'

    def handle(self, *args, **_options):
        # Create the Flower, Fruit and Veg game type
        ffv_game_type, created = GameType.objects.get_or_create(
            name="Flower, Fruit & Veg",
            defaults={
                'description': "Players think of items in specific categories that start with a given letter"
            }
        )
        
        if created:
            self.stdout.write(f"Created game type: {ffv_game_type.name}")
        else:
            self.stdout.write(f"Game type already exists: {ffv_game_type.name}")
        
        # Create the Multiple Choice game type
        mc_game_type, created = GameType.objects.get_or_create(
            name="Multiple Choice",
            defaults={
                'description': "Players answer multiple choice questions from various categories"
            }
        )
        
        if created:
            self.stdout.write(f"Created game type: {mc_game_type.name}")
        else:
            self.stdout.write(f"Game type already exists: {mc_game_type.name}")
        
        # Update any existing "Letter Categories" to "Flower, Fruit & Veg"
        try:
            old_game_type = GameType.objects.get(name="Letter Categories")
            # Move all categories from old type to new type
            old_categories = old_game_type.categories.all()
            for category in old_categories:
                category.game_type = ffv_game_type
                category.save()
            # Delete the old game type
            old_game_type.delete()
            self.stdout.write(f"Migrated 'Letter Categories' to 'Flower, Fruit & Veg' and deleted old record")
        except GameType.DoesNotExist:
            pass
        
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
                game_type=ffv_game_type
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
