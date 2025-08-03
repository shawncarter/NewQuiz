"""
Shared Models

Unified question model to replace MultipleChoiceQuestion and SpecialistQuestion
with a single Question model that supports both general and specialist questions.
"""

from django.db import models
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


class Subject(models.Model):
    """Specialist subjects for specialist questions"""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return self.name


class Question(models.Model):
    """Unified model for all question types (general and specialist)"""
    
    QUESTION_TYPE_CHOICES = [
        ('general', 'General Knowledge'),
        ('specialist', 'Specialist Subject'),
    ]
    
    DIFFICULTY_CHOICES = [
        ('easy', 'Easy'),
        ('medium', 'Medium'),
        ('hard', 'Hard'),
    ]
    
    # Core question fields
    question_text = models.TextField()
    choices = models.JSONField()
    correct_answer = models.CharField(max_length=255)
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPE_CHOICES, default='general')
    
    # Category/Subject fields
    category = models.CharField(max_length=100, blank=True, help_text="Category for general questions")
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, null=True, blank=True, 
                               related_name='questions', help_text="Subject for specialist questions")
    
    # Optional difficulty (mainly for specialist questions)
    difficulty = models.CharField(max_length=20, choices=DIFFICULTY_CHOICES, 
                                default='medium', blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    last_used = models.DateTimeField(null=True, blank=True)
    usage_count = models.IntegerField(default=0)
    is_ai_generated = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['usage_count', 'last_used']
        indexes = [
            # Performance indexes for question selection
            models.Index(fields=['question_type', 'category', 'usage_count', 'last_used']),
            models.Index(fields=['question_type', 'subject', 'usage_count', 'last_used']),
            models.Index(fields=['subject', 'difficulty']),
            models.Index(fields=['last_used']),
            models.Index(fields=['usage_count']),
        ]
        constraints = [
            # Ensure general questions have category, specialist questions have subject
            models.CheckConstraint(
                check=(
                    (models.Q(question_type='general') & ~models.Q(category='')) |
                    (models.Q(question_type='specialist') & models.Q(subject__isnull=False))
                ),
                name='question_type_category_subject_consistency'
            ),
            # Ensure question_text is unique within the same type and category/subject
            models.UniqueConstraint(
                fields=['question_text', 'question_type', 'category'],
                condition=models.Q(question_type='general'),
                name='unique_general_question_text'
            ),
            models.UniqueConstraint(
                fields=['question_text', 'question_type', 'subject'],
                condition=models.Q(question_type='specialist'),
                name='unique_specialist_question_text'
            ),
        ]
    
    def __str__(self):
        if self.question_type == 'specialist' and self.subject:
            return f"{self.subject.name}: {self.question_text[:50]}..."
        else:
            return f"{self.category}: {self.question_text[:50]}..."
    
    def clean(self):
        """Validate model constraints"""
        from django.core.exceptions import ValidationError
        
        if self.question_type == 'general':
            if not self.category or self.category.strip() == '':
                raise ValidationError("General questions must have a category")
            if self.subject is not None:
                raise ValidationError("General questions should not have a subject")
        elif self.question_type == 'specialist':
            if self.subject is None:
                raise ValidationError("Specialist questions must have a subject")
            # Category can be empty for specialist questions or derived from subject
            if not self.category:
                self.category = self.subject.name
    
    def save(self, *args, **kwargs):
        """Override save to ensure data consistency"""
        self.full_clean()
        super().save(*args, **kwargs)
    
    def mark_as_used(self):
        """Mark this question as used"""
        self.usage_count += 1
        self.last_used = timezone.now()
        self.save(update_fields=['usage_count', 'last_used'])
    
    @property
    def is_specialist(self):
        """Backward compatibility property"""
        return self.question_type == 'specialist'
    
    @property
    def display_category(self):
        """Get display category (category for general, subject name for specialist)"""
        if self.question_type == 'specialist' and self.subject:
            return self.subject.name
        return self.category
    
    @classmethod
    def get_general_questions(cls, category: str = None):
        """Get general knowledge questions, optionally filtered by category"""
        queryset = cls.objects.filter(question_type='general')
        if category:
            queryset = queryset.filter(category=category)
        return queryset
    
    @classmethod
    def get_specialist_questions(cls, subject_name: str = None, subject_obj: 'Subject' = None):
        """Get specialist questions, optionally filtered by subject"""
        queryset = cls.objects.filter(question_type='specialist')
        if subject_obj:
            queryset = queryset.filter(subject=subject_obj)
        elif subject_name:
            queryset = queryset.filter(subject__name=subject_name)
        return queryset