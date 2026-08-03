"""MBS-26 probe: does profileScale survive to rendered pixels?

Reimplements build_asset.py's normalization + camera + fit math (lines 134-159,
278-311) in NumPy so it can run without Blender. Run: python3 probe_ortho_scale_cancellation.py
"""
import json, math, sys
import numpy as np

PROFILES = sys.argv[1] if len(sys.argv) > 1 else 'profiles/craft_profiles.json'

def cube(cx, cy, cz, sx, sy, sz):          # bpy cube primitive is 2x2x2 -> half-extent == scale
    return np.array([(cx+dx*sx, cy+dy*sy, cz+dz*sz)
                     for dx in (-1, 1) for dy in (-1, 1) for dz in (-1, 1)])

FIXTURE = np.vstack([cube(0, 0, 0, 1.25, 2.1, .35),      # fallback_ship() Hull
                     cube(-1.6, -.15, 0, .42, 1.25, .38),  # Engine_L
                     cube(1.6, -.15, 0, .42, 1.25, .38),   # Engine_R
                     cube(0, .65, .38, .65, .8, .28)])     # Cockpit

def normalize(pts, profile_scale, base=5.5):              # build_normalized_hierarchy
    lo, hi = pts.min(0), pts.max(0)
    span = max(hi[0]-lo[0], hi[1]-lo[1], 1e-5)            # X/Y only, per line 154
    return (pts - (lo+hi)/2) * ((base*profile_scale)/span)

def camera(pitch_deg, distance=14.0):                     # set_camera_pitch
    p = math.radians(pitch_deg)
    loc = np.array([0, -distance*math.sin(p), distance*math.cos(p)])
    fwd = -loc/np.linalg.norm(loc)
    right = np.cross(fwd, np.array([0., 1., 0.])); right /= np.linalg.norm(right)
    M = np.eye(4); M[:3, :3] = np.column_stack([right, np.cross(right, fwd), -fwd]); M[:3, 3] = loc
    return M

def bank_y(deg):
    a = math.radians(deg); c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])

def projected_fit_scale(pts, pitch, banks, margin=1.14):  # lines 292-311
    inv = np.linalg.inv(camera(pitch)); m = 0.1
    for b in banks:
        h = np.hstack([pts @ bank_y(b).T, np.ones((len(pts), 1))])
        cam = (inv @ h.T).T
        m = max(m, np.abs(cam[:, 0]).max(), np.abs(cam[:, 1]).max())
    return m * 2 * margin

def rendered_px(pts, pitch, ortho, res=96):
    inv = np.linalg.inv(camera(pitch))
    cam = (inv @ np.hstack([pts, np.ones((len(pts), 1))]).T).T
    return ((cam[:, 0].max()-cam[:, 0].min())/ortho*res,
            (cam[:, 1].max()-cam[:, 1].min())/ortho*res)

profiles = json.load(open(PROFILES))
canonical = projected_fit_scale(normalize(FIXTURE, max(p['scale'] for p in profiles)), 20.0, [-18, 0, 18])
print(f"{'profile':22s} {'scale':>6s} {'worldSpan':>10s} {'v0.2.0 px@96':>16s} {'pinned-ortho px@96':>20s}")
print('-'*80)
for p in profiles:
    n = normalize(FIXTURE, p['scale'])
    lo, hi = n.min(0), n.max(0)
    a = rendered_px(n, 20.0, projected_fit_scale(n, 20.0, [-18, 0, 18]))
    b = rendered_px(n, 20.0, canonical)
    print(f"{p['id']:22s} {p['scale']:6.2f} {max(hi[0]-lo[0], hi[1]-lo[1]):10.3f} "
          f"{a[0]:7.2f} x{a[1]:6.2f} {b[0]:11.2f} x{b[1]:6.2f}")
print(f"\nPinned ortho_scale (largest profile) = {canonical:.4f}")
print("MBS-26 confirmed if the v0.2.0 column is invariant across profiles.")
