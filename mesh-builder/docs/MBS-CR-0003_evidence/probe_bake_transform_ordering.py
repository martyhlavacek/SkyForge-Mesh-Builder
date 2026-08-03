"""MBS-45 probe: does bake_static_mesh_transforms preserve the normalization?

Models Blender's parenting semantics (matrix_world = parent.matrix_world @
matrix_parent_inverse @ matrix_basis, and the matrix_world setter deriving basis
from the current parent matrix), then replays bake_static_mesh_transforms() with
the craft_root reset placed after the loop (v0.2.1) and before it (proposed).

Usage: python3 probe_bake_transform_ordering.py
"""
import numpy as np

np.set_printoptions(precision=4, suppress=True)


class Obj:
    def __init__(self, name, basis=None):
        self.name = name
        self.parent = None
        self.mpi = np.eye(4)
        self.basis = np.eye(4) if basis is None else basis
        self.verts = None

    @property
    def world(self):
        return (self.parent.world @ self.mpi @ self.basis) if self.parent else self.basis

    @world.setter
    def world(self, value):
        parent_matrix = (self.parent.world @ self.mpi) if self.parent else np.eye(4)
        self.basis = np.linalg.inv(parent_matrix) @ value

    def render(self):
        return (self.world @ np.vstack([self.verts.T, np.ones(len(self.verts))])).T[:, :3]


def scale_matrix(k):
    m = np.eye(4); m[:3, :3] *= k; return m


def translation_matrix(v):
    m = np.eye(4); m[:3, 3] = v; return m


NORMALIZATION = scale_matrix(1.506) @ translation_matrix([-0.1, -0.2, -0.14])
CHILD_LOCAL = translation_matrix([0.4, -0.3, 0.05])
VERTS = np.array([[1., 2., 0.3], [-1., -2., -0.3]])


def run(reset_root_first):
    root = Obj('craft_root', NORMALIZATION.copy())
    mesh = Obj('Hull'); mesh.parent = root; mesh.basis = CHILD_LOCAL.copy(); mesh.verts = VERTS.copy()
    target = mesh.render().copy()
    world_matrices = {mesh: mesh.world.copy()}          # captured before mutation
    if reset_root_first:
        root.world = np.eye(4)
    mesh.verts = (world_matrices[mesh] @ np.vstack([mesh.verts.T, np.ones(len(mesh.verts))])).T[:, :3]
    mesh.parent = root
    mesh.world = np.eye(4)
    if not reset_root_first:
        root.world = np.eye(4)                          # build_asset.py line 450
    return target, mesh.render(), root.world, mesh.world


target, _, _, _ = run(True)
print("Target normalized world position:", target[0], target[1], "\n")

for label, first in (('v0.2.1 (root reset AFTER the loop)', False),
                     ('proposed (root reset BEFORE the loop)', True)):
    target, actual, root_world, mesh_world = run(first)
    print(f"--- {label} ---")
    print("  craft_root identity      :", np.allclose(root_world, np.eye(4)))
    print("  mesh.matrix_world identity:", np.allclose(mesh_world, np.eye(4)))
    print("  mesh.matrix_world == N^-1 :", np.allclose(mesh_world, np.linalg.inv(NORMALIZATION)))
    print("  geometry lands at         :", actual[0], actual[1])
    print("  matches normalized pose   :", np.allclose(actual, target), "\n")
