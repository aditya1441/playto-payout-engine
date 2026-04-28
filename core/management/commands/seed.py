import uuid
from django.core.management.base import BaseCommand
from core.models import Merchant, BankAccount, LedgerEntry, LedgerEntryType


MERCHANTS = [
    {
        'id': uuid.UUID('00000000-0000-0000-0000-000000000001'),
        'name': 'Acme Freelance',
        'email': 'acme@merchant.com',
        'credits': [5000000, 2500000, 750000],  # multiple client payments
    },
    {
        'id': uuid.UUID('00000000-0000-0000-0000-000000000002'),
        'name': 'Global Agency India',
        'email': 'global@merchant.com',
        'credits': [15000000, 8000000],
    },
    {
        'id': uuid.UUID('00000000-0000-0000-0000-000000000003'),
        'name': 'Dev Studio Tech',
        'email': 'dev@merchant.com',
        'credits': [250000, 1200000, 400000],
    },
]

BANK_ACCOUNT_PREFIX = '00000000-0000-0000-0000-00000000001'


class Command(BaseCommand):
    help = 'Seed merchants, bank accounts, and credit history'

    def handle(self, *args, **options):
        for i, data in enumerate(MERCHANTS):
            merchant, created = Merchant.objects.get_or_create(
                id=data['id'],
                defaults={'name': data['name'], 'email': data['email']},
            )
            action = 'Created' if created else 'Exists'
            self.stdout.write(f"  {action}: {merchant.name}")

            # Create bank account
            bank_id = uuid.UUID(f"{BANK_ACCOUNT_PREFIX}{i}")
            BankAccount.objects.get_or_create(
                id=bank_id, merchant=merchant,
                defaults={
                    'account_holder_name': f"{data['name']} Director",
                    'account_number': f'1234567890{i}',
                    'ifsc_code': 'HDFC0001234',
                    'is_verified': True,
                },
            )

            # Seed credit history only if merchant was just created
            if created:
                running = 0
                for j, amt in enumerate(data['credits']):
                    running += amt
                    LedgerEntry.objects.create(
                        merchant=merchant,
                        entry_type=LedgerEntryType.CREDIT,
                        amount=amt,
                        balance_after=running,
                        description=f"Client payment #{j+1} (USD converted)",
                    )
                self.stdout.write(f"    Seeded {len(data['credits'])} credits, total: ₹{running/100:,.2f}")

        self.stdout.write(self.style.SUCCESS('\nDone. Dashboard merchants:'))
        for i, m in enumerate(MERCHANTS):
            self.stdout.write(f"  {m['name']}: {m['id']}")
