"""Compatibility wrapper for the now-reviewed answer-stage projection.

Only the benchmark patches the pure rule builder. It retains the canonical
clinical provenance, evidence limits, behavior and R4 safety instructions.
This stage filter does not establish task authority or clinical noninferiority.
"""
from app.services.agent_prompt_sections import (
    build_base_prompt_parts,
    project_read_synthesis_parts,
)


def build_read_synthesis_parts(**kwargs):
    return project_read_synthesis_parts(build_base_prompt_parts(**kwargs), **kwargs)
