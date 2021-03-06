#!/usr/bin/env python3
"""
Create a report of intra and inter-observer atlas label statistics

Expects a label directory organized as follows:
<label_dir>/
  <observer A>/
    <template 1>
  <observer B>/


Usage
----
atlas.py -d <observer labels directory>
atlas.py -h

Authors
----
Mike Tyszka, Caltech Brain Imaging Center

Dates
----
2017-02-14 JMT From scratch

License
----
This file is part of atlaskit.

    atlaskit is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    atlaskit is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with atlaskit.  If not, see <http://www.gnu.org/licenses/>.

Copyright
----
2017 California Institute of Technology.
"""

__version__ = '0.2.0'

import os
import sys
import csv
import argparse
from six import BytesIO
import nibabel as nib
import numpy as np
import pandas as pd
import multiprocessing as mp
import shutil
from glob import glob
from scipy.ndimage.morphology import binary_erosion


def main():

    print()
    print('-------------------------------------------------------')
    print('Probablistic Atlas Construction with Similarity Metrics')
    print('-------------------------------------------------------')

    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Calculate label similarity metrics for multiple observers')
    parser.add_argument('-d','--labeldir', help='Directory containing observer label subdirectories ["."]')
    parser.add_argument('-a','--atlasdir', help='Output atlas directory ["<labeldir>/atlas"]')
    parser.add_argument('-k','--key', help='ITK-SNAP label key text file ["<labeldir>/labels.txt"]')
    parser.add_argument('-l','--labels', required=False, type=parse_range, help='List of label indices to process (eg 1-5, 7-9, 12)')

    # Parse command line arguments
    args = parser.parse_args()

    if args.labeldir:
        label_dir = args.labeldir
        if not os.path.isdir(label_dir):
            print('Label directory does not exist (%s) - exiting' % label_dir)
            sys.exit(1)
    else:
        label_dir = os.path.realpath(os.getcwd())

    print('Label directory  : %s' % label_dir)

    if args.atlasdir:
        atlas_dir = args.atlasdir
    else:
        atlas_dir = os.path.join(label_dir, 'atlas')

    print('Atlas directory  : %s' % atlas_dir)

    # Handle label key file
    if args.key:
        label_keyfile = args.key
    else:
        label_keyfile = os.path.join(label_dir, 'labels.txt')

    print('Label key file   : %s' % label_keyfile)

    if not os.path.isfile(label_keyfile):
        print('* ITK-SNAP label key is missing (%s) - exiting' % label_keyfile)
        sys.exit(1)

    # Safely create atlas directory
    if not os.path.isdir(atlas_dir):
        os.mkdir(atlas_dir)

    # Save a copy of label key file in the atlas directory
    label_keyfile_save = os.path.join(atlas_dir, 'labels.txt')
    shutil.copyfile(label_keyfile, label_keyfile_save)

    # Load the label key as a data frame
    label_key = load_key(label_keyfile_save)

    # Init grand lists
    labels = []
    vox_mm = []  # Voxel dimensions in mm
    vox_ul = []  # Voxel volume in mm^3 (microliters)
    affine_tx = []  # Nifti affine transform
    obs_names = []  # Observer names/initials

    # Similarity metrics output files
    inter_metrics_csv = os.path.join(atlas_dir, 'inter_observer_metrics.csv')
    intra_metrics_csv = os.path.join(atlas_dir, 'intra_observer_metrics.csv')

    # Loop over observer directories ("obs-*")
    # Load labeled images and collect into a nested list
    # (template within observer)

    for obs_dir in sorted(glob(os.path.join(label_dir, "obs-*"))):

        if os.path.isdir(obs_dir):

            obs_names.append(os.path.basename(obs_dir))

            print('Loading label images from %s' % obs_dir)

            # Init template label list for this observer
            obs_labels = []

            # Loop over all template label images
            for im in sorted(glob(os.path.join(obs_dir, '*.nii.gz'))):

                # Load label image and add to list
                this_nii = nib.load(im)
                obs_labels.append(this_nii.get_data())

                # Save voxel dimensions, volume
                d = np.array(this_nii.header.get_zooms())
                vox_mm.append(d)
                vox_ul.append(d.prod())
                affine_tx.append(this_nii.get_affine())

            # Add observer labels to grand list
            if len(obs_labels) > 0:
                print("  Loaded %d label images" % len(obs_labels))
                labels.append(obs_labels)
            else:
                print("* No label images detected - skipping")

    # Voxel dimensions and volumes
    vox_mm, vox_ul = np.array(vox_mm), np.array(vox_ul)

    if not vox_mm.any():
        print("* No label images detected in %s - exiting" % label_dir)
        sys.exit(1)

    # Check for any variation in dimensions across templates and observers
    if any(np.nonzero(np.std(vox_mm, axis=1))):
        print('* Not all images have the same voxel dimensions - exiting')
        sys.exit(1)
    else:
        # Use dimensions from first image
        vox_mm = vox_mm[0]
        vox_ul = vox_ul[0]

    # Convert nested list to 5D numpy array
    # -> labels[observer][template][x][y][z]
    print('Preparing labels')
    labels = np.array(labels)

    # Limited list of labels to process
    if args.labels:
        label_nos = args.labels
    else:
        label_nos = np.int32(np.unique(labels))
        label_nos = np.delete(label_nos, np.where(label_nos == 0))  # Remove background label

    # Remove labels not present in key
    label_unknown = []
    for ll, label_no in enumerate(label_nos):
        if get_label_name(label_no, label_key) == 'Unknown':
            print('* Label %d unknown - removing from list' % label_no)
            label_unknown.append(ll)
    label_nos = np.delete(label_nos, label_unknown)

    # Report remaining labels
    print('  Analyzing %d unique labels (excluding background)' % len(label_nos))

    # Construct and output label mean and variance maps
    label_stats_maps(atlas_dir, labels, label_nos, affine_tx[0], obs_names)

    # Similarity metrics between and within observers
    print('')
    print('Computing similarity metrics between and within observers')

    intra_metrics_all = []
    inter_metrics_all = []

    # Loop over each unique label value
    for label_no in label_nos:

        print('Analyzing label index %d' % label_no)

        # Current label mask
        label_mask = (labels == label_no)

        # Intra-observer metrics
        intra_metrics_all.append(intra_observer_metrics(label_mask, vox_mm))

        # Inter-observer metrics
        inter_metrics_all.append(inter_observer_metrics(label_mask, vox_mm))

    # Write metrics to report directory as CSV
    save_intra_metrics(intra_metrics_csv, intra_metrics_all, label_nos, label_key)
    save_inter_metrics(inter_metrics_csv, inter_metrics_all, label_nos, label_key)

    # Clean exit
    sys.exit(0)


def label_stats_maps(atlas_dir, labels, label_nos, affine_tx, obs_names):
    """
    Construct label mean and variance maps and write to atlas directory

    Parameters
    ----------
    atlas_dir: string
        Output atlas directory path
    labels: 5D numpy array of integers
        Integer label volumes for all labels and observers [obs][tmp][x][y][z]
    label_nos: list
        List of label numbers present in labels
    affine_tx: numpy matrix
        Affine transform matrix between voxel and real space
    obs_names: list of strings
        Observer names/initials

    Returns
    -------

    """

    print('Constructing probablistic atlas for each observer')

    # Get dimensions of label data
    n_obs, n_tmp, nx, ny, nz = labels.shape

    # Number of unique labels
    n = len(label_nos)

    # Init the label means and variances over all templates
    label_means = np.zeros([nx, ny, nz, n, n_obs])
    label_vars = np.zeros([nx, ny, nz, n, n_obs])

    # Create independent prob atlases for each observer
    for oc, obs_name in enumerate(obs_names):

        print('  Observer %02d (%s)' % (oc, obs_name))

        # Extract labels for current observer
        labels_obs = labels[oc,:,:,:,:]

        # Loop over each unique label value
        for lc, label_no in enumerate(label_nos):

            print('    Adding label %d' % label_no)

            # Label mask for all templates
            mask = labels_obs == label_no

            # Label mean and variance over all templates
            label_means[:, :, :, lc, oc] = np.mean(mask, axis=0)
            label_vars[:, :, :, lc, oc] = np.var(mask, axis=0)

        # Save observer label mean to atlas dir
        print('    Saving observer label mean')
        obs_mean_fname = os.path.join(atlas_dir, 'obs-{0:02d}_label_mean.nii.gz'.format(oc))
        obs_mean_nii = nib.Nifti1Image(label_means[:,:,:,:,oc], affine_tx)
        obs_mean_nii.to_filename(obs_mean_fname)

        # Save observer label variance to atlas dir
        print('    Saving observer label variance')
        obs_var_fname = os.path.join(atlas_dir, 'obs-{0:02d}_label_var.nii.gz'.format(oc))
        obs_var_nii = nib.Nifti1Image(label_vars[:,:,:,:,oc], affine_tx)
        obs_var_nii.to_filename(obs_var_fname)

    # Label means over all observers (aka probabilistic atlas)
    print('Computing global label means (probabilistic atlas)')
    p = np.mean(label_means, axis=4)
    prob_atlas_fname = os.path.join(atlas_dir, 'prob_atlas.nii.gz')
    prob_nii = nib.Nifti1Image(p, affine_tx)
    prob_nii.to_filename(prob_atlas_fname)


def intra_observer_metrics(label_mask, vox_mm):
    """
    Calculate within-observer Dice, Hausdorff and related metrics

    Parameters
    ----------
    label_mask: 5D numpy boolean array [observer][template][x][y][z]
    vox_mm: voxel dimensions in mm

    Returns
    -------
    intra_metrics: nobs x ntmp x ntmp nested list
    """

    # Dimensions
    nobs, ntmp, nx, ny, nz = label_mask.shape

    # Init grand intra-observer metrics list
    intra_metrics = []

    print('  Calculating intra-observer similarity metrics :', end='')

    for obs in range(0,nobs):

        print(' %d' % obs, end='')

        # Results list for current observer
        obs_res = []

        for ta in range(0, ntmp):

            mask_a = label_mask[obs, ta, :, :, :]
            data_list = []

            for tb in range(0, ntmp):

                mask_b = label_mask[obs,tb,:,:,:]
                data_list.append((mask_a, mask_b, vox_mm))

            # Run similarity metric function in parallel on template A data list
            with mp.Pool(mp.cpu_count()-2) as pool:
                res = pool.starmap(similarity, data_list)

            # Add to current observer results
            obs_res.append(res)

        # Add observer results to grand list
        intra_metrics.append(obs_res)

    print()

    return intra_metrics


def inter_observer_metrics(label_mask, vox_mm):
    """
     Calculate between-observer Dice, Hausdorff and related metrics

     Parameters
     ----------
     label_mask: 5D numpy boolean array [observer][template][x][y][z]
     vox_mm: voxel dimensions in mm

     Returns
     -------
     inter_metrics: ntmp x nobs x nobs nested list
     """

    # Dimensions
    nobs, ntmp, nx, ny, nz = label_mask.shape

    # Init grand inter-observer metrics list
    inter_metrics = []

    print('  Calculating inter-observer similarity metrics :', end='')

    for tmp in range(0, ntmp):

        print(' %d' % tmp, end='')

        # Results list for this template
        tmp_res = []

        for obs_a in range(0, nobs):

            mask_a = label_mask[obs_a, tmp, :, :, :]

            data_list = []

            for obs_b in range(0, nobs):

                mask_b = label_mask[obs_b, tmp, :, :, :]

                data_list.append((mask_a, mask_b, vox_mm))

            # Run similarity metric function in parallel on data list
            with mp.Pool(mp.cpu_count()-2) as pool:
                res = pool.starmap(similarity, data_list)

            # Add to current template results
            tmp_res.append(res)

        # Add template results to grand list
        inter_metrics.append(tmp_res)

    print()

    return inter_metrics


def save_intra_metrics(fname, intra_metrics, label_nos, label_key):
    """

    Parameters
    ----------
    fname: CSV filename
    intra_metrics: nobs x ntmp x ntmp nested list
    label_nos:
    label_key:

    Returns
    -------

    """

    print('Saving intra-observer metrics to %s' % fname)

    # Preferred method for safe opening CSV file in Python 3
    with open(fname, "w", newline='') as f:

        writer = csv.writer(f)

        # Column headers
        writer.writerow(('labelName','labelNo','observer','tmpA','tmpB','dice','hausdorff','nA','nB'))

        for idx, m_idx in enumerate(intra_metrics):
            label_no = label_nos[idx]
            label_name = get_label_name(label_no, label_key)
            for obs, m_obs in enumerate(m_idx):
                for tA, m_ta in enumerate(m_obs):
                    for tB, m_tb in enumerate(m_ta):
                        writer.writerow((label_name, label_no, obs, tA, tB) + m_tb)


def save_inter_metrics(fname, inter_metrics, label_nos, label_key):
    """

    Parameters
    ----------
    fname: CSV filename
    inter_metrics: ntmp x nobs x nobs nested list
    label_nos:
    label_key:

    Returns
    -------

    """

    print('Saving inter-observer metrics to %s' % fname)

    with open(fname, "w", newline='') as f:

        writer = csv.writer(f)

        # Column headers
        writer.writerow(('labelName','labelNo','template','obsA','obsB','dice','hausdorff','nA','nB'))

        for idx, m_idx in enumerate(inter_metrics):
            label_no = label_nos[idx]
            label_name = get_label_name(label_no, label_key)
            for tmp, m_tmp in enumerate(m_idx):
                for obsA, m_oa in enumerate(m_tmp):
                    for obsB, m_ob in enumerate(m_oa):
                        writer.writerow((label_name, label_no, tmp, obsA, obsB) + m_ob)


def similarity(mask_a, mask_b, vox_mm):
    """

    Parameters
    ----------
    mask_a: 3D logical array
    mask_b: 3D logical array
    vox_mm: tuple of voxel dimensions in mm

    Returns
    -------
    dice, haus: similarity metrics
    na, nb: number of voxels in each mask
    """

    # Count voxels in each mask
    na, nb = np.sum(mask_a), np.sum(mask_b)

    # Only calculate stats if labels present in A or B
    if na > 0 or nb > 0:

        # Find intersection and union of A and B masks
        a_and_b = np.logical_and(mask_a, mask_b)
        a_or_b = np.logical_or(mask_a, mask_b)

        # Count voxels in intersection and union
        n_a_and_b, n_a_or_b = np.sum(a_and_b), np.sum(a_or_b)

        # Similarity metrics
        dice = 2.0 * n_a_and_b / float(na + nb)
        haus = hausdorff_distance(mask_a, mask_b, vox_mm)
    else:
        dice, haus = np.nan, np.nan

    return dice, haus, na, nb


def hausdorff_distance(A, B, vox_mm):
    """
    Calculate the Hausdorff distance in mm between two binary masks in 3D

    Parameters
    ----------
    A : 3D numpy logical array
        Binary mask A
    B : 3D numpy logical array
        Binary mask B
    vox_mm : numpy float array
        voxel dimensions in mm

    Returns
    -------
    H : float
        hausdorff_distance distance between labels
    """

    # Only need to calculate distances for surface voxels in each mask
    sA = surface_voxels(A)
    sB = surface_voxels(B)

    # Create lists of all True points in both surface masks
    xA, yA, zA = np.nonzero(sA)
    xB, yB, zB = np.nonzero(sB)

    # Count elements in each point set
    nA = xA.size
    nB = xB.size

    if nA > 0 and nB > 0:

        # Init min dr to -1 for all points in A
        min_dr = -1.0 * np.ones([nA])

        for ac in range(0,nA):

            dx = (xA[ac] - xB[:]) * vox_mm[0]
            dy = (yA[ac] - yB[:]) * vox_mm[1]
            dz = (zA[ac] - zB[:]) * vox_mm[2]
            min_dr[ac] = np.min(np.sqrt(dx**2 + dy**2 + dz**2))

        # Find maximum over A of the minimum distances A to B
        H = np.max(min_dr)

    else:

        H = np.nan

    return H


def surface_voxels(x):
    """
    Isolate surface voxel in a boolean mask using single voxel erosion

    Parameters
    ----------
    x: 3D numpy boolean array

    Returns
    -------

    """

    # Erode by one voxel
    x_eroded = binary_erosion(x, structure=np.ones([3,3,3]), iterations=1)

    # Return logical XOR of mask and eroded mask = surface voxels
    return np.logical_xor(x, x_eroded)


def bounding_box(x):

    # Projections onto x, y and z axes
    px = np.any(x, axis=(1, 2))
    py = np.any(x, axis=(0, 2))
    pz = np.any(x, axis=(0, 1))

    px_min, px_max = np.where(px)[0][[0, -1]]
    py_min, py_max = np.where(py)[0][[0, -1]]
    pz_min, pz_max = np.where(pz)[0][[0, -1]]

    return px_min, px_max, py_min, py_max, pz_min, pz_max


def extract_box(x, bb):

    return x[bb[0]:bb[1],bb[2]:bb[3],bb[4]:bb[5]]


def get_template_ids(label_dir, obs):

    obs_dir = os.path.join(label_dir, obs)

    if os.path.isdir(obs_dir):

        ims = sorted(glob(os.path_join(obs_dir, '*.nii.gz')))

        print(ims)


def parse_range(astr):
    '''
    Parse compound list of integers and integer ranges

    Parameters
    ----------
    astr

    Returns
    -------

    '''
    result = set()
    for part in astr.split(','):
        x = part.split('-')
        result.update(range(int(x[0]), int(x[-1]) + 1))

    return sorted(result)


def load_key(key_fname):
    """
    Parse an ITK-SNAP label key file

    Parameters
    ----------
    key_fname: ITK-SNAP label key filename

    Returns
    -------
    key: Data table containing ITK-SNAP style label key
    """

    # Import key as a data table
    # Note the partially undocumented delim_whitespace flag
    key = pd.read_table(key_fname,
                         comment='#',
                         header=None,
                         names=['Index','R','G','B','A','Vis','Mesh','Name'],
                         delim_whitespace=True)

    return key


def get_label_name(label_idx, label_key):

    label_name = 'Unknown'

    for i, idx in enumerate(label_key.Index):
        if label_idx == idx:
            label_name = label_key.Name[i]

    return label_name


# This is the standard boilerplate that calls the main() function.
if __name__ == '__main__':
    main()
