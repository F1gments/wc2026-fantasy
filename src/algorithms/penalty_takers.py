"""
Penalty taker registry.

Penalty takers earn an extra +2 pts per penalty won (on top of the goal bonus).
Over a tournament they also take all their team's penalties → higher goal probability.

Bonus applied in scoring.py:
  - +0.25 goals/game added to expected goals rate (one pen attempt ~every 4 games)
  - The +2 "winning a penalty" pts added per expected pen won

Sources: Transfermarkt penalty stats, known international takers.
"""

# { normalised_name: confidence }
# confidence 1.0 = designated first-choice taker, 0.7 = likely taker
PENALTY_TAKERS: dict[str, float] = {
    # Confirmed first-choice international takers
    "harry kane":           1.0,
    "kylian mbappe":        1.0,
    "lionel messi":         1.0,
    "cristiano ronaldo":    1.0,
    "bruno fernandes":      1.0,
    "lamine yamal":         0.7,  # emerging taker for Spain
    "vinicius junior":      0.8,
    "neymar":               1.0,
    "erling haaland":       1.0,
    "romelu lukaku":        1.0,
    "ivan toney":           0.9,
    "ciro immobile":        1.0,
    "robert lewandowski":   1.0,
    "memphis depay":        1.0,
    "richarlison":          0.7,
    "gabriel jesus":        0.7,
    "bukayo saka":          0.8,
    "marcus rashford":      0.7,
    "raheem sterling":      0.7,
    "pedri":                0.7,
    "dani olmo":            0.7,
    "fabian ruiz":          0.7,
    "alvaro morata":        0.8,
    "florian wirtz":        0.7,
    "leroy sane":           0.7,
    "thomas muller":        0.8,
    "serge gnabry":         0.7,
    "achraf hakimi":        0.9,
    "hakim ziyech":         0.9,
    "sadio mane":           0.9,
    "karim benzema":        1.0,
    "ousmane dembele":      0.7,
    "olivier giroud":       0.8,
    "darwin nunez":         0.8,
    "luis suarez":          0.9,
    "edinson cavani":       0.9,
    "hirving lozano":       0.7,
    "raul jimenez":         0.9,
    "javier hernandez":     0.8,
    "heung min son":        0.9,
    "mehdi taremi":         0.9,
    "gabriel martinelli":   0.7,
    "rodrygo":              0.8,
    "gabriel magalhaes":    0.5,
    "trent alexander arnold": 0.7,
    "michael olise":        0.6,
}


def get_pen_bonus(norm_name: str) -> float:
    """
    Return the penalty confidence score for a normalised player name.
    0.0 if not a known penalty taker.
    """
    return PENALTY_TAKERS.get(norm_name, 0.0)
