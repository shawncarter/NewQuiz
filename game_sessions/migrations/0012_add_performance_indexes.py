# Generated manually for adding performance indexes
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('game_sessions', '0011_multiplechoicequestion_is_specialist'),
    ]

    operations = [
        # Add index on MultipleChoiceQuestion.last_used for question selection queries
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS game_sessions_multiplechoicequestion_last_used_idx ON game_sessions_multiplechoicequestion(last_used);",
            reverse_sql="DROP INDEX IF EXISTS game_sessions_multiplechoicequestion_last_used_idx;"
        ),
        
        # Add index on MultipleChoiceQuestion.usage_count for question selection queries  
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS game_sessions_multiplechoicequestion_usage_count_idx ON game_sessions_multiplechoicequestion(usage_count);",
            reverse_sql="DROP INDEX IF EXISTS game_sessions_multiplechoicequestion_usage_count_idx;"
        ),
        
        # Add composite index on GameSession.game_code, current_round_number for game lookups
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS game_sessions_gamesession_code_round_idx ON game_sessions_gamesession(game_code, current_round_number);",
            reverse_sql="DROP INDEX IF EXISTS game_sessions_gamesession_code_round_idx;"
        ),
        
        # Add composite index on MultipleChoiceQuestion category and usage for smart selection
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS game_sessions_multiplechoicequestion_category_usage_idx ON game_sessions_multiplechoicequestion(category, usage_count, last_used);",
            reverse_sql="DROP INDEX IF EXISTS game_sessions_multiplechoicequestion_category_usage_idx;"
        ),
    ]