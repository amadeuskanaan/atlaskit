#!/usr/bin/python
"""
Create an ITK-SNAP label key from a subset of the Allen Brain Atlas human
ontology availble through the online API

Usage
----
allen2itksnap.py -k <ITK-SNAP label key file>
allen2itksnap.py -h

Example
----
>>> allen2itksnap.py -o Amy_BG_Labels.txt

Authors
----
Mike Tyszka, Caltech, Division of Humaninities and Social Sciences

Dates
----
2015-11-20 JMT From scratch

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
2015 California Institute of Technology.
"""

__version__ = '0.1.0'

import argparse
from urllib.request import urlopen
import xml.etree.cElementTree as ET

def main():
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Allen ontology to ITKSNAP labels')
    parser.add_argument('-o','--output', help="Output ITKSNAP label key file")
    
    # Parse command line arguments
    args = parser.parse_args()
    
    if args.output:
        itksnap_fname = args.output
    else:
        itksnap_fname = 'Allen_Labels.txt'
    
    # Allen Brain Institute human brain ontology via their online API
    allen_url = 'http://api.brain-map.org/api/v2/structure_graph_download/10.xml'
    
    # Download XML for Allen human brain ontology
    print('Downloading ontology from %s' % allen_url)
    xml_remote = urlopen(allen_url)

    # Parse XML as a Document Object Model (DOM) 
    print('Parsing XML tree')
    tree = ET.parse(xml_remote)
    
    print('Finding tree root')
    root = tree.getroot()
    
    # Find basal nuclei root element
    structure = 'BN'
    
    for structure in strucutres
    
    # Iterate over ontology printing structure names
    print('Iterating over tree')
    for elem in root.iter():
        if elem.tag == 'structure':
            name = elem.findtext('name')
            acronym = elem.findtext('acronym')
            ID = elem.findtext('id')
            rgb = elem.findtext('color-hex-triplet')
            print('%s %s %s %s' % (name, acronym, ID, rgb))

    # Done
    print('Done')

def SaveKey(key_fname, ontology):
    '''
    Save an ontology as an ITK-SNAP label key file
    '''
    
    print('Saving ontology in %s' % key_fname)



# This is the standard boilerplate that calls the main() function.
if __name__ == '__main__':
    main()
