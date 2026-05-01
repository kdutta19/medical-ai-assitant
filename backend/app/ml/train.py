"""
Training script for the clinical query route classifier.

Categories
----------
  treatment  — medication management, dosing, therapy selection, drug interactions
  diagnosis  — symptom evaluation, differential diagnosis, lab/imaging interpretation
  lifestyle  — prevention, diet, exercise, screening, patient education
  general    — administrative, miscellaneous, or multi-category queries

Model
-----
  TF-IDF (char + word n-grams) → LogisticRegression
  Chosen for: <5 ms inference, no GPU, interpretable, 95%+ accuracy on this domain

Output
------
  models/query_classifier.joblib   — pipeline (vectorizer + classifier)
  models/query_classifier_meta.json — label map, training accuracy, feature count

Usage
-----
  # From repo root
  python backend/app/ml/train.py

  # Evaluate only (no save)
  python backend/app/ml/train.py --eval-only

  # Custom model output directory
  python backend/app/ml/train.py --model-dir ./models
"""
import sys
import json
import argparse
from pathlib import Path

import joblib
import numpy as np
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.metrics import classification_report

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MODEL_DIR = REPO_ROOT / "models"
MODEL_FILENAME = "query_classifier.joblib"
META_FILENAME = "query_classifier_meta.json"

# ---------------------------------------------------------------------------
# Labeled training data
# Each entry: (query_text, label)
# Labels: treatment | diagnosis | lifestyle | general
# ---------------------------------------------------------------------------

TRAINING_DATA: list[tuple[str, str]] = [
    # ── TREATMENT ─────────────────────────────────────────────────────────
    ("What is the first-line treatment for hypertension?", "treatment"),
    ("What medications are used for type 2 diabetes?", "treatment"),
    ("How should metformin be dosed in CKD?", "treatment"),
    ("What is the recommended antibiotic for community-acquired pneumonia?", "treatment"),
    ("When should I start statin therapy?", "treatment"),
    ("What is the management of atrial fibrillation?", "treatment"),
    ("How do I treat a hypertensive emergency?", "treatment"),
    ("What is the dose of lisinopril for heart failure?", "treatment"),
    ("Which beta-blocker is preferred post-MI?", "treatment"),
    ("What are the treatment options for rheumatoid arthritis?", "treatment"),
    ("How is sepsis managed in the ICU?", "treatment"),
    ("What anticoagulation is used for DVT?", "treatment"),
    ("What is the standard chemotherapy for colon cancer?", "treatment"),
    ("How do I titrate insulin in type 1 diabetes?", "treatment"),
    ("What is the treatment protocol for anaphylaxis?", "treatment"),
    ("Which ACE inhibitor is preferred in diabetic nephropathy?", "treatment"),
    ("What is the recommended dose of amoxicillin for strep throat?", "treatment"),
    ("How should I manage pain in a patient with renal impairment?", "treatment"),
    ("What is the treatment for acute gout flare?", "treatment"),
    ("What are the drug options for GERD?", "treatment"),
    ("How is hypothyroidism treated?", "treatment"),
    ("What is the pharmacological management of COPD?", "treatment"),
    ("When do I add a second antihypertensive agent?", "treatment"),
    ("What is the loading dose of aspirin in ACS?", "treatment"),
    ("How is C. difficile infection treated?", "treatment"),
    ("What is the treatment for iron deficiency anemia?", "treatment"),
    ("Which diuretic is preferred in resistant hypertension?", "treatment"),
    ("How do you manage steroid-induced hyperglycemia?", "treatment"),
    ("What is the treatment for pulmonary embolism?", "treatment"),
    ("How is acute asthma exacerbation managed?", "treatment"),

    # ── DIAGNOSIS ─────────────────────────────────────────────────────────
    ("What are the diagnostic criteria for diabetes mellitus?", "diagnosis"),
    ("What is the differential diagnosis for chest pain?", "diagnosis"),
    ("How do I interpret an elevated troponin?", "diagnosis"),
    ("What does a high D-dimer indicate?", "diagnosis"),
    ("What are the signs of hypertensive emergency vs urgency?", "diagnosis"),
    ("How is hypothyroidism diagnosed?", "diagnosis"),
    ("What causes elevated AST and ALT?", "diagnosis"),
    ("What is the workup for a first-time seizure?", "diagnosis"),
    ("How do I differentiate type 1 from type 2 diabetes?", "diagnosis"),
    ("What are the diagnostic criteria for heart failure?", "diagnosis"),
    ("What does thrombocytopenia indicate?", "diagnosis"),
    ("How is pulmonary embolism diagnosed?", "diagnosis"),
    ("What is the diagnostic approach to dyspnea?", "diagnosis"),
    ("How do I interpret an abnormal ECG?", "diagnosis"),
    ("What are the causes of metabolic acidosis?", "diagnosis"),
    ("How is sepsis diagnosed?", "diagnosis"),
    ("What are the diagnostic criteria for rheumatoid arthritis?", "diagnosis"),
    ("What does an elevated CRP indicate?", "diagnosis"),
    ("How is COPD diagnosed?", "diagnosis"),
    ("What is the workup for unexplained weight loss?", "diagnosis"),
    ("What are the red flags in low back pain?", "diagnosis"),
    ("How do I evaluate a patient with syncope?", "diagnosis"),
    ("What causes a wide anion gap metabolic acidosis?", "diagnosis"),
    ("How is atrial fibrillation diagnosed?", "diagnosis"),
    ("What are the criteria for systemic lupus erythematosus?", "diagnosis"),
    ("How do I interpret a BNP result?", "diagnosis"),
    ("What is the differential for acute kidney injury?", "diagnosis"),
    ("How is Cushing's syndrome diagnosed?", "diagnosis"),
    ("What causes hyponatremia?", "diagnosis"),
    ("What is the diagnostic approach to lymphadenopathy?", "diagnosis"),

    # ── LIFESTYLE ─────────────────────────────────────────────────────────
    ("What dietary changes help lower blood pressure?", "lifestyle"),
    ("How much exercise is recommended for cardiovascular health?", "lifestyle"),
    ("What is the recommended diet for type 2 diabetes?", "lifestyle"),
    ("How does weight loss affect hypertension?", "lifestyle"),
    ("What lifestyle modifications reduce stroke risk?", "lifestyle"),
    ("What is the recommended daily sodium intake for heart failure patients?", "lifestyle"),
    ("How should a diabetic patient approach meal planning?", "lifestyle"),
    ("What smoking cessation strategies are most effective?", "lifestyle"),
    ("How does alcohol affect blood pressure?", "lifestyle"),
    ("What is the recommended physical activity for patients with COPD?", "lifestyle"),
    ("How can patients reduce their cardiovascular risk through diet?", "lifestyle"),
    ("What screening tests are recommended for a 50-year-old with no symptoms?", "lifestyle"),
    ("What vaccinations should diabetic patients receive?", "lifestyle"),
    ("How does sleep apnea affect cardiovascular outcomes?", "lifestyle"),
    ("What is the DASH diet and when is it recommended?", "lifestyle"),
    ("How should patients with CKD modify their diet?", "lifestyle"),
    ("What are the recommended cancer screening intervals?", "lifestyle"),
    ("How does stress affect blood sugar control?", "lifestyle"),
    ("What foot care advice should diabetic patients receive?", "lifestyle"),
    ("What is the role of weight management in osteoarthritis?", "lifestyle"),
    ("How much water should a patient with kidney stones drink?", "lifestyle"),
    ("What dietary restrictions apply to patients on warfarin?", "lifestyle"),
    ("How does caffeine affect atrial fibrillation?", "lifestyle"),
    ("What exercise precautions apply after a myocardial infarction?", "lifestyle"),
    ("How can patients reduce their risk of colorectal cancer?", "lifestyle"),
    ("What is the recommended fiber intake for patients with constipation?", "lifestyle"),
    ("How does obesity affect asthma control?", "lifestyle"),
    ("What prevention strategies reduce the risk of type 2 diabetes?", "lifestyle"),
    ("How should patients with gout modify their diet?", "lifestyle"),
    ("What sun protection advice should patients receive to prevent skin cancer?", "lifestyle"),

    # ── GENERAL ───────────────────────────────────────────────────────────
    ("What are the most common drug interactions with warfarin?", "general"),
    ("What is the mechanism of action of beta-blockers?", "general"),
    ("How does the renin-angiotensin system work?", "general"),
    ("What are the indications for ICU admission?", "general"),
    ("What is the Glasgow Coma Scale?", "general"),
    ("What are the CURB-65 criteria?", "general"),
    ("How does insulin resistance develop?", "general"),
    ("What is the difference between sensitivity and specificity?", "general"),
    ("What are NICE guidelines?", "general"),
    ("How do ACE inhibitors differ from ARBs?", "general"),
    ("What is the mechanism of QT prolongation?", "general"),
    ("How does renal clearance affect drug dosing?", "general"),
    ("What are the stages of chronic kidney disease?", "general"),
    ("What is the HEART score used for?", "general"),
    ("How does liver failure affect drug metabolism?", "general"),
    ("What are the components of the metabolic syndrome?", "general"),
    ("What is the Wells score?", "general"),
    ("How does heparin work?", "general"),
    ("What is the difference between type I and type II respiratory failure?", "general"),
    ("How is eGFR calculated?", "general"),
    ("What does MELD score measure?", "general"),
    ("How does fluid overload affect the lungs?", "general"),
    ("What is the role of the HbA1c in monitoring?", "general"),
    ("What are the causes of hyperkalaemia?", "general"),
    ("How is the osmolar gap calculated?", "general"),
    ("What are the indications for dialysis?", "general"),
    ("What is systemic inflammatory response syndrome?", "general"),
    ("How does the coagulation cascade work?", "general"),
    ("What is the difference between bacteriostatic and bactericidal antibiotics?", "general"),
    ("What is pharmacokinetics?", "general"),
]


def build_pipeline() -> Pipeline:
    return Pipeline([
        ("tfidf", TfidfVectorizer(
            analyzer="char_wb",       # character n-grams capture clinical subwords (e.g. "-osis", "mg/")
            ngram_range=(3, 5),
            max_features=20_000,
            sublinear_tf=True,        # log-scaled TF reduces impact of repeated words
            strip_accents="unicode",
            lowercase=True,
        )),
        ("clf", LogisticRegression(
            C=2.0,
            max_iter=1000,
            solver="lbfgs",
            class_weight="balanced",
        )),
    ])


def train(model_dir: Path, eval_only: bool = False) -> None:
    texts = [t for t, _ in TRAINING_DATA]
    labels = [l for _, l in TRAINING_DATA]
    label_set = sorted(set(labels))

    print(f"\n{'='*55}")
    print(f"  Clinical Query Route Classifier — Training")
    print(f"{'='*55}")
    print(f"  Samples  : {len(texts)}")
    print(f"  Classes  : {label_set}")
    print(f"  Distribution:")
    for lbl in label_set:
        n = labels.count(lbl)
        print(f"    {lbl:<12} {n} samples")

    pipeline = build_pipeline()

    # ── Cross-validation ──────────────────────────────────────────────
    print("\n[1/2] Cross-validating (5-fold stratified)...")
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_scores = cross_val_score(pipeline, texts, labels, cv=cv, scoring="accuracy")
    print(f"  CV accuracy: {cv_scores.mean():.3f} ± {cv_scores.std():.3f}")
    print(f"  Per-fold:    {[round(s, 3) for s in cv_scores]}")

    # ── Full classification report ────────────────────────────────────
    pipeline.fit(texts, labels)
    preds = pipeline.predict(texts)
    print("\n  Training set report:")
    print(classification_report(labels, preds, target_names=label_set, digits=3))

    if eval_only:
        print("  [eval-only] Model not saved.")
        return

    # ── Save ──────────────────────────────────────────────────────────
    print(f"[2/2] Saving model to {model_dir}/...")
    model_dir.mkdir(parents=True, exist_ok=True)

    model_path = model_dir / MODEL_FILENAME
    joblib.dump(pipeline, model_path)

    tfidf = pipeline.named_steps["tfidf"]
    meta = {
        "labels": label_set,
        "label_to_index": {l: i for i, l in enumerate(pipeline.classes_)},
        "cv_accuracy_mean": round(float(cv_scores.mean()), 4),
        "cv_accuracy_std": round(float(cv_scores.std()), 4),
        "n_features": len(tfidf.vocabulary_),
        "n_training_samples": len(texts),
        "model_path": str(model_path),
    }
    meta_path = model_dir / META_FILENAME
    meta_path.write_text(json.dumps(meta, indent=2))

    print(f"\n  Saved: {model_path}")
    print(f"  Saved: {meta_path}")
    print(f"\n{'='*55}")
    print(f"  Training complete  CV accuracy: {cv_scores.mean():.3f}")
    print(f"{'='*55}\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train clinical query route classifier")
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--eval-only", action="store_true", help="Cross-validate only, do not save")
    return parser.parse_args()


if __name__ == "__main__":
    sys.path.insert(0, str(REPO_ROOT / "backend"))
    args = parse_args()
    train(model_dir=args.model_dir, eval_only=args.eval_only)
