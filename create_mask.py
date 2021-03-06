#!/usr/bin/env python3
"""
Create a binary inclusive mask, including certain labels (brain areas), using a particular threshold (for the probabilistic atlas)

Usage
----
create_mask.py -i <probabilistic atlas image> -o <output mask image> -t <threshold> [label numbers]
create_mask.py -h

Authors
----
Wolfgang M. Pauli, Caltech Brain Imaging Center

Dates
----
2017-03-21 WMP From scratch

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

import sys
import argparse
import nibabel as nib
import numpy as np

def main():
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Create a binary inclusive mask')
    parser.add_argument('-i','--in_file', help="probabilistic atlas file")
    parser.add_argument('-o','--out_file', help="binary mask image")
    parser.add_argument('-t','--threshold', help="threshold to apply to probabilistic atlas", type=float)
    parser.add_argument('labels', metavar='N', type=int, nargs='+',
                        help='label numbers to smooth')

    args = parser.parse_args()

    in_file = args.in_file
    out_file = args.out_file
    threshold = args.threshold
    labels = args.labels

    # Load the source atlas image
    print('Opening %s' % in_file)
    in_nii = nib.load(in_file)

    # Load label image
    print('Loading labels')
    in_data = in_nii.get_data()
    
    mask_data = np.zeros((in_data.shape[0:3]))

    for label in labels:
        if label <= in_data.shape[3]:
            print("Pulling out label: %s" % label)
            label_image = in_data[:, :, :, label]
            mask_data[np.where(label_image > threshold)] = 1
            
    # Save smoothed labels image
    print('Saving mask to %s' % out_file)
    out_nii = nib.Nifti1Image(mask_data, in_nii.get_affine())
    out_nii.to_filename(out_file)
    
    print('Done')
    
    # Clean exit
    sys.exit(0)
            


# This is the standard boilerplate that calls the main() function.
if __name__ == '__main__':
    main()
