from django.db import models

class SMTPConfiguration(models.Model):
    host = models.CharField(max_length=255, null=True, blank=True)
    port = models.PositiveIntegerField(default=587)
    username = models.CharField(max_length=255, null=True, blank=True)
    password = models.CharField(max_length=255, null=True, blank=True)
    use_tls = models.BooleanField(default=True)
    use_ssl = models.BooleanField(default=False)
    default_from_email = models.EmailField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now = True)

    class Meta:
            verbose_name = 'SMTP Configuration'
            verbose_name_plural = 'SMTP Configuration'
            
    def __str__(self):
        return f"{self.host} ({self.username})"