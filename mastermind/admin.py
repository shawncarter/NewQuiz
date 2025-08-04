"""
Mastermind Admin Interface

Django admin configuration for mastermind models.
"""

from django.contrib import admin
from .models import Subject, SpecialistQuestion, MastermindRound, PlayerQuestionSet, MastermindAnswer


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'question_count', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'description']
    ordering = ['name']
    
    def question_count(self, obj):
        return obj.questions.count()
    question_count.short_description = 'Questions'


@admin.register(SpecialistQuestion)
class SpecialistQuestionAdmin(admin.ModelAdmin):
    list_display = ['subject', 'question_preview', 'difficulty', 'usage_count', 'is_ai_generated', 'last_used']
    list_filter = ['subject', 'difficulty', 'is_ai_generated', 'created_at']
    search_fields = ['question_text', 'subject__name']
    ordering = ['subject', 'usage_count']
    readonly_fields = ['usage_count', 'last_used', 'created_at']
    
    def question_preview(self, obj):
        return obj.question_text[:80] + '...' if len(obj.question_text) > 80 else obj.question_text
    question_preview.short_description = 'Question'


@admin.register(MastermindRound)
class MastermindRoundAdmin(admin.ModelAdmin):
    list_display = ['game_session', 'round_number', 'state', 'current_player', 'completed_count', 'created_at']
    list_filter = ['state', 'created_at', 'updated_at']
    search_fields = ['game_session__game_code', 'current_player__name']
    ordering = ['-created_at']
    readonly_fields = ['created_at', 'updated_at']
    
    def completed_count(self, obj):
        return obj.completed_players.count()
    completed_count.short_description = 'Completed Players'


@admin.register(PlayerQuestionSet)
class PlayerQuestionSetAdmin(admin.ModelAdmin):
    list_display = ['mastermind_round', 'player', 'question_count', 'created_at']
    list_filter = ['created_at']
    search_fields = ['player__name', 'mastermind_round__game_session__game_code']
    ordering = ['-created_at']
    readonly_fields = ['created_at']
    
    def question_count(self, obj):
        return len(obj.questions) if obj.questions else 0
    question_count.short_description = 'Question Count'


@admin.register(MastermindAnswer)
class MastermindAnswerAdmin(admin.ModelAdmin):
    list_display = ['mastermind_round', 'player', 'question_index', 'is_correct', 'response_time_ms', 'answered_at']
    list_filter = ['is_correct', 'answered_at']
    search_fields = ['player__name', 'mastermind_round__game_session__game_code']
    ordering = ['-answered_at']
    readonly_fields = ['answered_at']