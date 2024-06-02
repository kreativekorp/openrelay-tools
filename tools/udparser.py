#!/usr/bin/env python

from __future__ import print_function
from bitset import BitSet
import os
import re
import sys

class DataParser:
	def __init__(self):
		self.files = []
		self.flags = []
		self.superstring = ''
		self.matchedFiles = []
		self.blockBits = BitSet()
		self.charBits = BitSet()
		self.blockLines = []
		self.charLines = []

	def parseArgs(self, args):
		for arg in args:
			if '/' in arg or '.' in arg:
				self.files.append(arg)
			elif '-' in arg:
				self.flags.append(arg)
			else:
				self.superstring += arg

	def processFile(self, file, matches):
		fileFlags = []
		fileSubstrings = []
		with open(file, 'r') as lines:
			inBlocks = False
			inChars = False
			for line in lines:
				line = line.strip()
				if line[0] == '@':
					fields = re.split(r'\s+', line)
					if fields[0] == '@flag':
						fileFlags.append(fields[1])
						if fields[1] in self.flags:
							matches = True
					if fields[0] == '@substring':
						fileSubstrings.append(fields[1])
						if fields[1] in self.superstring:
							matches = True
					if fields[0] == '@file':
						inBlocks = (fields[1] == 'Blocks.txt')
						inChars = (fields[1] == 'UnicodeData.txt')
				elif matches:
					if inBlocks:
						fields = re.split(r'[.]+|;', line)
						bs = int(fields[0], 16)
						be = int(fields[1], 16)
						if self.blockBits.getAny(bs, be):
							raise ValueError('overlapping block data: ' + line)
						else:
							self.blockBits.setAll(bs, be)
							self.blockLines.append(line)
					if inChars:
						fields = re.split(r';', line)
						ch = int(fields[0], 16)
						if self.charBits.get(ch):
							raise ValueError('overlapping character data: ' + line)
						else:
							self.charBits.set(ch)
							self.charLines.append(line)
		if matches:
			self.matchedFiles.append({
				'file': file,
				'flags': fileFlags,
				'substrings': fileSubstrings
			})

	def processFiles(self):
		for file in self.files:
			self.processFile(file, True)
		datadir = os.path.normpath(os.path.join(os.path.dirname(os.path.realpath(__file__)), '..', 'unicodedata'))
		for file in os.listdir(datadir):
			self.processFile(os.path.join(datadir, file), False)

	def printBlocks(self):
		self.blockLines.sort(key=lambda line: int(re.split(r'[.]+|;', line)[0], 16))
		for line in self.blockLines:
			print(line)

	def printUnicodeData(self):
		self.charLines.sort(key=lambda line: int(re.split(r';', line)[0], 16))
		for line in self.charLines:
			print(line)

	def printMatchedFiles(self, prefix=''):
		self.matchedFiles.sort(key=lambda m: m['file'])
		for m in self.matchedFiles:
			print(prefix + m['file'])

	def printMatchedFlags(self, prefix=''):
		self.matchedFiles.sort(key=lambda m: m['file'])
		for m in self.matchedFiles:
			print(prefix + m['flags'][0])

if __name__ == '__main__':
	p = DataParser()
	p.parseArgs(sys.argv[1:])
	p.processFiles()
	if p.matchedFiles:
		print('Matched files:')
		p.printMatchedFiles('  ')
		print('Matched flags:')
		p.printMatchedFlags('  ')
