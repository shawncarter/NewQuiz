# Generated by Django 5.2.3 on 2025-06-21 21:31

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('game_sessions', '0004_auto_20250621_1753'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='gameround',
            unique_together=None,
        ),
        migrations.RemoveField(
            model_name='gameround',
            name='category',
        ),
        migrations.RemoveField(
            model_name='gameround',
            name='game_session',
        ),
    ]
