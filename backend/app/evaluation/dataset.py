"""
Evaluation dataset for the Clinical AI Assistant.

Each EvalCase contains:
  question        — the clinical question to ask
  query_type      — QueryType enum value
  expected_facts  — list of facts the answer MUST contain (used by keyword metrics)
  must_not_contain— phrases that must NOT appear (hallucination / safety checks)
  reference       — authoritative source the answer should align with
  category        — human label for reporting (treatment / diagnosis / lifestyle / general)

Dataset is intentionally drawn from the three ingested reference documents so
keyword checks are grounded in the actual knowledge base content.
"""
from dataclasses import dataclass, field
from app.schemas.query import QueryType


@dataclass
class EvalCase:
    id: str
    question: str
    query_type: QueryType
    expected_facts: list[str]          # at least one substring per fact must appear in answer
    must_not_contain: list[str]        # strings that must NOT appear
    reference: str                     # authoritative source label
    category: str                      # treatment | diagnosis | lifestyle | general
    patient_context: str | None = None


EVAL_DATASET: list[EvalCase] = [

    # ── TREATMENT ─────────────────────────────────────────────────────────

    EvalCase(
        id="T-001",
        question="What are the first-line pharmacologic agents for hypertension according to ACC/AHA guidelines?",
        query_type=QueryType.clinical_guideline,
        expected_facts=[
            "thiazide",
            "ACE inhibitor",
            "calcium channel blocker",
        ],
        must_not_contain=["beta-blocker as first-line", "beta blockers are first"],
        reference="ACC/AHA 2017 Hypertension Guidelines",
        category="treatment",
    ),
    EvalCase(
        id="T-002",
        question="What is the standard adult dosing for metformin and what is the maximum daily dose?",
        query_type=QueryType.drug_reference,
        expected_facts=[
            "500",
            "2550",
            "meals",
        ],
        must_not_contain=["3000 mg", "4000 mg"],
        reference="Clinical Drug Reference — Metformin",
        category="treatment",
    ),
    EvalCase(
        id="T-003",
        question="When is metformin contraindicated due to renal function?",
        query_type=QueryType.drug_reference,
        expected_facts=[
            "eGFR",
            "30",
            "contraindicated",
        ],
        must_not_contain=["eGFR less than 60", "eGFR below 45"],
        reference="Clinical Drug Reference — Metformin",
        category="treatment",
    ),
    EvalCase(
        id="T-004",
        question="What is the preferred fourth-line agent for resistant hypertension?",
        query_type=QueryType.clinical_guideline,
        expected_facts=[
            "spironolactone",
        ],
        must_not_contain=["amlodipine as fourth", "lisinopril as fourth"],
        reference="ACC/AHA 2017 Hypertension Guidelines",
        category="treatment",
    ),
    EvalCase(
        id="T-005",
        question="What are the cardiovascular outcome benefits of GLP-1 receptor agonists in type 2 diabetes?",
        query_type=QueryType.clinical_guideline,
        expected_facts=[
            "ASCVD",
            "cardiovascular",
            "liraglutide",
        ],
        must_not_contain=[],
        reference="ADA Standards of Medical Care in Diabetes",
        category="treatment",
    ),
    EvalCase(
        id="T-006",
        question="What lisinopril dosing adjustments are needed and what are its main contraindications?",
        query_type=QueryType.drug_reference,
        expected_facts=[
            "angioedema",
            "pregnancy",
            "bilateral renal artery stenosis",
        ],
        must_not_contain=[],
        reference="Clinical Drug Reference — Lisinopril",
        category="treatment",
    ),
    EvalCase(
        id="T-007",
        question="What statin intensity is recommended for patients with established ASCVD?",
        query_type=QueryType.clinical_guideline,
        expected_facts=[
            "high-intensity",
            "atorvastatin",
        ],
        must_not_contain=["low-intensity for ASCVD"],
        reference="ADA Standards of Medical Care in Diabetes",
        category="treatment",
    ),

    # ── DIAGNOSIS ─────────────────────────────────────────────────────────

    EvalCase(
        id="D-001",
        question="What are the diagnostic criteria for hypertension according to the 2017 ACC/AHA guidelines?",
        query_type=QueryType.clinical_guideline,
        expected_facts=[
            "130",
            "80",
            "systolic",
        ],
        must_not_contain=["140/90 as the new threshold", "JNC 7 threshold is current"],
        reference="ACC/AHA 2017 Hypertension Guidelines",
        category="diagnosis",
    ),
    EvalCase(
        id="D-002",
        question="What HbA1c level is used to diagnose diabetes mellitus?",
        query_type=QueryType.clinical_guideline,
        expected_facts=[
            "6.5%",
            "HbA1c",
        ],
        must_not_contain=["7.0% for diagnosis", "8% for diagnosis"],
        reference="ADA Standards of Medical Care in Diabetes",
        category="diagnosis",
    ),
    EvalCase(
        id="D-003",
        question="What defines prediabetes by fasting plasma glucose?",
        query_type=QueryType.clinical_guideline,
        expected_facts=[
            "100",
            "125",
            "fasting",
        ],
        must_not_contain=[],
        reference="ADA Standards of Medical Care in Diabetes",
        category="diagnosis",
    ),
    EvalCase(
        id="D-004",
        question="How is diabetic kidney disease detected and what defines microalbuminuria?",
        query_type=QueryType.clinical_guideline,
        expected_facts=[
            "UACR",
            "30",
            "eGFR",
        ],
        must_not_contain=[],
        reference="ADA Standards of Medical Care in Diabetes",
        category="diagnosis",
    ),
    EvalCase(
        id="D-005",
        question="What is the definition of resistant hypertension?",
        query_type=QueryType.clinical_guideline,
        expected_facts=[
            "three",
            "goal",
            "maximum",
        ],
        must_not_contain=[],
        reference="ACC/AHA 2017 Hypertension Guidelines",
        category="diagnosis",
    ),

    # ── LIFESTYLE ─────────────────────────────────────────────────────────

    EvalCase(
        id="L-001",
        question="What blood pressure target is recommended for most adults with hypertension?",
        query_type=QueryType.clinical_guideline,
        expected_facts=[
            "130/80",
        ],
        must_not_contain=["140/90 for all adults"],
        reference="ACC/AHA 2017 Hypertension Guidelines",
        category="lifestyle",
    ),
    EvalCase(
        id="L-002",
        question="What vaccinations are recommended for patients with diabetes?",
        query_type=QueryType.clinical_guideline,
        expected_facts=[
            "vaccination",
        ],
        must_not_contain=[],
        reference="ADA Standards of Medical Care in Diabetes",
        category="lifestyle",
    ),
    EvalCase(
        id="L-003",
        question="What foot care monitoring is recommended for diabetic patients?",
        query_type=QueryType.clinical_guideline,
        expected_facts=[
            "foot",
            "annual",
            "monofilament",
        ],
        must_not_contain=[],
        reference="ADA Standards of Medical Care in Diabetes",
        category="lifestyle",
    ),

    # ── DRUG SAFETY ───────────────────────────────────────────────────────

    EvalCase(
        id="S-001",
        question="What is the risk of combining an ACE inhibitor with an ARB?",
        query_type=QueryType.drug_reference,
        expected_facts=[
            "contraindicated",
            "hyperkalemia",
            "acute kidney injury",
        ],
        must_not_contain=["safe to combine", "recommended combination"],
        reference="ACC/AHA 2017 Hypertension Guidelines",
        category="treatment",
    ),
    EvalCase(
        id="S-002",
        question="What are the QT prolongation risks with ondansetron and which patients need ECG monitoring?",
        query_type=QueryType.drug_reference,
        expected_facts=[
            "QT",
            "ECG",
            "electrolyte",
        ],
        must_not_contain=["no cardiac risk", "QT prolongation is not a concern"],
        reference="Clinical Drug Reference — Ondansetron",
        category="treatment",
    ),
    EvalCase(
        id="S-003",
        question="What are the drug interaction risks between atorvastatin and CYP3A4 inhibitors?",
        query_type=QueryType.drug_reference,
        expected_facts=[
            "CYP3A4",
            "myopathy",
            "clarithromycin",
        ],
        must_not_contain=["no interaction risk"],
        reference="Clinical Drug Reference — Atorvastatin",
        category="treatment",
    ),
]
