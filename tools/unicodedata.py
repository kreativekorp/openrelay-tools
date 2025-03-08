#!/usr/bin/env python

from __future__ import print_function
from udparser import DataParser
import sys

def main(args):
	p = DataParser()
	p.parseArgs(args)
	p.processFiles()
	if p.actions:
		p.processActions()
	else:
		p.printUnicodeData()

if __name__ == '__main__':
	main(sys.argv[1:])
