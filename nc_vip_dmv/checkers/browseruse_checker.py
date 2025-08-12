from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from browser_use import Agent
from browser_use.llm import ChatOpenAI
import inspect


@dataclass
class Slot:
    label: str

    def signature(self) -> str:
        return self.label


@dataclass
class AvailabilityResult:
    office_name: str
    office_url: Optional[str]
    available: bool
    slots: List[Slot]
    raw: Optional[str] = None


async def check_with_browser_use(office_name: str, office_url: Optional[str]) -> AvailabilityResult:
    """Use browser-use Agent to navigate the SPA and check availability without assuming a static URL.

    Strategy:
    - Start from https://skiptheline.ncdot.gov/webapp/#/ (or provided office_url within that domain).
    - Find the office by name inside the Locations view and open its detail.
    - Click Make an Appointment and let the site generate the unique UUID path automatically.
    - Do NOT attempt to book or confirm; only identify the earliest available slot within the next 60 days.
    - Return a single line: 'AVAILABLE: <summary>' or 'NONE: <reason>'.
    """

    # Note: Requires OPENAI_API_KEY in environment
    task_instructions = (
        "You are checking appointment availability on the NCDMV Skip-the-Line site. "
        "Rules: 1) Only operate on the domain skiptheline.ncdot.gov, 2) Start strictly at https://skiptheline.ncdot.gov/ (root), "
        "3) Do not manually navigate to /webapp/#/ or any #/location/... route; only reach them by clicking links from the root, "
        "4) Do not attempt to book or confirm, 5) If a unique UUID appears (e.g., /Webapp/Appointment/Index/<uuid>), treat it as ephemeral, "
        "6) Your output must be a single line starting with AVAILABLE or NONE.\n\n"
        "Goal: Determine whether any appointment slots exist within the next 60 days for the specified office.\n"
        "Process: Begin at https://skiptheline.ncdot.gov/. From the landing page, click 'Make an Appointment' or the equivalent to enter the flow. "
        "Then find the office by name and open its details. View the appointment calendar (handle simple consent/continue if needed). "
        "Once times are visible, identify the earliest date and 1-3 example times (if any). Do not proceed beyond viewing.\n\n"
        "Output format (strict): If slots exist, return: AVAILABLE: <earliest date> <example time(s)> <short note>. "
        "If none exist, return: NONE: <short reason>."
    )

    base_note = (
        "Base: https://skiptheline.ncdot.gov/. "
        + f"Office name: {office_name}."
    )
    full_task = task_instructions + "\n\nContext: " + base_note

    agent = Agent(
        task=full_task,
        llm=ChatOpenAI(model="o4-mini", temperature=0),
        max_actions_per_step=24,
    )

    result = await agent.run()
    # browser-use may expose final_result as a string or as a callable; be defensive
    raw_output = None
    final_attr = getattr(result, "final_result", None)
    if isinstance(final_attr, str):
        raw_output = final_attr
    elif callable(final_attr):
        try:
            if inspect.iscoroutinefunction(final_attr):
                raw_output = await final_attr()  # type: ignore[misc]
            else:
                raw_output = final_attr()  # type: ignore[misc]
        except Exception:
            raw_output = None
    elif isinstance(result, str):
        raw_output = result
    else:
        try:
            raw_output = str(result)
        except Exception:
            raw_output = None

    out_text = (raw_output or "").strip()

    available = out_text.upper().startswith("AVAILABLE")
    slots: List[Slot] = []
    if available:
        slots.append(Slot(label=out_text[:200]))

    return AvailabilityResult(
        office_name=office_name,
        office_url=office_url,
        available=available,
        slots=slots,
        raw=out_text,
    )
