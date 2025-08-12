from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from browser_use import Agent
from browser_use.llm import ChatOpenAI


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
    # Note: Requires OPENAI_API_KEY in environment
    agent = Agent(
        task=(
            "Open the North Carolina DMV 'Skip the Line' appointment page for the given office URL, "
            "determine if any appointment slots are available in the next 60 days, and return a compact summary. "
            "If there are slots, list the earliest date and at least 1-3 example times. "
            "Return strictly one line starting with AVAILABLE or NONE, followed by a brief reason."
        ),
        llm=ChatOpenAI(model="o4-mini", temperature=0),
        max_actions_per_step=12,
    )

    url_note = f" The office URL is: {office_url}." if office_url else ""
    result = await agent.run(input=f"Office: {office_name}.{url_note}")
    out_text = (result.final_result or "").strip()

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
