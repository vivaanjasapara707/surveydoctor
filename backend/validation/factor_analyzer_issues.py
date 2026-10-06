"""Evidence for the two factor_analyzer 0.5.1 issues corrected in surveydoctor.structure.

Fits the 5-factor bfi EFA with factor_analyzer directly and prints, next to psych::fa's
values (from tests/fixtures/reference_structure.json) and SurveyDoctor's corrected values:

1. the factor correlation matrix: factor_analyzer's ``phi_`` vs psych's Phi vs ours;
2. communalities: factor_analyzer's ``get_communalities()`` vs psych vs ours.

Factors are matched to psych's by loadings (structure.factor_matching), and the same
matching is applied to the library's ``phi_`` and to ours. Run from backend/, after
Rscript validation/reference_structure.R:

    python validation/factor_analyzer_issues.py
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from factor_analyzer import FactorAnalyzer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from surveydoctor.io import load_csv, prepare_data  # noqa: E402
from surveydoctor.reliability import complete_cases  # noqa: E402
from surveydoctor.schema import SurveySchema  # noqa: E402
from surveydoctor.structure import (  # noqa: E402
    efa,
    factor_matching,
    match_factor_correlations,
)

FIXTURE = Path("tests/fixtures/reference_structure.json")


def main() -> None:
    """Print the comparison tables."""
    ref = json.loads(FIXTURE.read_text(encoding="utf-8"))
    schema = SurveySchema.load("data/sample/bfi_schema.json")
    prepared = prepare_data(load_csv("data/sample/bfi.csv"), schema)
    data = complete_cases(prepared.scored_items, schema.items)
    items, factors = ref["items"], ref["efa"]["factors"]
    n_factors = ref["efa"]["n_factors"]

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = FactorAnalyzer(n_factors=n_factors, rotation="oblimin", method="minres")
        model.fit(data.to_numpy(dtype=float))
    ours = efa(data, n_factors)

    psych_loadings = pd.DataFrame(
        {f: [ref["efa"]["loadings"][f][i] for i in items] for f in factors}, index=items
    )
    psych_phi = pd.DataFrame(
        {f: [ref["efa"]["phi"][f][g] for g in factors] for f in factors}, index=factors
    )
    # The library's loadings_ are identical to ours, so one matching serves both.
    library_loadings = pd.DataFrame(model.loadings_, index=items, columns=ours.loadings.columns)
    assert np.allclose(library_loadings.to_numpy(), ours.loadings.to_numpy())
    matching = factor_matching(ours.loadings, psych_loadings)
    names = list(ours.loadings.columns)
    library_phi = match_factor_correlations(
        pd.DataFrame(model.phi_, index=names, columns=names), matching
    )
    our_phi = match_factor_correlations(ours.factor_correlations, matching)

    print(f"n = {len(data)}, {n_factors} factors, minres + oblimin")
    print(f"Factor matching (psych -> ours, sign): {matching}")
    library_gap = np.abs(model.loadings_ @ model.phi_ - model.structure_).max()
    our_gap = np.abs(
        ours.loadings.to_numpy() @ ours.factor_correlations.to_numpy() - model.structure_
    ).max()
    print(
        "Consistency check, max |loadings_ @ phi_ - structure_| (0 if phi_ is in the same "
        f"order as the loadings): {library_gap:.4f}"
    )
    print(f"Same check with our Phi: {our_gap:.2e}")

    print("\n1. Factor correlations (upper triangle, psych's factor order)")
    rows = []
    for a in range(len(factors)):
        for b in range(a + 1, len(factors)):
            fa_, fb = factors[a], factors[b]
            rows.append(
                {
                    "pair": f"{fa_}-{fb}",
                    "factor_analyzer phi_": library_phi.loc[fa_, fb],
                    "psych Phi": psych_phi.loc[fa_, fb],
                    "SurveyDoctor": our_phi.loc[fa_, fb],
                }
            )
    table = pd.DataFrame(rows).set_index("pair")
    table["|library - psych|"] = (table["factor_analyzer phi_"] - table["psych Phi"]).abs()
    table["|ours - psych|"] = (table["SurveyDoctor"] - table["psych Phi"]).abs()
    print(table.round(4).to_string())
    print(
        f"Max |library - psych| = {table['|library - psych|'].max():.4f}; "
        f"max |ours - psych| = {table['|ours - psych|'].max():.2e}"
    )

    print("\n2. Communalities")
    comm = pd.DataFrame(
        {
            "factor_analyzer get_communalities()": model.get_communalities(),
            "psych communality": [ref["efa"]["communality"][i] for i in items],
            "SurveyDoctor diag(L Phi L')": ours.communalities.to_numpy(),
        },
        index=items,
    )
    comm["|library - psych|"] = (comm.iloc[:, 0] - comm.iloc[:, 1]).abs()
    comm["|ours - psych|"] = (comm.iloc[:, 2] - comm.iloc[:, 1]).abs()
    print(comm.round(4).to_string())
    print(
        f"Max |library - psych| = {comm['|library - psych|'].max():.4f} "
        f"(item {comm['|library - psych|'].idxmax()}); "
        f"max |ours - psych| = {comm['|ours - psych|'].max():.2e}"
    )


if __name__ == "__main__":
    main()
