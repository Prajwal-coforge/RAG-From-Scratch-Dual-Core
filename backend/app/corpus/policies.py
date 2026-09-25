"""What each generated AeroPolicy document must contain, and its reviewed metadata.

The 10 and 30 minute deadlines are invented demonstration rules. Both
baggage versions carry the same escalation clause apart from the deadline,
so the conflict is the deadline and not who or what the rule applies to.
"""

from __future__ import annotations

from dataclasses import dataclass

CORPUS_ID = "airport-generated"
ISSUER = "AeroPolicy Airport"
OWNER = "AeroPolicy Airport Operations"
AS_OF = "2025-08-01"

ESCALATION_CLAUSE = (
    "When a baggage handler finds a damaged, leaking, or unattended checked bag in the baggage "
    "make-up area, the handler must escalate the incident to the Baggage Duty Supervisor within "
    "{minutes} minutes of discovery and must report it under AP-INC-002."
)

BAGGAGE_SECTIONS = (
    "1. Purpose and Scope",
    "2. Roles and Responsibilities",
    "3. Handling Standards",
    "4. Baggage Incident Escalation",
    "5. Restricted Items Found in Baggage",
    "6. Records and Review",
)


@dataclass(frozen=True)
class PolicySpec:
    key: str
    policy_id: str
    version: int
    title: str
    sections: tuple[str, ...]
    brief: str
    verbatim: tuple[str, ...]
    references: tuple[str, ...]
    forbidden: tuple[str, ...]
    effective_from: str
    effective_to: str | None
    publication_status: str
    clause_section: str
    section_forbidden: tuple[str, ...] = ()
    supersedes: str | None = None

    @property
    def document_version_id(self) -> str:
        return f"{CORPUS_ID}:{self.policy_id}:v{self.version}"

    @property
    def heading(self) -> str:
        return f"# {self.policy_id} {self.title}"

    @property
    def filename(self) -> str:
        return f"{self.policy_id}-v{self.version}.md"


BAGGAGE_BRIEF = (
    "Staff rules for handling checked baggage between the check-in belts, the baggage make-up area, "
    "and aircraft loading. Name the roles Baggage Handler, Baggage Duty Supervisor, and Ramp Lead. "
    "Section 3 covers bag tags, heavy bags, and fragile items. Section 4 covers escalation of "
    "baggage incidents and is the only place that states the escalation deadline. Section 5 says that a restricted item found in a bag is not handled further "
    "until it is approved or removed under the restricted-items approval procedure in AP-SEC-003. "
    "Section 6 covers the incident log and an annual policy review."
)

ESCALATION_SECTION = "4. Baggage Incident Escalation"
VAGUE_TIMING = ("immediately", "promptly", "as soon as", "without delay")

POLICIES = (
    PolicySpec(
        key="bag-v2",
        policy_id="AP-BAG-001",
        version=2,
        title="Staff Baggage Handling and Escalation",
        sections=BAGGAGE_SECTIONS,
        brief=BAGGAGE_BRIEF,
        verbatim=(ESCALATION_CLAUSE.format(minutes=10),),
        references=("AP-INC-002", "AP-SEC-003"),
        forbidden=("30 minutes",),
        effective_from="2025-07-01",
        effective_to=None,
        publication_status="active",
        clause_section=ESCALATION_SECTION,
        section_forbidden=VAGUE_TIMING,
        supersedes=f"{CORPUS_ID}:AP-BAG-001:v1",
    ),
    PolicySpec(
        key="inc-v1",
        policy_id="AP-INC-002",
        version=1,
        title="Operational Incident Response and Review",
        sections=(
            "1. Purpose and Scope",
            "2. Incident Categories",
            "3. Reporting and First Response",
            "4. Incident Coordinator Duties",
            "5. Post-Incident Review",
            "6. Records",
        ),
        brief=(
            "How any airport operational incident is reported, coordinated, and reviewed. Name the "
            "roles Reporting Staff Member, Incident Coordinator, and Airside Duty Manager. Categories "
            "include baggage, restricted-item, ramp safety, and equipment incidents. For the "
            "baggage-specific escalation deadline, point to AP-BAG-001 section 4 and do not state a "
            "deadline in minutes yourself. For a restricted item, point to AP-SEC-003. Section 5 "
            "describes a review meeting that records the cause and corrective actions."
        ),
        verbatim=(
            "The Incident Coordinator must open an incident record for every reported incident "
            "before the end of the shift in which it was reported.",
        ),
        references=("AP-BAG-001", "AP-SEC-003"),
        forbidden=("10 minutes", "30 minutes"),
        effective_from="2025-01-01",
        effective_to=None,
        publication_status="active",
        clause_section="4. Incident Coordinator Duties",
    ),
    PolicySpec(
        key="sec-v1",
        policy_id="AP-SEC-003",
        version=1,
        title="Staff Access, Restricted Items, and Approvals",
        sections=(
            "1. Purpose and Scope",
            "2. Staff Access Zones",
            "3. Restricted Items",
            "4. Approval Procedure for Restricted Items",
            "5. Restricted Items Found in Baggage",
            "6. Records and Review",
        ),
        brief=(
            "Staff access zones (landside, airside, baggage make-up area) and restricted items such "
            "as tools, blades, lithium batteries, and flammable liquids. Name the roles Requesting "
            "Staff Member, Line Manager, and Security Duty Manager. Section 4 gives the approval "
            "steps in order: a written request, line manager endorsement, then Security Duty "
            "Manager approval. These roles describe the approval procedure; they are not rules about "
            "who may read this document. Section 5 says a restricted item found in a checked bag is "
            "handled under AP-BAG-001 and reported under AP-INC-002."
        ),
        verbatim=(
            "Approval to carry a restricted item airside must be granted in writing by the Security "
            "Duty Manager before the item passes the staff screening point.",
        ),
        references=("AP-BAG-001", "AP-INC-002"),
        forbidden=("10 minutes", "30 minutes"),
        effective_from="2025-01-01",
        effective_to=None,
        publication_status="active",
        clause_section="4. Approval Procedure for Restricted Items",
    ),
    PolicySpec(
        key="bag-v1",
        policy_id="AP-BAG-001",
        version=1,
        title="Staff Baggage Handling and Escalation",
        sections=BAGGAGE_SECTIONS,
        brief=BAGGAGE_BRIEF,
        verbatim=(ESCALATION_CLAUSE.format(minutes=30),),
        references=("AP-INC-002", "AP-SEC-003"),
        forbidden=("10 minutes",),
        effective_from="2025-01-01",
        effective_to="2025-06-30",
        publication_status="superseded",
        clause_section=ESCALATION_SECTION,
        section_forbidden=VAGUE_TIMING,
    ),
)

BY_KEY = {spec.key: spec for spec in POLICIES}
