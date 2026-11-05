#!/usr/bin/env python3
"""Render deployment and final displacement from standard SMP/MPP d3plot files.

Time and length values retain the deck's units. No part IDs, binary offsets,
time estimates, or model-specific camera bounds are assumed.
"""
import argparse
import json
from pathlib import Path
import sys

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection
from matplotlib.ticker import MaxNLocator
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from lasso.dyna import D3plot, ArrayType as A


def load_results(filename):
    # First read only times, then at most four coordinate states. This avoids
    # loading every stress/velocity array of a long run into memory.
    time_db = D3plot(str(filename), state_array_filter=[A.global_timesteps], buffered_reading=True)
    times = np.asarray(time_db.arrays.get(A.global_timesteps, []), dtype=float)
    if times.size < 2 or not np.all(np.isfinite(times)):
        raise ValueError('d3plot needs at least two finite time states for deployment rendering')
    selected = sorted(set(np.linspace(0, len(times) - 1, min(4, len(times)), dtype=int).tolist()))
    db = D3plot(str(filename), state_filter=set(selected),
                state_array_filter=[A.node_displacement, A.element_shell_is_alive], buffered_reading=True)
    arrays = db.arrays
    initial = np.asarray(arrays.get(A.node_coordinates, []))
    # Despite its name, lasso's node_displacement array contains current coordinates.
    current = np.asarray(arrays.get(A.node_displacement, []))
    shells = np.asarray(arrays.get(A.element_shell_node_indexes, []), dtype=int)
    parts = np.asarray(arrays.get(A.element_shell_part_indexes, []), dtype=int)
    if initial.ndim != 2 or initial.shape[1] != 3 or not len(initial):
        raise ValueError('d3plot has no valid node coordinates')
    if current.shape != (len(selected), len(initial), 3):
        raise ValueError('d3plot has no complete current-coordinate states; check DATABASE_EXTENT_BINARY')
    if not np.all(np.isfinite(initial)) or not np.all(np.isfinite(current)):
        raise ValueError('d3plot contains non-finite coordinates')
    if shells.ndim != 2 or shells.shape[1] != 4 or not len(shells):
        raise ValueError('d3plot has no curtain shell elements')
    if shells.min() < 0 or shells.max() >= len(initial):
        raise ValueError('d3plot shell connectivity is outside the node range')
    if parts.shape != (len(shells),):
        raise ValueError('d3plot shell part indexes are missing')
    alive = arrays.get(A.element_shell_is_alive)
    if alive is not None:
        alive = np.asarray(alive, dtype=bool)
        if alive.shape != (len(selected), len(shells)):
            raise ValueError('invalid d3plot shell deletion states')
    return dict(initial=initial, current=current, shells=shells, parts=parts,
                times=times[selected], state_indexes=selected, state_count=len(times), alive=alive)


def camera_bounds(points, axes):
    low = points[:, axes].min(axis=0)
    high = points[:, axes].max(axis=0)
    span = high - low
    pad = np.maximum(span * 0.06, max(float(span.max()), 1.0) * 0.025)
    return low - pad, high + pad


def panel(ax, coordinates, shells, parts, axes, bounds, title, values=None):
    vertices = coordinates[shells][:, :, axes]
    if values is None:
        palette = plt.get_cmap('tab20')
        colors = palette(parts % 20)
        collection = PolyCollection(vertices, facecolors=colors, edgecolors='#334155', linewidths=0.12)
    else:
        collection = PolyCollection(vertices, array=values, cmap='viridis',
                                    edgecolors='#334155', linewidths=0.08)
    ax.add_collection(collection)
    ax.set_xlim(bounds[0][0], bounds[1][0])
    ax.set_ylim(bounds[0][1], bounds[1][1])
    ax.set_aspect('equal', adjustable='box')
    ax.set_xlabel('XYZ'[axes[0]] + ' (deck length unit)')
    ax.set_ylabel('XYZ'[axes[1]] + ' (deck length unit)')
    ax.set_title(title, fontsize=10, loc='left')
    ax.grid(alpha=0.15)
    return collection


def deployment_panel(ax, coordinates, shells, parts, points, title):
    colors = plt.get_cmap('tab20')(parts % 20)
    collection = Poly3DCollection(coordinates[shells], facecolors=colors,
                                  edgecolors='#334155', linewidths=0.25)
    ax.add_collection3d(collection)
    low, high = points.min(axis=0), points.max(axis=0)
    span = high - low
    pad = np.maximum(span * 0.06, max(float(span.max()), 1.0) * 0.025)
    ax.set_xlim(low[0] - pad[0], high[0] + pad[0])
    ax.set_ylim(low[1] - pad[1], high[1] + pad[1])
    ax.set_zlim(low[2] - pad[2], high[2] + pad[2])
    ax.set_box_aspect(np.maximum(span, max(float(span.max()), 1.0) * 0.15))
    ax.set_proj_type('ortho')
    ax.view_init(elev=25, azim=-65)
    ax.set_xlabel('X')
    ax.set_ylabel('Y')
    ax.set_zlabel('Z')
    ax.tick_params(labelsize=7)
    ax.xaxis.set_major_locator(MaxNLocator(4))
    ax.yaxis.set_major_locator(MaxNLocator(2))
    ax.zaxis.set_major_locator(MaxNLocator(2))
    ax.set_title(title, fontsize=10, loc='left')


def render(data, output_dir, prefix):
    initial, current, shells, parts = (data[key] for key in ('initial', 'current', 'shells', 'parts'))
    used_nodes = np.unique(shells)
    points = np.concatenate([initial[used_nodes], current[:, used_nodes].reshape(-1, 3)])
    spans = np.ptp(points, axis=0)
    axes = tuple(sorted(np.argsort(spans)[-2:].tolist()))
    projection = ''.join('XYZ'[axis] for axis in axes)

    def visible(index):
        return data['alive'][index] if data['alive'] is not None else np.ones(len(shells), dtype=bool)

    fig, panels = plt.subplots(2, 2, figsize=(14, 9), facecolor='white', subplot_kw={'projection': '3d'})
    for index, ax in enumerate(panels.flat):
        if index >= len(current):
            ax.set_visible(False)
            continue
        keep = visible(index)
        if not np.any(keep):
            raise ValueError('no active shell elements at selected state %s' % data['state_indexes'][index])
        deployment_panel(ax, current[index], shells[keep], parts[keep], points,
                         'State %d | t = %.6g (deck time unit)' % (data['state_indexes'][index], data['times'][index]))
    fig.suptitle('Deployment process | 3D orthographic | colors identify parts | deck length units')
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    process_path = output_dir / (prefix + '_process.png')
    fig.savefig(process_path, dpi=120)
    plt.close(fig)

    last = current[-1]
    keep = visible(-1)
    active_shells, active_parts = shells[keep], parts[keep]
    displacement = np.linalg.norm(last - initial, axis=1)
    shell_displacement = displacement[active_shells].mean(axis=1)
    fig, panels = plt.subplots(2, 2, figsize=(14, 9), facecolor='white')
    for ax, view_axes in zip(list(panels.flat)[:3], [(0, 1), (0, 2), (1, 2)]):
        panel(ax, last, active_shells, active_parts, view_axes,
              camera_bounds(last[used_nodes], view_axes),
              'Final state | %s projection' % ''.join('XYZ'[axis] for axis in view_axes))
    contour = panel(panels[1, 1], last, active_shells, active_parts, axes,
                    camera_bounds(last[used_nodes], axes), 'Final displacement magnitude', shell_displacement)
    fig.colorbar(contour, ax=panels[1, 1], label='Shell mean |current - initial| (deck length unit)', shrink=0.8)
    fig.suptitle('Final state | t = %.6g (deck time unit)' % data['times'][-1])
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    detail_path = output_dir / (prefix + '_t20_detail.png')
    fig.savefig(detail_path, dpi=120)
    plt.close(fig)
    return dict(ok=True, reader='lasso-python', stateCount=data['state_count'],
                selectedStates=data['state_indexes'], times=data['times'].tolist(),
                shellCount=len(shells), nodeCount=len(initial), projection='3D orthographic', contourProjection=projection,
                contourQuantity='displacement_magnitude', maxDisplacement=float(displacement[used_nodes].max()),
                bounds=[points.min(axis=0).tolist(), points.max(axis=0).tolist()],
                processPng=str(process_path), detailPng=str(detail_path),
                units='length and time use the input deck units')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--d3dir', required=True)
    parser.add_argument('--d3plot', default='')
    parser.add_argument('--out', default='render')
    parser.add_argument('--output-dir', default='')
    # Retain the existing CLI surface; state times now come directly from d3plot.
    parser.add_argument('--deck', default='')
    parser.add_argument('--glstat', default='glstat')
    parser.add_argument('--mass', type=float, default=None)
    args = parser.parse_args()
    output_dir = Path(args.output_dir or args.d3dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = Path(args.d3plot) if args.d3plot else Path(args.d3dir) / 'd3plot'
    metadata = render(load_results(filename), output_dir, args.out)
    (output_dir / (args.out + '_metadata.json')).write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    print(json.dumps(metadata))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('d3plot rendering failed: %s' % error, file=sys.stderr)
        sys.exit(1)
