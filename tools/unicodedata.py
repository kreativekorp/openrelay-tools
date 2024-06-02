#!/usr/bin/env python

from __future__ import print_function
from udparser import DataParser
import sys

if __name__ == '__main__':
	p = DataParser()
	p.parseArgs(sys.argv[1:])
	p.processFiles()
	p.printUnicodeData()
