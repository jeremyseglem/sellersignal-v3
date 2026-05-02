"""
Agent voice API.

  POST /api/agent/generate-scripts — runs the voice product:
                                  reads voice_sample/stance/bio from the
                                  authenticated agent's profile, runs 6
                                  archetype LLM calls in parallel,
                                  stores results in
                                  agent_profiles_v3.generated_scripts.
                                  Sets voice_onboarding_completed_at on
                                  successful completion of all 6.

  PUT  /api/agent/edit-script   — agent's edit of one generated
                                  archetype script. Whole-script
                                  replacement. Used after generation
                                  when the agent has reviewed the LLM
                                  output and wants to save edited
                                  versions as canonical.

Authentication: same Bearer-token-from-Supabase-Auth pattern as
profile.py. Voice endpoints operate on the calling user's
agent_profiles_v3 row only — no cross-user access.

Migration dependency: 014_agent_voice_columns.sql must be applied
before these endpoints will work. The schema adds voice_sample,
stance, bio, generated_scripts, voice_onboarding_completed_at to
agent_profiles_v3.
"""
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from backend.api.db import get_supabase_client
from backend.api.auth import user_from_authorization as _user_from_authorization
from backend.agent_voice import prompts as voice_prompts


router = APIRouter()


# ── Models ───────────────────────────────────────────────────────

class EditScriptBody(BaseModel):
    """Agent's edit of one generated archetype script."""
    archetype: str
    script:    dict


# ── Endpoints ────────────────────────────────────────────────────

@router.post("/generate-scripts")
async def generate_scripts_endpoint(
    authorization: Optional[str] = Header(None),
):
    """
    Generate the agent's full set of archetype scripts.

    Reads voice_sample, stance, bio from the authenticated user's
    agent_profiles_v3 row. Runs 6 archetype LLM calls in parallel.
    Stores results in agent_profiles_v3.generated_scripts as a JSON
    object keyed by archetype name. Sets
    voice_onboarding_completed_at on successful completion.

    Returns:
      {
        "scripts": { archetype → parsed_script_object },
        "errors":  { archetype → error_string }   # only present if any failed
        "tokens":  total tokens consumed (for cost tracking)
        "voice_onboarding_completed_at": ISO timestamp
      }

    Errors:
      - 401 if not authenticated
      - 400 if voice_sample is missing (must be set first via PUT /api/profile)
      - 503 if Anthropic SDK is unavailable
      - 502 if all 6 generations fail
    """
    user = _user_from_authorization(authorization)
    supa = get_supabase_client()

    # Read profile inputs
    res = (supa.table('agent_profiles_v3')
           .select('voice_sample, stance, bio')
           .eq('id', user.id)
           .limit(1)
           .execute())
    rows = res.data or []
    if not rows:
        raise HTTPException(404, 'Agent profile not found.')

    profile = rows[0]
    voice_sample = profile.get('voice_sample') or ''
    stance = profile.get('stance') or {}
    bio = profile.get('bio') or {}

    # Voice sample is required — without it the system has no signal
    # to model. Stance and bio can be empty (defaults will apply).
    if not voice_sample.strip():
        raise HTTPException(
            400,
            'Voice sample required. Set voice_sample via PUT /api/profile '
            'before generating scripts.',
        )

    # Anthropic client
    try:
        from anthropic import Anthropic
    except ImportError as e:
        raise HTTPException(503, f'Anthropic SDK not available: {e}')
    client = Anthropic()

    # Run all 6 archetypes in parallel via ThreadPoolExecutor. The
    # Anthropic SDK is thread-safe; each generate_archetype_script
    # call is independent.
    results: dict[str, dict] = {}
    errors:  dict[str, str] = {}
    total_tokens = {'input': 0, 'output': 0}

    with ThreadPoolExecutor(max_workers=6) as pool:
        future_map = {
            pool.submit(
                voice_prompts.generate_archetype_script,
                client=client,
                voice_sample=voice_sample,
                stance=stance,
                bio=bio,
                archetype=arch,
            ): arch
            for arch in voice_prompts.ARCHETYPES
        }
        for fut in as_completed(future_map):
            arch = future_map[fut]
            try:
                r = fut.result()
                results[arch] = r
                if r.get('tokens_in'):    total_tokens['input']  += r['tokens_in']
                if r.get('tokens_out'):   total_tokens['output'] += r['tokens_out']
                if r.get('retry_tokens_in'):  total_tokens['input']  += r['retry_tokens_in']
                if r.get('retry_tokens_out'): total_tokens['output'] += r['retry_tokens_out']
            except Exception as e:
                errors[arch] = str(e)

    # If every archetype failed, surface as an error
    if not results and errors:
        raise HTTPException(502, f'All archetype generations failed: {errors}')

    # Store the parsed scripts back to the profile. Only store
    # archetypes that parsed cleanly — failed ones leave the slot
    # empty and the agent can retry.
    storable = {}
    for arch, r in results.items():
        if r.get('parsed') is not None:
            storable[arch] = r['parsed']
        else:
            errors[arch] = 'output failed to parse as JSON'

    completed_at = None
    if storable:
        # Update generated_scripts and (if all 6 succeeded) the
        # voice_onboarding_completed_at timestamp.
        update_payload: dict = {'generated_scripts': storable}
        if len(storable) == len(voice_prompts.ARCHETYPES):
            completed_at = datetime.now(timezone.utc).isoformat()
            update_payload['voice_onboarding_completed_at'] = completed_at

        upd = (supa.table('agent_profiles_v3')
               .update(update_payload)
               .eq('id', user.id)
               .execute())
        if not upd.data:
            raise HTTPException(500, 'Failed to write generated scripts to profile.')

    return {
        'scripts': storable,
        'errors':  errors if errors else None,
        'tokens':  total_tokens,
        'voice_onboarding_completed_at': completed_at,
    }


@router.put("/edit-script")
async def edit_script_endpoint(
    body: EditScriptBody,
    authorization: Optional[str] = Header(None),
):
    """
    Save the agent's edited version of one archetype script as
    canonical. Whole-script replacement: the body.script object
    overwrites generated_scripts[archetype] in the agent's profile.

    The agent has reviewed what the LLM produced, made edits, and
    is saving the final version. The system then renders the
    edited scripts at the dossier level.
    """
    user = _user_from_authorization(authorization)

    if body.archetype not in voice_prompts.ARCHETYPES:
        raise HTTPException(400, f'Unknown archetype: {body.archetype}')

    supa = get_supabase_client()

    # Read the current generated_scripts so we can splice in the
    # edited archetype without overwriting the others.
    res = (supa.table('agent_profiles_v3')
           .select('generated_scripts')
           .eq('id', user.id)
           .limit(1)
           .execute())
    rows = res.data or []
    if not rows:
        raise HTTPException(404, 'Agent profile not found.')

    current = rows[0].get('generated_scripts') or {}
    current[body.archetype] = body.script

    upd = (supa.table('agent_profiles_v3')
           .update({'generated_scripts': current})
           .eq('id', user.id)
           .execute())
    if not upd.data:
        raise HTTPException(500, 'Failed to write edited script to profile.')

    return {
        'archetype': body.archetype,
        'saved': True,
    }
