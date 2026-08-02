"""MBS-47 probe: does the canonical orthographic frame survive the protocol's own runs?

Reimplements canonical_ortho_scale(), build_normalized_hierarchy(), create_thrusters(),
set_camera_pitch() and projected_required_scale() without Blender, then sweeps every
configuration EXPERIMENT_PROTOCOL.md mandates and reports the required margin.

Usage: python3 probe_canonical_frame_sweep.py [path/to/craft_profiles.json]
"""
import json, math, sys
import numpy as np

BASE_WORLD_SPAN = 5.5
CANONICAL_ORTHO_MARGIN = 1.23      # common/mesh_math.py
FIT_MARGIN = 1.14                  # projected_required_scale() default
PITCHES = (0.0, 20.0, 36.0)        # protocol-required camera pitch sweep
BANKS = (-18.0, 0.0, 18.0)


def box(cx, cy, cz, hx, hy, hz):
    return np.array([(cx + dx * hx, cy + dy * hy, cz + dz * hz)
                     for dx in (-1, 1) for dy in (-1, 1) for dz in (-1, 1)])


FIXTURE = [box(0, 0, 0, 1.25, 2.1, .35),        # fallback_ship() Hull
           box(-1.6, -.15, 0, .42, 1.25, .38),  # Engine_L
           box(1.6, -.15, 0, .42, 1.25, .38),   # Engine_R
           box(0, .65, .38, .65, .8, .28)]      # Cockpit


def normalize(objs, profile_scale):
    pts = np.vstack(objs)
    lo, hi = pts.min(0), pts.max(0)
    span = max(hi[0] - lo[0], hi[1] - lo[1], 1e-5)
    scale = (BASE_WORLD_SPAN * profile_scale) / span
    return [(o - (lo + hi) / 2) * scale for o in objs]


def thruster_boxes(objs):
    """create_thrusters(): cone rotated 90deg about X, so depth maps to the Y axis."""
    pts = np.vstack(objs)
    lo, hi = pts.min(0), pts.max(0)
    width, depth = hi[0] - lo[0], hi[1] - lo[1]
    center_z = (lo[2] + hi[2]) / 2
    length = max(0.45, depth * 0.16)
    radius = max(0.08, width * 0.035)
    anchor_y = lo[1] + depth * 0.08
    return [box(ax, anchor_y - length / 2, center_z, radius, length / 2, radius)
            for ax in (lo[0] + width * 0.30, hi[0] - width * 0.30)]


def camera(pitch_degrees, distance=14.0):
    pitch = math.radians(pitch_degrees)
    location = np.array([0, -distance * math.sin(pitch), distance * math.cos(pitch)])
    forward = -location / np.linalg.norm(location)
    right = np.cross(forward, np.array([0., 1., 0.])); right /= np.linalg.norm(right)
    matrix = np.eye(4)
    matrix[:3, :3] = np.column_stack([right, np.cross(right, forward), -forward])
    matrix[:3, 3] = location
    return matrix


def bank_y(degrees):
    a = math.radians(degrees); c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def projected_required_scale(objs, pitch, banks, margin=FIT_MARGIN):
    inverse = np.linalg.inv(camera(pitch))
    extent = 0.1
    for bank in banks:
        for obj in objs:
            homogeneous = np.hstack([obj @ bank_y(bank).T, np.ones((len(obj), 1))])
            camera_points = (inverse @ homogeneous.T).T
            extent = max(extent, np.abs(camera_points[:, 0]).max(), np.abs(camera_points[:, 1]).max())
    return extent * 2 * margin


profiles = json.load(open(sys.argv[1] if len(sys.argv) > 1 else 'craft_profiles.json'))
maximum_scale = max(p['scale'] for p in profiles)
canonical = round(BASE_WORLD_SPAN * maximum_scale * CANONICAL_ORTHO_MARGIN, 6)

print(f"canonicalOrthoScale = {BASE_WORLD_SPAN} x {maximum_scale} x {CANONICAL_ORTHO_MARGIN} = {canonical}\n")
print(f"{'profile':22s}{'pitch':>6s}{'thrusters':>11s}{'required':>10s}{'headroom':>10s}  verdict")
print('-' * 72)
worst = 0.0
for profile in sorted(profiles, key=lambda p: -p['scale']):
    normalized = normalize(FIXTURE, profile['scale'])
    for thrusters in (True, False):
        objs = normalized + (thruster_boxes(normalized) if thrusters else [])
        for pitch in PITCHES:
            required = projected_required_scale(objs, pitch, BANKS)
            worst = max(worst, required)
            headroom = canonical - required
            verdict = 'OK' if headroom >= -1e-6 else '*** JOB FAILS ***'
            print(f"{profile['id']:22s}{pitch:6.0f}{str(thrusters):>11s}"
                  f"{required:10.4f}{headroom:10.4f}  {verdict}")

needed = worst / (BASE_WORLD_SPAN * maximum_scale)
print(f"\nworst required scale across the mandated sweep : {worst:.4f}")
print(f"minimum viable CANONICAL_ORTHO_MARGIN          : {needed:.4f}")
print(f"currently configured                           : {CANONICAL_ORTHO_MARGIN}")
print("Set the margin from this sweep rather than from a single configuration.")
