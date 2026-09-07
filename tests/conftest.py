"""
conftest.py — pytest configuration and shared fixtures.

Kept minimal: test classes in test_services.py are self-contained.
This file exists to configure pytest settings and the sys.path so
modules can be imported from their service directories.
"""
import sys
import os
import pytest

# Add all service directories to sys.path so tests can import their modules directly.
# This avoids needing an __init__.py or package install for testing.
for service_dir in ["api-gateway", "user-service", "order-service", "ai-service"]:
    service_path = os.path.join(os.path.dirname(__file__), "..", service_dir)
    abs_path = os.path.abspath(service_path)
    if abs_path not in sys.path:
        sys.path.insert(0, abs_path)
