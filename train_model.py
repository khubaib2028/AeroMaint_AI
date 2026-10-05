from pathlib import Path
import random
import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

BASE_DIR = Path(__file__).resolve().parent
MODEL_DIR = BASE_DIR / "models"
MODEL_DIR.mkdir(exist_ok=True)
MODEL_PATH = MODEL_DIR / "failure_model.joblib"

random.seed(42)
np.random.seed(42)

X = []
y = []

# Synthetic training data for SIH prototype/demo.
# Features:
# engine_temperature, vibration, oil_pressure,
# flight_hours, component_age, previous_failures, maintenance_count
for _ in range(8000):
    temp = random.uniform(60, 110)
    vibration = random.uniform(0.10, 1.30)
    pressure = random.uniform(25, 60)
    hours = random.uniform(100, 5000)
    age = random.uniform(1, 100)
    failures = random.randint(0, 5)
    maintenance = random.randint(0, 15)

    risk_signal = (
        max(0, temp - 82) * 0.065
        + max(0, vibration - 0.60) * 0.90
        + max(0, 38 - pressure) * 0.045
        + max(0, hours - 3000) / 9000
        + max(0, age - 65) / 120
        + failures * 0.075
        - maintenance * 0.012
    )

    probability = min(0.98, max(0.02, 0.05 + risk_signal))
    failure = 1 if random.random() < probability else 0

    X.append([temp, vibration, pressure, hours, age, failures, maintenance])
    y.append(failure)

X = np.array(X)
y = np.array(y)

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.20, random_state=42, stratify=y
)

model = RandomForestClassifier(
    n_estimators=250,
    max_depth=10,
    random_state=42,
    class_weight="balanced"
)

model.fit(X_train, y_train)

predictions = model.predict(X_test)
accuracy = accuracy_score(y_test, predictions)

joblib.dump(model, MODEL_PATH)

print(f"Model saved: {MODEL_PATH}")
print(f"Validation accuracy: {accuracy:.2%}")
