import os
import requests
from datetime import datetime
from django.core.management.base import BaseCommand
from apps.people.models import Person  # Ajustá si tu app tiene otro nombre

class Command(BaseCommand):
    help = 'Send birthday messages to people whose birthday is today.'

    def handle(self, *args, **options):
        api_url = os.getenv('API_WPP_SEND_BIRTHDAY')
        if not api_url:
            self.stderr.write("ERROR: Environment variable API_WPP_SEND_BIRTHDAY not set.")
            return

        today = datetime.now()
        today_day = today.day
        today_month = today.month

        persons = Person.objects.filter(
            birth_date__day=today_day,
            birth_date__month=today_month,
            deleted__isnull=True
        )

        if not persons.exists():
            self.stdout.write("No birthdays today.")
            return

        sent = 0
        failed = 0

        for person in persons:
            if not person.phone or not person.name:
                self.stdout.write(f"Skipping person ID {person.id} (missing phone or name)")
                continue

            payload = {
                "phone": person.phone,
                "name": person.name
            }

            try:
                response = requests.post(api_url, json=payload, timeout=5)
                response.raise_for_status()
                sent += 1
                self.stdout.write(f"🎉 Sent birthday message to {person.name} ({person.phone})")
            except requests.RequestException as e:
                failed += 1
                self.stderr.write(f"❌ Failed to send to {person.name} ({person.phone}): {str(e)}")

        self.stdout.write(f"✅ Done: Sent {sent}, Failed {failed}")
