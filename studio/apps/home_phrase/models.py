from django.db import models


class HomePhrase(models.Model):
    title = models.CharField(max_length=150, blank=True, default='')
    phrase = models.TextField()
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Frase del home'

    def __str__(self):
        return f"{self.title} – {self.phrase[:40]}" if self.title else self.phrase[:60]

    # @classmethod
    # def get(cls):
    # obj, _ = cls.objects.get_or_create(pk=1, defaults={'text': ''})
    # return obj
