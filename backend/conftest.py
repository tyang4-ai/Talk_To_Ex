"""Test environment bootstrap. Runs before app modules import config, so secrets
are present and the DB points at a throwaway file."""
import os
from cryptography.fernet import Fernet

os.environ.setdefault("FERNET_KEY", Fernet.generate_key().decode())
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic")
os.environ.setdefault("TWILIO_ACCOUNT_SID", "AC_test")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "test-twilio-token")
os.environ.setdefault("TWILIO_FROM_NUMBER", "+18005550100")
os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_x")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_test")
os.environ.setdefault("STRIPE_PRICE_ID", "price_test")
os.environ.setdefault("DATABASE_URL", "sqlite:///./_test_ttx.db")
