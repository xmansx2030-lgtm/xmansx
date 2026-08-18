from django.db import models


class TimestampedModel(models.Model):
    """أساس مشترك: created_at / updated_at لكل الكيانات."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
