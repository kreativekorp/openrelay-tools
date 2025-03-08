#!/usr/bin/env python

from __future__ import print_function
from bitset import BitSet
import os
import re
import sys

class DataParser:
	def __init__(self):
		self.parseOptions = True
		self.actions = []
		self.files = []
		self.flags = []
		self.superstring = ''
		self.matchedFiles = []
		self.blockBits = BitSet()
		self.charBits = BitSet()
		self.blockLines = []
		self.charLines = []
		self.fileLines = {}

	def printHelp(self, file=None):
		print('Create Unicode data files for characters in the Private Use Area.', file=file)
		print('  --<flag>        Include the source file matching the specified flag.', file=file)
		print('  --no-<flag>     Exclude the source file matching the specified flag.', file=file)
		print('  [-s] <string>   Include all source files matching the specified superstring.', file=file)
		print('  [-f] <path>     Include the specified source file.', file=file)
		print('  -b              Print Blocks.txt to standard output.', file=file)
		print('  -u              Print UnicodeData.txt to standard output.', file=file)
		print('  -p <filename>   Print a specified data file (e.g. CaseFolding.txt) to stdout.', file=file)
		print('  -o <path>       Write a single data file or a directory of all data files.', file=file)
		print('  -l              Print paths of all matched source files (list).', file=file)
		print('  -x              Print flags of all matched source files (expand).', file=file)
		print('  -m              Print both paths and flags of all matched source files.', file=file)

	def parseArgs(self, args):
		args = list(args)
		def w1(f):
			a = args.pop(0)
			return lambda: f(a)
		while args:
			arg = args.pop(0)
			if self.parseOptions and arg[0] == '-':
				if arg == '--':
					self.parseOptions = False
				elif arg == '-h' or arg == '-help' or arg == '--help':
					self.actions.append(lambda: self.printHelp())
				elif arg == '-b':
					self.actions.append(lambda: self.printBlocks())
				elif arg == '-u':
					self.actions.append(lambda: self.printUnicodeData())
				elif arg == '-p' and args:
					self.actions.append(w1(lambda a: self.printFile(a)))
				elif arg == '-o' and args:
					self.actions.append(w1(lambda a: self.writePath(a)))
				elif arg == '-l':
					self.actions.append(lambda: self.printMatchedFiles())
				elif arg == '-x':
					self.actions.append(lambda: self.printMatchedFlags())
				elif arg == '-m':
					self.actions.append(lambda: self.printMatches())
				elif arg == '-f' and args:
					self.files.append(args.pop(0))
				elif arg == '-s' and args:
					self.superstring += args.pop(0)
				else:
					self.flags.append(arg)
			else:
				if '/' in arg or '.' in arg:
					self.files.append(arg)
				elif '-' in arg:
					self.flags.append(arg)
				else:
					self.superstring += arg

	def processFile(self, file, matchesFile):
		matchesFlag = False
		matchesNoFlag = False
		matchesSubstring = False
		fileFlags = []
		fileSubstrings = []
		with open(file, 'r') as lines:
			fileName = None
			for line in lines:
				line = line.strip()
				if line[0] == '@':
					fields = re.split(r'\s+', line)
					if fields[0] == '@flag':
						fileFlags.append(fields[1])
						if fields[1] in self.flags:
							matchesFlag = True
						if re.sub(r'^(-*)', r'\1no-', fields[1]) in self.flags:
							matchesNoFlag = True
					elif fields[0] == '@substring':
						fileSubstrings.append(fields[1])
						if fields[1] in self.superstring:
							matchesSubstring = True
					elif fields[0] == '@file':
						fileName = fields[1]
				elif matchesFile or ((matchesFlag or matchesSubstring) and not matchesNoFlag):
					if fileName == 'Blocks.txt':
						fields = re.split(r'[.]+|;', line)
						bs = int(fields[0], 16)
						be = int(fields[1], 16)
						if self.blockBits.getAny(bs, be):
							raise ValueError('overlapping block data: ' + line)
						else:
							self.blockBits.setAll(bs, be)
							self.blockLines.append(line)
					elif fileName == 'UnicodeData.txt':
						fields = re.split(r';', line)
						ch = int(fields[0], 16)
						if self.charBits.get(ch):
							raise ValueError('overlapping character data: ' + line)
						else:
							self.charBits.set(ch)
							self.charLines.append(line)
					elif fileName is not None:
						if fileName in self.fileLines:
							self.fileLines[fileName].append(line)
						else:
							self.fileLines[fileName] = [line]
		if matchesFile or ((matchesFlag or matchesSubstring) and not matchesNoFlag):
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

	def printBlocks(self, file=None):
		self.blockLines.sort(key=lambda line: int(re.split(r'[.]+|;', line)[0], 16))
		for line in self.blockLines:
			print(line, file=file)

	def printUnicodeData(self, file=None):
		self.charLines.sort(key=lambda line: int(re.split(r';', line)[0], 16))
		for line in self.charLines:
			print(line, file=file)

	def printFile(self, fileName, file=None):
		if fileName == 'Blocks.txt':
			self.printBlocks(file=file)
		elif fileName == 'UnicodeData.txt':
			self.printUnicodeData(file=file)
		elif fileName in self.fileLines:
			for line in self.fileLines[fileName]:
				print(line, file=file)

	def writeFile(self, fileName, file=None, isdir=False):
		if file is None:
			file = fileName
		elif isdir:
			os.makedirs(file, exist_ok=True)
			file = os.path.join(file, fileName)
		with open(file, 'w') as f:
			self.printFile(fileName, file=f)

	def writeDir(self, file=None):
		if self.blockLines:
			self.writeFile('Blocks.txt', file=file, isdir=True)
		if self.charLines:
			self.writeFile('UnicodeData.txt', file=file, isdir=True)
		for fileName in self.fileLines:
			self.writeFile(fileName, file=file, isdir=True)

	def writePath(self, file=None):
		if file is None or os.path.isdir(file):
			self.writeDir(file=file)
		else:
			fileName = os.path.basename(file)
			if os.path.isfile(file) or fileName.endswith('.txt'):
				self.writeFile(fileName, file=file)
			else:
				self.writeDir(file=file)

	def printMatchedFiles(self, prefix='', file=None):
		self.matchedFiles.sort(key=lambda m: m['file'])
		for m in self.matchedFiles:
			print(prefix + m['file'], file=file)

	def printMatchedFlags(self, prefix='', file=None):
		self.matchedFiles.sort(key=lambda m: m['file'])
		for m in self.matchedFiles:
			print(prefix + m['flags'][0], file=file)

	def printMatches(self, file=None):
		print('Matched files:', file=file)
		self.printMatchedFiles('  ', file=file)
		print('Matched flags:', file=file)
		self.printMatchedFlags('  ', file=file)

	def processActions(self):
		for action in self.actions:
			action()

def main(args):
	p = DataParser()
	p.parseArgs(args)
	p.processFiles()
	if p.actions:
		p.processActions()
	elif p.matchedFiles:
		p.printMatches()

if __name__ == '__main__':
	main(sys.argv[1:])
