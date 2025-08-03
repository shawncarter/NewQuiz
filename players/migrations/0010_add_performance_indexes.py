# Generated manually for adding performance indexes
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('players', '0009_player_specialist_subject'),
    ]

    operations = [
        # Add composite index on Player.game_session, is_connected for connected player queries
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS players_player_game_session_connected_idx ON players_player(game_session_id, is_connected);",
            reverse_sql="DROP INDEX IF EXISTS players_player_game_session_connected_idx;"
        ),
        
        # Add composite index on PlayerAnswer for score calculations and answer lookups
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS players_playeranswer_player_round_idx ON players_playeranswer(player_id, round_number);",
            reverse_sql="DROP INDEX IF EXISTS players_playeranswer_player_round_idx;"
        ),
        
        # Add index on ScoreHistory.timestamp for score timeline queries
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS players_scorehistory_timestamp_idx ON players_scorehistory(timestamp);",
            reverse_sql="DROP INDEX IF EXISTS players_scorehistory_timestamp_idx;"
        ),
        
        # Add composite index on ScoreHistory for player score queries
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS players_scorehistory_player_round_idx ON players_scorehistory(player_id, round_number);",
            reverse_sql="DROP INDEX IF EXISTS players_scorehistory_player_round_idx;"
        ),
    ]