import uuid
from core.models import Merchant, BankAccount, LedgerEntry, LedgerEntryType

MERCHANTS = [
    {
        "id": uuid.UUID('00000000-0000-0000-0000-000000000001'),
        "name": "Acme Freelance",
        "email": "acme@merchant.com",
        "initial_balance": 5000000,
    },
    {
        "id": uuid.UUID('00000000-0000-0000-0000-000000000002'),
        "name": "Global Agency India",
        "email": "global@merchant.com",
        "initial_balance": 15000000,
    },
    {
        "id": uuid.UUID('00000000-0000-0000-0000-000000000003'),
        "name": "Dev Studio Tech",
        "email": "dev@merchant.com",
        "initial_balance": 250000,
    }
]

BANK_ACCOUNT_ID_PREFIX = '00000000-0000-0000-0000-00000000001'

def seed():
    print("Seeding database with 3 merchants...")
    
    for i, data in enumerate(MERCHANTS):
        merchant, created = Merchant.objects.get_or_create(
            id=data["id"],
            defaults={
                'name': data["name"],
                'email': data["email"],
            }
        )
        if created:
            print(f"Created Merchant: {merchant.name}")
            
            LedgerEntry.objects.create(
                merchant=merchant,
                entry_type=LedgerEntryType.CREDIT,
                amount=data["initial_balance"],
                balance_after=data["initial_balance"],
                description="Initial customer payment (USD converted)"
            )
        else:
            print(f"Merchant {merchant.name} already exists.")

        bank_id = uuid.UUID(f"{BANK_ACCOUNT_ID_PREFIX}{i}")
        bank_account, created = BankAccount.objects.get_or_create(
            id=bank_id,
            merchant=merchant,
            defaults={
                'account_holder_name': f'{data["name"]} Director',
                'account_number': f'1234567890{i}',
                'ifsc_code': 'HDFC0001234',
                'is_verified': True
            }
        )
        if created:
            print(f"Created Bank Account for {merchant.name}")

    print("\nSeeding complete! You can now use the React dashboard.")
    print("By default, the dashboard uses Merchant 1:")
    print("MERCHANT_ID: 00000000-0000-0000-0000-000000000001")
    print("BANK_ACCOUNT_ID: 00000000-0000-0000-0000-000000000010")

seed()
