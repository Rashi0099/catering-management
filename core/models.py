from django.db import models
import json


class TermAndCondition(models.Model):
    text = models.TextField(help_text="The actual term or condition rule.")
    order = models.IntegerField(default=0, help_text="Order in which this term appears.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return self.text[:60]


class InvoiceItem(models.Model):
    name = models.CharField(max_length=255, unique=True, help_text="Name of the service/item (e.g., Captain, Juice)")
    default_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, help_text="Default price/rate for manual invoices")
    order = models.IntegerField(default=0, help_text="Order in the dropdown lists")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return self.name


class InvoiceRecord(models.Model):
    """Saved record of every generated manual invoice."""
    client_name = models.CharField(max_length=255)
    client_phone = models.CharField(max_length=50, blank=True)
    event_date = models.DateField(null=True, blank=True)
    items_json = models.JSONField(default=list, help_text="Snapshot of line items at generation time")
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Invoice — {self.client_name} ({self.created_at.strftime('%d %b %Y')})"


class NoteCategory(models.Model):
    name = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class AdminNote(models.Model):
    """A single note card in the admin notepad."""
    title = models.CharField(max_length=255, blank=True, default='New Note')
    content = models.TextField(blank=True)
    category = models.ForeignKey(NoteCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name='notes')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return self.title or 'Untitled Note'
