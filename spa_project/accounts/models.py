from django.db import models
# CustomerProfile has been moved to customers app
# This import alias maintains backward compatibility
from customers.models import CustomerProfile  # noqa: F401
