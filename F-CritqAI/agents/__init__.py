"""
agents package — exposes root_agent for ADK CLI (`adk run agents`).
"""
from .orchestrator import create_orchestrator

root_agent = create_orchestrator()
