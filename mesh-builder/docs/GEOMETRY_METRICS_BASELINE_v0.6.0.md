# Geometry Metrics Baseline — v0.6.0 CR-0011 Remediation

All values below were generated locally without network access. Claude must reproduce them independently.

| Metric | Approved gunship | Field gunship | Interceptor | Gate |
|---|---:|---:|---:|---:|
| Triangles | 83,180 | 108,412 | 88,176 | <= 180,000 |
| Components | 1 | 1 | 1 | <= 1 |
| Euler number | 2 | 2 | 2 | — |
| Genus | 0 | 0 | 0 | <= 0 |
| Flat-belly fraction | 0.017814 | 0.028625 | 0.029802 | <= 0.06 |
| Vertical-wall fraction | 0.007195 | 0.007093 | 0.008191 | <= 0.045 |
| Combined artifact fraction | 0.025009 | 0.035717 | 0.037994 | <= 0.10 |
| Tip/root thickness ratio | 0.207438 | 0.157915 | 0.192907 | <= 0.40 |
| Lower-field relative residual | 0.230694 | 0.234321 | 0.247570 | >= 0.10 |
| Top silhouette IoU | 0.982218 | 0.981267 | 0.978496 | >= 0.94 |
| Emulated Blender-import IoU | 0.981433 | 0.981429 | 0.978337 | >= 0.94 |

## Gate derivation

The artifact thresholds are deliberately much tighter than the first v0.6.0 candidate while retaining measured margin:

- flat belly 0.06: approximately 2× the measured maximum;
- vertical wall 0.045: approximately 5.5× the measured maximum;
- combined artifact 0.10: approximately 2.6× the measured maximum;
- height/planform 0.28: approximately 1.65× the measured maximum;
- tip/root 0.40: approximately 1.9× the measured maximum.

These gates still reject the v0.5.3 field baseline at 0.323049 / 0.313233 / 0.636282.
